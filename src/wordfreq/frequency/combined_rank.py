"""Combined-rank scoring across wordfreq corpora and tier sources.

Replacement for the legacy ``wordfreq.frequency.analysis.calculate_combined_ranks``
which read the now-deprecated ``WordFrequency`` table. This module rolls the
new lexeme-level signal up to a single integer ``Lemma.frequency_rank`` per
English lemma:

  * Wordfreq corpora — for each enabled corpus, every English lexeme is
    ordered by its rolled-up ``LexemeFrequency.total_frequency`` (already
    share-split across homographs by ``sense_prominence``); the resulting
    1..N position is the per-corpus synthetic rank. Corpus-level weight comes
    from ``Corpus.corpus_weight`` (synced from ``CORPUS_CONFIGS``).
  * Cambridge YLE — fixed synthetic ranks per tier (``starters``/``movers``/
    ``flyers``), weight 1.0.
  * CEFR — fixed synthetic ranks per tier (``A1``..``C2``), weight 1.0.

Per-lemma combined rank is the weighted harmonic mean of the sources that
actually contributed:

    combined = sum(w_i) / sum(w_i / rank_i)

Lemmas with zero contributing sources keep their existing ``frequency_rank``
value (so noisy partial runs do not wipe data). Lemmas whose only forms are
multi-word (no ``word_token_id``) rolling up to zero across all corpora can
still receive a rank from tier signals alone.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from storage.backend import create_session
from storage.backend.config import DataSourceConfig
from storage.models.schema import Corpus, Lemma, LemmaTier
from wordfreq.frequency.corpus import get_enabled_corpus_configs

logger = logging.getLogger(__name__)


# Synthetic rank assignments for tier sources. Lower = more common.
YLE_TIER_RANKS: Dict[str, int] = {
    "starters": 200,
    "movers": 800,
    "flyers": 2000,
}
YLE_TIER_WEIGHT: float = 1.0

CEFR_TIER_RANKS: Dict[str, int] = {
    "A1": 500,
    "A2": 1500,
    "B1": 3000,
    "B2": 6000,
    "C1": 12000,
    "C2": 25000,
}
CEFR_TIER_WEIGHT: float = 1.0

# Lemmas are written back in batches of this size to bound the per-commit
# transaction footprint on a large corpus.
_BATCH_SIZE: int = 1000


def _english_lemma_ids(session: Session) -> List[int]:
    """Return the ids of every Lemma that has at least one English DerivativeForm.

    We only assign ``frequency_rank`` to lemmas that have an English lexeme,
    since the wordfreq corpora are English. Tier sources (YLE/CEFR) likewise
    annotate English. A lemma without an English lexeme stays unranked.
    """
    from storage.models.schema import DerivativeForm

    rows = (
        session.query(DerivativeForm.lemma_id)
        .filter(DerivativeForm.language_code == "en")
        .distinct()
        .all()
    )
    return [row[0] for row in rows]


def _build_corpus_rank_table(
    session: Session,
    corpus_name: str,
    lemma_ids: List[int],
) -> Dict[int, int]:
    """Rank lemmas by their per-corpus rolled-up frequency.

    Returns ``{lemma_id: rank}`` where rank is 1-based and most-frequent first.
    Lemmas with zero or missing rollup in this corpus are omitted.
    """
    # Imported lazily to avoid a circular import via storage.lexeme ->
    # storage.models.schema -> wordfreq.frequency package init.
    from storage.lexeme import get_lexeme
    from wordfreq.lexeme_frequency import get_lexeme_frequency

    scored: List[Tuple[int, float]] = []
    for lemma_id in lemma_ids:
        lexeme = get_lexeme(session, lemma_id, "en")
        if lexeme is None:
            continue
        rollup = get_lexeme_frequency(session, lexeme, corpus_name)
        if rollup.total_frequency > 0.0:
            scored.append((lemma_id, rollup.total_frequency))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return {lemma_id: i + 1 for i, (lemma_id, _) in enumerate(scored)}


def _corpus_weights(session: Session) -> Dict[str, float]:
    """Map enabled wordfreq corpus name -> ``Corpus.corpus_weight``.

    Falls back to the in-code ``CorpusConfig.corpus_weight`` when no DB row
    exists yet (fresh DB before pradzia sync). Only returns weights > 0.
    """
    db_rows = {row.name: row.corpus_weight for row in session.query(Corpus).all()}
    weights: Dict[str, float] = {}
    for cfg in get_enabled_corpus_configs():
        weight = db_rows.get(cfg.name, cfg.corpus_weight)
        if weight > 0.0:
            weights[cfg.name] = weight
    return weights


def _tier_rank_for_lemma(
    tier_rows: Dict[Tuple[int, str], str],
    lemma_id: int,
    source: str,
    rank_table: Dict[str, int],
) -> Optional[int]:
    """Return the synthetic rank for ``(lemma_id, source)``, or None if unmapped."""
    tier_name = tier_rows.get((lemma_id, source))
    if tier_name is None:
        return None
    return rank_table.get(tier_name)


def _harmonic_mean(weighted_ranks: List[Tuple[float, int]]) -> Optional[int]:
    """Weighted harmonic mean of (weight, rank) pairs. None if no contributors."""
    if not weighted_ranks:
        return None
    total_weight = 0.0
    weighted_inv = 0.0
    for weight, rank in weighted_ranks:
        if rank <= 0:
            continue
        total_weight += weight
        weighted_inv += weight / rank
    if weighted_inv <= 0.0:
        return None
    return int(round(total_weight / weighted_inv))


def calculate_lemma_combined_ranks(
    config: DataSourceConfig,
    *,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Compute ``Lemma.frequency_rank`` from lexeme rollups + tier signals.

    Args:
        config: DataSourceConfig describing the database to read/write.
        dry_run: If True, compute the ranks but do not write them back.

    Returns:
        A summary dict: success flag, counts of updated/skipped lemmas, and
        the ordered list of source names that contributed at least one rank.
    """
    logger.info(f"Calculating lemma combined ranks (dry_run={dry_run})...")
    session = create_session(config)
    try:
        lemma_ids = _english_lemma_ids(session)
        logger.info(f"Found {len(lemma_ids)} English lemmas to score")

        corpus_weights = _corpus_weights(session)
        logger.info(f"Active corpora ({len(corpus_weights)}): " f"{sorted(corpus_weights.keys())}")

        per_corpus_ranks: Dict[str, Dict[int, int]] = {}
        for corpus_name in corpus_weights:
            logger.info(f"Ranking lemmas within corpus '{corpus_name}'...")
            per_corpus_ranks[corpus_name] = _build_corpus_rank_table(
                session, corpus_name, lemma_ids
            )

        tier_rows_q = session.query(LemmaTier.lemma_id, LemmaTier.source, LemmaTier.tier_name).all()
        tier_rows: Dict[Tuple[int, str], str] = {
            (row.lemma_id, row.source): row.tier_name for row in tier_rows_q
        }

        sources_used: set[str] = set()
        new_ranks: Dict[int, int] = {}
        skipped = 0

        for lemma_id in lemma_ids:
            contributors: List[Tuple[float, int]] = []

            for corpus_name, weight in corpus_weights.items():
                rank = per_corpus_ranks[corpus_name].get(lemma_id)
                if rank is not None:
                    contributors.append((weight, rank))
                    sources_used.add(f"wordfreq_{corpus_name}")

            yle_rank = _tier_rank_for_lemma(tier_rows, lemma_id, "cambridge_yle", YLE_TIER_RANKS)
            if yle_rank is not None:
                contributors.append((YLE_TIER_WEIGHT, yle_rank))
                sources_used.add("cambridge_yle")

            cefr_rank = _tier_rank_for_lemma(tier_rows, lemma_id, "cefr", CEFR_TIER_RANKS)
            if cefr_rank is not None:
                contributors.append((CEFR_TIER_WEIGHT, cefr_rank))
                sources_used.add("cefr")

            combined = _harmonic_mean(contributors)
            if combined is None:
                skipped += 1
                continue
            new_ranks[lemma_id] = combined

        logger.info(
            f"Computed ranks for {len(new_ranks)} lemmas; "
            f"{skipped} skipped (no contributing sources)"
        )

        if dry_run:
            return {
                "dry_run": True,
                "success": True,
                "lemmas_scored": len(new_ranks),
                "lemmas_skipped": skipped,
                "sources_used": sorted(sources_used),
            }

        updated = 0
        ids = list(new_ranks.keys())
        for offset in range(0, len(ids), _BATCH_SIZE):
            batch_ids = ids[offset : offset + _BATCH_SIZE]
            lemmas = session.query(Lemma).filter(Lemma.id.in_(batch_ids)).all()
            for lemma in lemmas:
                target = new_ranks[lemma.id]
                if lemma.frequency_rank != target:
                    lemma.frequency_rank = target
                    updated += 1
            session.commit()
            logger.info(f"Wrote {min(offset + _BATCH_SIZE, len(ids))}/{len(ids)} lemma ranks")

        logger.info(f"Lemma combined-rank update complete: {updated} rows changed")
        return {
            "dry_run": False,
            "success": True,
            "lemmas_scored": len(new_ranks),
            "lemmas_updated": updated,
            "lemmas_skipped": skipped,
            "sources_used": sorted(sources_used),
        }
    finally:
        session.close()


__all__ = [
    "CEFR_TIER_RANKS",
    "CEFR_TIER_WEIGHT",
    "YLE_TIER_RANKS",
    "YLE_TIER_WEIGHT",
    "calculate_lemma_combined_ranks",
]
