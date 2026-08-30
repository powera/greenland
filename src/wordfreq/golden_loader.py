"""Load wordfreq frequency + tier data into the JSONL backend's in-memory DB.

Golden/hosted personas serve from JSONL files in ``data/release/`` via a cached
in-memory SQLite database. That database normally only holds lemma/sentence
data because the wordfreq frequency signal is not (yet) checked into the
release directory. This module loads the frequency sources directly
from their on-disk files into the same in-memory SQLite so that
``Lemma.frequency_rank``, ``ExternalLexemeAnnotation``, and ``LemmaTier``
queries return real data in golden mode.

The sources:
    1. every enabled wordfreq corpus (see ``frequency.corpus.CORPUS_CONFIGS``)
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
from wordfreq.lexeme_frequency import link_forms_to_word_tokens
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


def _ensure_corpus_rows(session: Session) -> None:
    """Insert ``Corpus`` rows from CORPUS_CONFIGS if missing.

    The combined-rank pass reads ``Corpus.corpus_weight``; without rows it
    falls back to in-code defaults, but populating the table makes the
    in-memory state match what a bootstrapped database looks like after corpus sync.
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
            link_counts = link_forms_to_word_tokens(session)
            summary["derivative_form_links"] = link_counts["derivative_forms"]
            logger.info(
                f"Golden loader: linked {link_counts['derivative_forms']} DerivativeForms "
                f"and {link_counts['variant_forms']} VariantForms to WordTokens"
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
