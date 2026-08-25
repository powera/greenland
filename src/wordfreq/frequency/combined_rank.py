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

from storage.models.schema import (
    SENSE_PROMINENCE_COMMON,
    SENSE_PROMINENCE_RARE,
    SENSE_PROMINENCE_UNCOMMON,
    SENSE_PROMINENCE_VERY_COMMON,
    Corpus,
    ExternalLexemeAnnotation,
    Lemma,
    LemmaTier,
)
from wordfreq.frequency.corpus import CorpusConfig, get_enabled_corpus_configs
from wordfreq.frequency.zipf import (
    DEFAULT_ZIPF_EXPONENT,
    combine_ranks,
    combine_weighted_ranks,
    fit_zipf_exponent,
)

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

# How much of a tier signal a sense is entitled to, by Lemma.sense_prominence.
#
# A tier row says Cambridge/CEFR/Ogden listed *the spelling* "top"; the import
# fans that one judgment out to every lemma holding the spelling. Unscaled,
# that hands a rare sense the teaching-list credit earned by a common one:
# "top" the spinning toy ranks ~42000 on corpus evidence alone, but three
# borrowed tier rows at 600/750/800 pull it to ~1700, because the combined
# score is a harmonic mean and is dominated by its smallest contributor.
#
# A multiplier of 0 does not drop the contributor -- it substitutes that
# source's ``*_UNKNOWN_RANK``, exactly as an untiered lemma is already scored.
# "This sense is not on the Cambridge list" is a stronger and truer statement
# than "we have no information", and it keeps the contributor count stable for
# a lemma with thin corpus coverage.
#
# ``common`` is the schema default, so an unrated lemma takes 0.2 rather than
# full credit: a lemma sharing its spelling with nothing is unaffected either
# way (see _tier_contribution), and a contested one should not claim the whole
# signal merely because nobody has rated it yet.
TIER_PROMINENCE_MULTIPLIERS: Dict[str, float] = {
    SENSE_PROMINENCE_VERY_COMMON: 1.0,
    SENSE_PROMINENCE_COMMON: 0.2,
    SENSE_PROMINENCE_UNCOMMON: 0.0,
    SENSE_PROMINENCE_RARE: 0.0,
}

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

    The corpus files already rank each surface form, and
    ``zipf.combine_weighted_ranks`` folds a lemma's forms into one rank. Each
    form's rank is scaled by this lemma's share of it, so senses competing for
    a spelling are separated here rather than all inheriting the form's rank.

    The share depends on the *other* lemmas holding the same spelling, so
    unlike the frequency rollup this is not entirely self-contained: editing a
    competing sense's prominence changes this lemma's rank too. Adding or
    removing a sense of an existing word therefore warrants rescoring that
    word's other senses.

    Returns:
        The combined rank, capped at what absence from this corpus would cost,
        or None when this corpus ranks none of the lemma's forms.
    """
    # Imported lazily to avoid a circular import via storage.lexeme ->
    # storage.models.schema -> wordfreq.frequency package init.
    from storage.lexeme import get_lexeme
    from wordfreq.lexeme_frequency import get_lexeme_form_rank_shares

    lexeme = get_lexeme(session, lemma_id, "en")
    if lexeme is None:
        return None
    rank_shares = get_lexeme_form_rank_shares(session, lexeme, corpus_name)
    if not rank_shares:
        return None
    rank = combine_weighted_ranks(rank_shares, exponent)
    if rank is None:
        return None

    # Cap a share-scaled rank at what absence from this corpus would cost.
    # Dividing a rank by a small share can push it far past the corpus's own
    # size -- a 0.6% share of rank 734 in wiki_vital implies rank 151228, in a
    # corpus holding 6000 words. Beyond the unknown-rank floor the number says
    # nothing the corpus can support, and "this sense is effectively absent
    # here" is the honest reading. Mirrors the ceiling already applied to a
    # lemma the corpus genuinely does not list.
    return min(rank, get_corpus_unknown_rank(session, corpus_name))


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


def get_corpus_unknown_rank(session: Session, corpus_name: str) -> int:
    """The rank this corpus assigns to a lemma it does not list.

    This is also the ceiling :func:`get_lemma_corpus_rank` clamps to, so a
    caller wanting to explain a rank -- rather than merely report it -- can
    compare the two without reimplementing the cap.
    """
    cfg = _enabled_corpus_configs_by_name().get(corpus_name)
    if cfg is None:
        return _DEFAULT_UNKNOWN_RANK
    return _unknown_rank_for_corpus(cfg, get_corpus_size(session, corpus_name))


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


# The tier sources, in the order they contribute: (name, rank table, weight,
# rank when the source does not list the lemma). Shared by the single-lemma and
# bulk scoring paths so the two cannot drift apart.
_TIER_SOURCES: Tuple[Tuple[str, Dict[str, int], float, int], ...] = (
    ("cambridge_yle", YLE_TIER_RANKS, YLE_TIER_WEIGHT, YLE_UNKNOWN_RANK),
    ("cefr", CEFR_TIER_RANKS, CEFR_TIER_WEIGHT, CEFR_UNKNOWN_RANK),
    (
        "basic_english",
        BASIC_ENGLISH_TIER_RANKS,
        BASIC_ENGLISH_TIER_WEIGHT,
        BASIC_ENGLISH_UNKNOWN_RANK,
    ),
)


def _is_contested_spelling(session: Session, lemma_text: str, lemma_id: int) -> bool:
    """Whether another lemma holds this lemma's spelling.

    Only a contested spelling has a tier signal worth discounting: an
    uncontested one has no competing sense the listing could have been about.
    """
    return (
        session.query(Lemma.id).filter(Lemma.lemma_text == lemma_text, Lemma.id != lemma_id).first()
        is not None
    )


def _tier_contribution(
    tier_rank: Optional[int],
    unknown_rank: int,
    sense_prominence: Optional[str],
    is_contested: bool,
) -> int:
    """The rank a tier source contributes for one lemma.

    A lemma that is the only holder of its spelling keeps its tier rank in
    full: there is no competing sense for the listing to have been about, so
    the prominence label carries no information here and scaling by it would
    penalize ordinary monosemous words.

    For a contested spelling the tier rank is discounted by
    :data:`TIER_PROMINENCE_MULTIPLIERS`. A multiplier of 0 yields
    ``unknown_rank`` -- the sense is scored as absent from the list, which is
    how an untiered lemma is scored already.

    Args:
        tier_rank: Synthetic rank from the source's tier table, or None when
            this lemma has no row for that source.
        unknown_rank: The source's rank for a lemma it does not list.
        sense_prominence: ``Lemma.sense_prominence``; None is treated as the
            schema default.
        is_contested: Whether another lemma shares this lemma's spelling.
    """
    if tier_rank is None:
        return unknown_rank
    if not is_contested:
        return tier_rank

    multiplier = TIER_PROMINENCE_MULTIPLIERS.get(
        sense_prominence or SENSE_PROMINENCE_COMMON,
        TIER_PROMINENCE_MULTIPLIERS[SENSE_PROMINENCE_COMMON],
    )
    if multiplier <= 0.0:
        return unknown_rank
    if multiplier >= 1.0:
        return tier_rank

    # Scale the implied frequency, not the rank: ranks are not linear in
    # frequency. Under Zipf with s=1, keeping a fraction f of the frequency
    # multiplies the rank by 1/f. Never better than the raw tier rank, and
    # never worse than being unlisted.
    scaled = int(round(tier_rank / multiplier))
    return min(max(scaled, tier_rank), unknown_rank)


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

    scored_lemma = session.query(Lemma).filter(Lemma.id == lemma_id).first()
    sense_prominence = scored_lemma.sense_prominence if scored_lemma is not None else None
    is_contested = scored_lemma is not None and _is_contested_spelling(
        session, scored_lemma.lemma_text, lemma_id
    )

    for source, rank_table, weight, unknown_rank in _TIER_SOURCES:
        tier_rank = _tier_rank_for_lemma(tier_rows, lemma_id, source, rank_table)
        contributors.append(
            (
                weight,
                _tier_contribution(tier_rank, unknown_rank, sense_prominence, is_contested),
            )
        )

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

    # Spelling and prominence for every lemma, plus the set of spellings held
    # by more than one, read once rather than per lemma: the bulk path scores
    # the whole database and a query per lemma per tier source would dominate
    # its runtime.
    lemma_text_by_id: Dict[int, str] = {}
    prominence_by_lemma_id: Dict[int, str] = {}
    text_counts: Dict[str, int] = {}
    for row in session.query(Lemma.id, Lemma.lemma_text, Lemma.sense_prominence).all():
        lemma_text_by_id[row.id] = row.lemma_text
        prominence_by_lemma_id[row.id] = row.sense_prominence
        text_counts[row.lemma_text] = text_counts.get(row.lemma_text, 0) + 1
    contested_texts = {text for text, count in text_counts.items() if count > 1}

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
        # A tier rank is evidence about the spelling, not the sense. Where a
        # spelling is contested, _tier_contribution discounts it by this
        # lemma's prominence, so a rare sense stops inheriting the listing a
        # common one earned. See TIER_PROMINENCE_MULTIPLIERS.
        prominence = prominence_by_lemma_id.get(lemma_id)
        contested = lemma_text_by_id.get(lemma_id) in contested_texts

        for source, rank_table, weight, unknown_rank in _TIER_SOURCES:
            tier_rank = _tier_rank_for_lemma(tier_rows, lemma_id, source, rank_table)
            contributors.append(
                (
                    weight,
                    _tier_contribution(tier_rank, unknown_rank, prominence, contested),
                )
            )
            sources_used.add(source if tier_rank is not None else f"{source}_unknown")

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
    "TIER_PROMINENCE_MULTIPLIERS",
    "YLE_TIER_RANKS",
    "YLE_TIER_WEIGHT",
    "YLE_UNKNOWN_RANK",
    "calculate_lemma_combined_ranks",
    "clear_zipf_exponent_cache",
    "get_corpus_size",
    "get_corpus_unknown_rank",
    "get_corpus_zipf_exponent",
    "get_lemma_corpus_rank",
    "recalculate_lemma_rank",
]
