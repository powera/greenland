"""Combined-rank scoring across wordfreq corpora and tier sources.

Replacement for the legacy ``wordfreq.frequency.analysis.calculate_combined_ranks``
which read the now-deprecated ``WordFrequency`` table. This module rolls the
new lexeme-level signal up to a single integer ``Lemma.frequency_rank`` per
English lemma:

  * Wordfreq corpora — for each enabled corpus, a lexeme's rank is its own
    forms' imported ranks combined under the corpus's fitted Zipf exponent
    (see ``wordfreq.frequency.zipf``); spelling variants count as forms, so
    "aluminium" contributes to "aluminum". Corpus-level weight comes from
    ``Corpus.corpus_weight`` (synced from ``CORPUS_CONFIGS``).

    These per-corpus ranks depend only on the lemma being scored. Nothing is
    sorted across lemmas, so one word can be rescored after an edit without
    recomputing the database, and two lemmas may share a rank.
  * Cambridge YLE — fixed synthetic ranks per tier (``starters``/``movers``/
    ``flyers``), weight 1.0.
  * CEFR — fixed synthetic ranks per tier (``A1``..``C2``), weight 1.0.
  * Basic English — fixed synthetic ranks per tier (``basic``/``extended``),
    weight 1.0.

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

from storage.models.schema import Corpus, ExternalLexemeAnnotation, Lemma, LemmaTier
from wordfreq.frequency.corpus import CorpusConfig, get_enabled_corpus_configs
from wordfreq.frequency.zipf import DEFAULT_ZIPF_EXPONENT, combine_ranks, fit_zipf_exponent

logger = logging.getLogger(__name__)


# Synthetic rank assignments for tier sources. Lower = more common.
YLE_TIER_RANKS: Dict[str, int] = {
    "starters": 325,
    "movers": 750,
    "flyers": 1200,
}
YLE_TIER_WEIGHT: float = 1.0
# Rank assigned when a lemma is absent from YLE entirely. Set higher than
# the last YLE tier (flyers=1200) would suggest because the combined score
# is a harmonic mean, which is dominated by the smallest contributor — a
# floor near the tier range would single-handedly pin truly-rare words to
# a deceptively common combined rank.
YLE_UNKNOWN_RANK: int = 7500

CEFR_TIER_RANKS: Dict[str, int] = {
    "A1": 800,
    "A2": 2100,
    "B1": 4200,
    "B2": 6900,
    "C1": 12000,
    "C2": 20000,
}
CEFR_TIER_WEIGHT: float = 1.0
# Rank assigned when a lemma is absent from CEFR entirely. Just past C2
# (20000) so words outside the CEFR vocabulary get pushed below it.
CEFR_UNKNOWN_RANK: int = 25000

BASIC_ENGLISH_TIER_RANKS: Dict[str, int] = {
    "basic": 600,
    "extended": 1600,
}
BASIC_ENGLISH_TIER_WEIGHT: float = 1.0
# Rank assigned when a lemma is absent from Basic English entirely. Set
# higher than extended (1600) would suggest because the combined score is
# a harmonic mean, which is dominated by the smallest contributor — a
# floor near the tier range would single-handedly pin truly-rare words to
# a deceptively common combined rank.
BASIC_ENGLISH_UNKNOWN_RANK: int = 7500

# Lemmas are written back in batches of this size to bound the per-commit
# transaction footprint on a large corpus.
_BATCH_SIZE: int = 1000

# Floor used when a wordfreq corpus has no entry for a lemma. Each corpus
# can override this via ``CorpusConfig.max_unknown_rank``; when neither is
# set, we fall back to this value (chosen to be larger than the largest
# corpus we currently load).
_DEFAULT_UNKNOWN_RANK: int = 20000


def _english_lemma_ids(session: Session) -> List[int]:
    """Return the ids of every Lemma that has at least one English DerivativeForm.

    We only assign ``frequency_rank`` to lemmas that have an English lexeme,
    since the wordfreq corpora are English. Tier sources (YLE/CEFR) likewise
    annotate English. A lemma without an English lexeme stays unranked.
    """
    from storage.models.schema import DerivativeForm, Lemma

    rows = (
        session.query(DerivativeForm.lemma_id)
        .join(Lemma, DerivativeForm.lemma_id == Lemma.id)
        .filter(
            DerivativeForm.language_code == "en",
        )
        .distinct()
        .all()
    )
    return [row[0] for row in rows]


#: Fitted Zipf exponent per corpus name. The exponent is a property of the
#: corpus data, which does not change while a process runs, and fitting it
#: reads every annotation row for that corpus -- so scoring lemmas one at a
#: time must not refit it each call. Re-importing a corpus in the same process
#: invalidates this; call :func:`clear_zipf_exponent_cache` if that happens.
_ZIPF_EXPONENT_CACHE: Dict[str, float] = {}


def clear_zipf_exponent_cache() -> None:
    """Forget the fitted exponents, so the next call refits from the database."""
    _ZIPF_EXPONENT_CACHE.clear()


def get_corpus_zipf_exponent(session: Session, corpus_name: str) -> float:
    """This corpus's Zipf exponent, fitted from its imported (rank, frequency) pairs.

    The fit is a least-squares regression over every ranked form in the corpus,
    so it needs each form's frequency -- it is not derivable from the corpus
    size. It is memoized because it depends only on the corpus data, and every
    lemma scored against that corpus wants the same number.
    """
    cached = _ZIPF_EXPONENT_CACHE.get(corpus_name)
    if cached is not None:
        return cached

    rows = (
        session.query(ExternalLexemeAnnotation.ordinal_rank, ExternalLexemeAnnotation.frequency)
        .filter(
            ExternalLexemeAnnotation.source == f"wordfreq_{corpus_name}",
            ExternalLexemeAnnotation.ordinal_rank.isnot(None),
            ExternalLexemeAnnotation.frequency.isnot(None),
        )
        .all()
    )
    exponent = fit_zipf_exponent((rank, frequency) for rank, frequency in rows)
    if exponent is None:
        logger.info(
            f"Corpus '{corpus_name}': too few usable pairs to fit a Zipf exponent; "
            f"using default {DEFAULT_ZIPF_EXPONENT}"
        )
        exponent = DEFAULT_ZIPF_EXPONENT
    else:
        logger.info(f"Corpus '{corpus_name}': fitted Zipf exponent s={exponent:.3f}")

    _ZIPF_EXPONENT_CACHE[corpus_name] = exponent
    return exponent


def get_corpus_size(session: Session, corpus_name: str) -> int:
    """How many surface forms this corpus ranks.

    The corpus's own size, not how many lemmas happen to match it: the
    unknown-rank floor is meant to say "worse than anything this corpus
    contains", which is a fact about the corpus file.
    """
    count: int = (
        session.query(ExternalLexemeAnnotation)
        .filter(
            ExternalLexemeAnnotation.source == f"wordfreq_{corpus_name}",
            ExternalLexemeAnnotation.ordinal_rank.isnot(None),
        )
        .count()
    )
    return count


def get_lemma_corpus_rank(
    session: Session,
    lemma_id: int,
    corpus_name: str,
    exponent: float,
) -> Optional[int]:
    """This lemma's rank in one corpus, from its own forms' imported ranks.

    Depends only on the lemma being scored: the corpus files already rank each
    surface form, and ``zipf.combine_ranks`` folds a lemma's forms into one
    rank without reference to any other lemma. That is what lets a single word
    be rescored after an edit -- adding a variant spelling, say -- instead of
    re-ranking the database.

    Returns:
        The combined rank, or None when this corpus ranks none of the lemma's
        forms.
    """
    # Imported lazily to avoid a circular import via storage.lexeme ->
    # storage.models.schema -> wordfreq.frequency package init.
    from storage.lexeme import get_lexeme
    from wordfreq.lexeme_frequency import get_lexeme_form_ranks

    lexeme = get_lexeme(session, lemma_id, "en")
    if lexeme is None:
        return None
    form_ranks = get_lexeme_form_ranks(session, lexeme, corpus_name)
    if not form_ranks:
        return None
    return combine_ranks(form_ranks, exponent)


def _build_corpus_rank_table(
    session: Session,
    corpus_name: str,
    lemma_ids: List[int],
) -> Dict[int, int]:
    """Each lemma's rank in this corpus, combined from its forms' stored ranks.

    Returns ``{lemma_id: rank}``. Lemmas with no ranked form in this corpus are
    omitted. The values are rank-like numbers rather than positions in an
    ordering: ties and gaps are both expected, and each entry is computed
    independently of the others.
    """
    exponent = get_corpus_zipf_exponent(session, corpus_name)

    table: Dict[int, int] = {}
    for lemma_id in lemma_ids:
        rank = get_lemma_corpus_rank(session, lemma_id, corpus_name, exponent)
        if rank is not None:
            table[lemma_id] = rank
    return table


def _corpus_weights(session: Session) -> Dict[str, float]:
    """Map enabled wordfreq corpus name -> ``Corpus.corpus_weight``.

    Falls back to the in-code ``CorpusConfig.corpus_weight`` when no DB row
    exists yet (fresh DB before corpus configuration sync). Only returns weights > 0.
    """
    db_rows = {row.name: row.corpus_weight for row in session.query(Corpus).all()}
    weights: Dict[str, float] = {}
    for cfg in get_enabled_corpus_configs():
        weight = db_rows.get(cfg.name, cfg.corpus_weight)
        if weight > 0.0:
            weights[cfg.name] = weight
    return weights


def _enabled_corpus_configs_by_name() -> Dict[str, CorpusConfig]:
    return {cfg.name: cfg for cfg in get_enabled_corpus_configs()}


def _unknown_rank_for_corpus(cfg: CorpusConfig, corpus_size: int) -> int:
    """Effective rank to assign when a lemma is absent from this corpus.

    Mirrors ``CorpusConfig.get_effective_unknown_rank`` but uses our local
    ``_DEFAULT_UNKNOWN_RANK`` floor. Lower of (configured cap, max(corpus
    size, default)) so a corpus's "missing" rank is never more flattering
    than the worst rank actually present in the corpus.
    """
    return cfg.get_effective_unknown_rank(corpus_size, _DEFAULT_UNKNOWN_RANK)


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


def recalculate_lemma_rank(
    session: Session,
    lemma_id: int,
    *,
    dry_run: bool = False,
) -> Optional[int]:
    """Recompute and store ``frequency_rank`` for a single lemma.

    Scores one word the same way :func:`calculate_lemma_combined_ranks` scores
    all of them, but touches only that word. Use it after an edit that changes
    which surface forms a lemma owns -- adding a spelling variant, linking a
    form to a token -- rather than rebuilding every rank in the database.

    Args:
        session: Session bound to the target database. The caller commits.
        lemma_id: The lemma to rescore.
        dry_run: Compute the rank but leave the row unchanged.

    Returns:
        The computed rank, or None when nothing contributed one (the stored
        value is then left alone, as in the bulk path).
    """
    corpus_weights = _corpus_weights(session)
    cfgs_by_name = _enabled_corpus_configs_by_name()

    contributors: List[Tuple[float, int]] = []
    corpus_ranks: Dict[str, Optional[int]] = {}
    for corpus_name in corpus_weights:
        exponent = get_corpus_zipf_exponent(session, corpus_name)
        corpus_ranks[corpus_name] = get_lemma_corpus_rank(session, lemma_id, corpus_name, exponent)

    has_wordfreq_hit = any(rank is not None for rank in corpus_ranks.values())
    for corpus_name, weight in corpus_weights.items():
        rank = corpus_ranks[corpus_name]
        if rank is not None:
            contributors.append((weight, rank))
        elif has_wordfreq_hit:
            cfg = cfgs_by_name.get(corpus_name)
            if cfg is None:
                unknown_rank = _DEFAULT_UNKNOWN_RANK
            else:
                unknown_rank = _unknown_rank_for_corpus(cfg, get_corpus_size(session, corpus_name))
            contributors.append((weight, unknown_rank))

    tier_rows_q = (
        session.query(LemmaTier.lemma_id, LemmaTier.source, LemmaTier.tier_name)
        .filter(LemmaTier.lemma_id == lemma_id)
        .all()
    )
    tier_rows: Dict[Tuple[int, str], str] = {
        (row.lemma_id, row.source): row.tier_name for row in tier_rows_q
    }

    for source, rank_table, weight, unknown_rank in (
        ("cambridge_yle", YLE_TIER_RANKS, YLE_TIER_WEIGHT, YLE_UNKNOWN_RANK),
        ("cefr", CEFR_TIER_RANKS, CEFR_TIER_WEIGHT, CEFR_UNKNOWN_RANK),
        (
            "basic_english",
            BASIC_ENGLISH_TIER_RANKS,
            BASIC_ENGLISH_TIER_WEIGHT,
            BASIC_ENGLISH_UNKNOWN_RANK,
        ),
    ):
        tier_rank = _tier_rank_for_lemma(tier_rows, lemma_id, source, rank_table)
        contributors.append((weight, tier_rank if tier_rank is not None else unknown_rank))

    combined = _harmonic_mean(contributors)
    if combined is None:
        return None

    if not dry_run:
        lemma = session.query(Lemma).filter(Lemma.id == lemma_id).first()
        if lemma is not None and lemma.frequency_rank != combined:
            lemma.frequency_rank = combined
    return combined


def calculate_lemma_combined_ranks(
    session: Session,
    *,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Compute ``Lemma.frequency_rank`` from lexeme rollups + tier signals.

    The caller owns the session lifecycle. Mid-stream commits are issued
    while writing back ranks in batches.

    Args:
        session: SQLAlchemy session bound to the target database.
        dry_run: If True, compute the ranks but do not write them back.

    Returns:
        A summary dict: success flag, counts of updated/skipped lemmas, and
        the ordered list of source names that contributed at least one rank.
    """
    logger.info(f"Calculating lemma combined ranks (dry_run={dry_run})...")
    lemma_ids = _english_lemma_ids(session)
    logger.info(f"Found {len(lemma_ids)} English lemmas to score")

    corpus_weights = _corpus_weights(session)
    logger.info(f"Active corpora ({len(corpus_weights)}): " f"{sorted(corpus_weights.keys())}")

    per_corpus_ranks: Dict[str, Dict[int, int]] = {}
    for corpus_name in corpus_weights:
        logger.info(f"Ranking lemmas within corpus '{corpus_name}'...")
        per_corpus_ranks[corpus_name] = _build_corpus_rank_table(session, corpus_name, lemma_ids)

    # Per-corpus "unknown" rank: applied when a lemma has no rollup in a given
    # corpus. Without this floor, a word that appears only in a small corpus
    # (e.g. "baking" in cooking) gets a deceptively high combined rank because
    # the larger corpora silently drop out of the harmonic mean.
    cfgs_by_name = _enabled_corpus_configs_by_name()
    unknown_rank_by_corpus: Dict[str, int] = {}
    for corpus_name in corpus_weights:
        cfg = cfgs_by_name.get(corpus_name)
        if cfg is None:
            unknown_rank_by_corpus[corpus_name] = _DEFAULT_UNKNOWN_RANK
        else:
            unknown_rank_by_corpus[corpus_name] = _unknown_rank_for_corpus(
                cfg, get_corpus_size(session, corpus_name)
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

        # Track whether this lemma had a positive signal in *any* wordfreq
        # corpus. Only then do we apply the unknown-rank floor for the other
        # wordfreq corpora — otherwise a lemma with zero wordfreq presence
        # would be ranked purely from "missing everywhere" floors, which is
        # misleading. Tier-only lemmas continue to fall through to the
        # tier-source contributors below.
        has_wordfreq_hit = any(
            per_corpus_ranks[name].get(lemma_id) is not None for name in corpus_weights
        )

        for corpus_name, weight in corpus_weights.items():
            rank = per_corpus_ranks[corpus_name].get(lemma_id)
            if rank is not None:
                contributors.append((weight, rank))
                sources_used.add(f"wordfreq_{corpus_name}")
            elif has_wordfreq_hit:
                contributors.append((weight, unknown_rank_by_corpus[corpus_name]))
                sources_used.add(f"wordfreq_{corpus_name}_unknown")

        # For each tier source, contribute either the lemma's tier rank or the
        # tier's "unknown" floor if the lemma is absent. Unlike wordfreq
        # corpora, we apply the floor unconditionally — these are curated
        # English vocabulary lists, so "absent" is a real signal that the
        # word is at least somewhat outside the everyday/learner core.
        yle_rank = _tier_rank_for_lemma(tier_rows, lemma_id, "cambridge_yle", YLE_TIER_RANKS)
        if yle_rank is not None:
            contributors.append((YLE_TIER_WEIGHT, yle_rank))
            sources_used.add("cambridge_yle")
        else:
            contributors.append((YLE_TIER_WEIGHT, YLE_UNKNOWN_RANK))
            sources_used.add("cambridge_yle_unknown")

        cefr_rank = _tier_rank_for_lemma(tier_rows, lemma_id, "cefr", CEFR_TIER_RANKS)
        if cefr_rank is not None:
            contributors.append((CEFR_TIER_WEIGHT, cefr_rank))
            sources_used.add("cefr")
        else:
            contributors.append((CEFR_TIER_WEIGHT, CEFR_UNKNOWN_RANK))
            sources_used.add("cefr_unknown")

        be_rank = _tier_rank_for_lemma(
            tier_rows, lemma_id, "basic_english", BASIC_ENGLISH_TIER_RANKS
        )
        if be_rank is not None:
            contributors.append((BASIC_ENGLISH_TIER_WEIGHT, be_rank))
            sources_used.add("basic_english")
        else:
            contributors.append((BASIC_ENGLISH_TIER_WEIGHT, BASIC_ENGLISH_UNKNOWN_RANK))
            sources_used.add("basic_english_unknown")

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


__all__ = [
    "BASIC_ENGLISH_TIER_RANKS",
    "BASIC_ENGLISH_TIER_WEIGHT",
    "BASIC_ENGLISH_UNKNOWN_RANK",
    "CEFR_TIER_RANKS",
    "CEFR_TIER_WEIGHT",
    "CEFR_UNKNOWN_RANK",
    "YLE_TIER_RANKS",
    "YLE_TIER_WEIGHT",
    "YLE_UNKNOWN_RANK",
    "calculate_lemma_combined_ranks",
    "clear_zipf_exponent_cache",
    "get_corpus_size",
    "get_corpus_zipf_exponent",
    "get_lemma_corpus_rank",
    "recalculate_lemma_rank",
]
