"""Load wordfreq frequency + tier data into the JSONL backend's in-memory DB.

Golden/hosted personas serve from JSONL files in ``data/release/`` via a cached
in-memory SQLite database. That database normally only holds lemma/sentence
data because the wordfreq frequency signal is not (yet) checked into the
release directory. This module loads the seven frequency sources directly
from their on-disk files into the same in-memory SQLite so that
``Lemma.frequency_rank``, ``ExternalLexemeAnnotation``, and ``LemmaTier``
queries return real data in golden mode.

The seven sources:
    1. wordfreq corpora (4): 19th_books, 20th_books, wiki_vital, cooking
    2. tier sources (3): cambridge_yle, cefr, basic_english

After loading, ``Lemma.frequency_rank`` is recomputed from the rolled-up
lexeme frequencies and tier signals so the dictionary/lemma views surface
the combined rank without a separate sync step.

Intended to be called from a background thread after Flask starts serving;
the JSONL SQLite backend uses ``StaticPool`` + ``check_same_thread=False``
so cross-thread writes are safe but will briefly contend with read queries.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session, sessionmaker

from wordfreq.frequency import combined_rank, corpus
from wordfreq.tiers.basic_english import BasicEnglishImporter
from wordfreq.tiers.cambridge_yle import CambridgeYleImporter
from wordfreq.tiers.cefr import CefrImporter
from wordfreq.tiers.runner import run_import as run_tier_import

if TYPE_CHECKING:
    from storage.backend.jsonl.storage import JSONLStorage

logger = logging.getLogger(__name__)


def _make_session_for_storage(storage: "JSONLStorage") -> Session:
    """Open a raw SQLAlchemy session against the storage's cached SQLite engine.

    Triggers cache population (loading JSONL lemmas into the in-memory DB) on
    first call by routing through a throwaway JSONLSession.
    """
    if storage._cached_sqlite_engine is None:
        # Force the cache to populate by creating one query-bearing session.
        warm = storage.create_session()
        try:
            # Any query is enough to trigger _get_or_create_cached_engine.
            from storage.backend.jsonl import models

            warm.query(models.Lemma).limit(1).all()
        finally:
            warm.close()

    engine = storage._cached_sqlite_engine
    assert engine is not None, "JSONL cached SQLite engine should be populated by now"
    factory = sessionmaker(bind=engine)
    return factory()


def _link_derivative_forms_to_word_tokens(session: Session) -> int:
    """Set ``DerivativeForm.word_token_id`` for forms whose surface text matches
    a ``WordToken``.

    The JSONL backend populates DerivativeForms from release files but never
    sets ``word_token_id`` (no WordToken loader exists). After the wordfreq
    importer creates WordToken rows for each annotated surface form, we wire
    every English DerivativeForm whose ``derivative_form_text`` matches a
    WordToken token to that WordToken. Without this link,
    ``get_lexeme_frequency`` skips every form (it filters on
    ``word_token_id is not None``) and rolls up zero for all wordfreq
    corpora — meaning lemma combined ranks in golden mode collapse to
    YLE/CEFR/Basic-English signals only.

    Matching is case-insensitive on the lowercased token text, since the
    wordfreq importer normalizes everything to lowercase.

    Returns the number of DerivativeForm rows updated.
    """
    from storage.models.schema import DerivativeForm, WordToken

    tokens = session.query(WordToken).filter(WordToken.language_code == "en").all()
    token_id_by_text: dict[str, int] = {}
    for token in tokens:
        # Wordfreq imports tokens already lowercased; defend against any
        # accidentally-cased rows by normalizing here too.
        token_id_by_text.setdefault(token.token.lower(), token.id)

    if not token_id_by_text:
        return 0

    forms = (
        session.query(DerivativeForm)
        .filter(
            DerivativeForm.language_code == "en",
            DerivativeForm.word_token_id.is_(None),
        )
        .all()
    )

    updated = 0
    for form in forms:
        text = (form.derivative_form_text or "").lower()
        if not text:
            continue
        token_id = token_id_by_text.get(text)
        if token_id is None:
            continue
        form.word_token_id = token_id
        updated += 1

    if updated:
        session.commit()
    return updated


def _ensure_corpus_rows(session: Session) -> None:
    """Insert ``Corpus`` rows from CORPUS_CONFIGS if missing.

    The combined-rank pass reads ``Corpus.corpus_weight``; without rows it
    falls back to in-code defaults, but populating the table makes the
    in-memory state match what a real DB looks like after pradzia sync.
    """
    from storage.models.schema import Corpus

    existing = {row.name for row in session.query(Corpus).all()}
    for cfg in corpus.get_all_corpus_configs():
        if cfg.name in existing:
            continue
        session.add(
            Corpus(
                name=cfg.name,
                description=cfg.description,
                corpus_weight=cfg.corpus_weight,
                max_unknown_rank=cfg.max_unknown_rank,
                enabled=cfg.enabled,
            )
        )
    session.commit()


def load_wordfreq_into_storage(storage: "JSONLStorage") -> dict[str, Any]:
    """Load all seven wordfreq sources into the JSONL backend's in-memory DB.

    Steps, in order:
      1. Open a session against the cached SQLite engine (warming it if needed).
      2. Insert ``Corpus`` rows so the combined-rank pass sees real weights.
      3. Import each enabled wordfreq corpus.
      4. Run each tier importer (Cambridge YLE, CEFR, Basic English).
      5. Compute and write ``Lemma.frequency_rank`` from the loaded data.

    Per-source failures are logged and recorded in the returned summary but do
    not abort the rest of the load.
    """
    started = time.monotonic()
    summary: dict[str, Any] = {
        "corpora": {},
        "tiers": {},
        "derivative_form_links": 0,
        "combined_rank": None,
        "elapsed_seconds": 0.0,
    }

    session = _make_session_for_storage(storage)
    try:
        _ensure_corpus_rows(session)

        logger.info("Golden loader: importing wordfreq corpora")
        summary["corpora"] = corpus.load_all_corpora(session)

        # Wire DerivativeForms (loaded from JSONL with no word_token_id) to the
        # WordTokens just created by the wordfreq importer. Without this, the
        # lexeme-frequency rollup finds no matching annotations and combined
        # ranks fall back to tier sources only.
        logger.info("Golden loader: linking DerivativeForms to WordTokens")
        try:
            summary["derivative_form_links"] = _link_derivative_forms_to_word_tokens(session)
            logger.info(
                f"Golden loader: linked {summary['derivative_form_links']} "
                f"DerivativeForms to WordTokens"
            )
        except Exception as e:
            logger.exception("Golden loader: derivative-form linking failed")
            summary["derivative_form_links"] = {"error": str(e)}

        logger.info("Golden loader: importing tier sources")
        for importer in (CambridgeYleImporter(), CefrImporter(), BasicEnglishImporter()):
            try:
                report = run_tier_import(session, importer)
                summary["tiers"][importer.source] = {
                    "total": report.total,
                    "annotations_inserted": report.annotations_inserted,
                    "lemma_links_inserted": report.lemma_links_inserted,
                    "lemma_tiers_inserted": report.lemma_tiers_inserted,
                    "unattached": report.unattached,
                }
            except Exception as e:
                logger.exception(f"Golden loader: tier import failed for {importer.source}")
                summary["tiers"][importer.source] = {"error": str(e)}

        logger.info("Golden loader: computing combined ranks")
        try:
            summary["combined_rank"] = combined_rank.calculate_lemma_combined_ranks(session)
        except Exception as e:
            logger.exception("Golden loader: combined-rank computation failed")
            summary["combined_rank"] = {"success": False, "error": str(e)}
    finally:
        session.close()

    summary["elapsed_seconds"] = time.monotonic() - started
    logger.info(f"Golden loader: complete in {summary['elapsed_seconds']:.1f}s")
    return summary
