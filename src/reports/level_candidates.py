"""Suggest curriculum levels for a word that has none yet.

This is placement, not rebalancing: ``curriculum_relevel`` reshuffles words
already in the curriculum, while this ranks the levels a *new* word -- a
pending import, usually -- could join, without moving anything. It reads
SQLite only and writes nothing.

A fixed set's level (``wordfreq.data.cohorts``) is never offered: a set is
completed when it is defined, so a new word does not join one.

Candidates come from, in order:

1. **Themes** (``wordfreq.data.curriculum_themes``): a word tagged with a
   theme, or of a theme's own subtype, or ranked far better in a theme's
   corpus than in general fiction, is offered that theme's topic levels. Only
   a tag overrides commonness: an untagged common word is general vocabulary
   even if a legal corpus uses it a lot.
2. **Subtype**: the core and named levels already holding the word's
   (pos, subtype). The core is offered only to a word with the evidence the
   rebalancer asks of core words (``curriculum_relevel.spill_from_core``);
   core levels are ordered by how close their words' ranks are to this one,
   since the core is sequential, and named levels by how many of the subtype
   they hold, since named numbers are not a teaching order.
3. **Curriculum theme** (``curriculum_relevel.THEME_BY_SUBTYPE``): when no
   level holds the subtype, named levels holding its broad theme.

A level at or over its band's maximum is still offered, but after the others,
and flagged full.

    GREENLAND_TEST_MODE=1 PYTHONPATH=src python src/reports/level_candidates.py --pending --limit 50
    GREENLAND_TEST_MODE=1 PYTHONPATH=src python src/reports/level_candidates.py --lemma-guid N14_001
"""

import argparse
import csv
import math
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session

import constants
from reports.curriculum_bands import (
    CORE_RULES,
    NAMED_RULES,
    NO_TIER,
    PRESERVED_LEVEL_MAX,
    TIER_ORDER,
    UNRANKED_SENTINEL,
    band_of,
    effective_rank,
    load_rank_evidence,
)
from reports.curriculum_relevel import (
    CORE_LOW_FREQUENCY_RANK,
    CORE_MAX_CEFR,
    CORE_RANK_CEILINGS,
    CORE_SUBTYPE_CAP,
    CORE_SUBTYPE_CAPS,
    theme_of,
)
from storage.backend import BackendType, DataSourceConfig, create_session
from storage.crud.lemma_tags import read_pending_import_tags, read_tags
from storage.models.imports import TARGET_KIND_LEMMA, PendingImport
from storage.models.schema import Corpus, ExternalLexemeAnnotation, Lemma, WordToken
from wordfreq.data.cohorts import COHORT_LEVELS
from wordfreq.data.curriculum_themes import (
    CURRICULUM_THEMES,
    THEMES_BY_NAME,
    CurriculumTheme,
    theme_for_subtype,
)

# Corpora standing for general vocabulary, against which a theme corpus rank
# is compared.
GENERAL_CORPORA = ("19th_books", "20th_books")
# A word must rank this many times better in a theme corpus than in general
# fiction to be read as a theme word ...
THEME_ENRICHMENT = 4.0
# ... and rank at least this well in the theme corpus itself.
THEME_MAX_CORPUS_RANK = 5000
# An untagged word ranked better than this is general vocabulary whatever its
# subtype or corpus profile; a tag still places it in its theme.
THEME_MIN_GENERAL_RANK = CORE_LOW_FREQUENCY_RANK
TIER_SOURCES = ("cefr", "cambridge_yle", "basic_english")
CORPUS_SOURCE_PREFIX = "wordfreq_"
DEFAULT_LIMIT = 3


@dataclass(frozen=True)
class IndexRow:
    """One placed lemma, as the index needs it."""

    lemma_id: int
    pos_type: str
    pos_subtype: Optional[str]
    level: int
    rank: int


@dataclass(frozen=True)
class PlacementQuery:
    """The word being placed. Built from a pending import or a lemma."""

    lemma_text: str
    pos_type: str
    pos_subtype: Optional[str]
    definition: str
    #: Effective rank: missing data reads as :data:`UNRANKED_SENTINEL`.
    rank: int
    tags: tuple[str, ...] = ()
    #: ``(source, tier_name)`` learner-list evidence.
    tiers: tuple[tuple[str, str], ...] = ()
    #: Corpus name -> this word's rank there.
    corpus_ranks: Mapping[str, int] = field(default_factory=dict)
    #: Leave this lemma out of the level counts, so a lemma already placed
    #: can be scored as if it were new.
    exclude_lemma_id: Optional[int] = None


@dataclass(frozen=True)
class LevelCandidate:
    """One suggested level."""

    level: int
    band: str
    reason: str
    level_size: int
    capacity: int
    #: Words of the query's (pos, subtype) already at this level.
    subtype_count: int = 0

    @property
    def full(self) -> bool:
        return self.level_size >= self.capacity


class LevelIndex:
    """Level sizes and subtype placement for every leveled lemma."""

    def __init__(self, rows: Iterable[IndexRow], corpus_unknown_ranks: Mapping[str, int]):
        self.rows_by_id: dict[int, IndexRow] = {}
        self.level_sizes: Counter[int] = Counter()
        self.subtype_levels: dict[tuple[str, str], Counter[int]] = defaultdict(Counter)
        self.subtype_level_ranks: dict[tuple[str, str, int], list[int]] = defaultdict(list)
        self.theme_levels: dict[str, Counter[int]] = defaultdict(Counter)
        self.core_subtype_counts: Counter[str] = Counter()
        self.corpus_unknown_ranks = dict(corpus_unknown_ranks)
        for row in rows:
            self.rows_by_id[row.lemma_id] = row
            subtype = row.pos_subtype or row.pos_type
            self.level_sizes[row.level] += 1
            self.subtype_levels[(row.pos_type, subtype)][row.level] += 1
            self.subtype_level_ranks[(row.pos_type, subtype, row.level)].append(row.rank)
            if band_of(row.level) == "named":
                self.theme_levels[theme_of(row.pos_type, row.pos_subtype)][row.level] += 1
            if band_of(row.level) == "core":
                self.core_subtype_counts[subtype] += 1

    def _excluded(self, query: PlacementQuery) -> Optional[IndexRow]:
        if query.exclude_lemma_id is None:
            return None
        return self.rows_by_id.get(query.exclude_lemma_id)

    def level_size(self, level: int, query: PlacementQuery) -> int:
        excluded = self._excluded(query)
        return self.level_sizes[level] - (1 if excluded and excluded.level == level else 0)

    def subtype_counts(self, query: PlacementQuery) -> Counter[int]:
        """Levels holding the query's (pos, subtype), without the query itself."""
        key = (query.pos_type, query.pos_subtype or query.pos_type)
        counts = Counter(self.subtype_levels.get(key, Counter()))
        excluded = self._excluded(query)
        if excluded and (excluded.pos_type, excluded.pos_subtype or excluded.pos_type) == key:
            counts[excluded.level] -= 1
        return +counts

    def peer_ranks(self, query: PlacementQuery, level: int) -> list[int]:
        key = (query.pos_type, query.pos_subtype or query.pos_type, level)
        ranks = list(self.subtype_level_ranks.get(key, []))
        excluded = self._excluded(query)
        if excluded and excluded.level == level and excluded.rank in ranks:
            ranks.remove(excluded.rank)
        return ranks

    def core_subtype_count(self, query: PlacementQuery) -> int:
        subtype = query.pos_subtype or query.pos_type
        count = self.core_subtype_counts[subtype]
        excluded = self._excluded(query)
        if (
            excluded
            and band_of(excluded.level) == "core"
            and (excluded.pos_subtype or excluded.pos_type) == subtype
        ):
            count -= 1
        return count

    def general_rank(self, query: PlacementQuery) -> int:
        """The query's best general-fiction rank; absence costs the corpus cap."""
        return min(
            query.corpus_ranks.get(name, self.corpus_unknown_ranks.get(name, UNRANKED_SENTINEL))
            for name in GENERAL_CORPORA
        )


def _capacity(level: int) -> int:
    band = band_of(level)
    if band == "core":
        return CORE_RULES.maximum
    # Named and topic units alike may run to a coherent unit's size.
    return NAMED_RULES.coherent_maximum


def _candidate(
    index: LevelIndex, query: PlacementQuery, level: int, reason: str, subtype_count: int = 0
) -> LevelCandidate:
    return LevelCandidate(
        level=level,
        band=band_of(level),
        reason=reason,
        level_size=index.level_size(level, query),
        capacity=_capacity(level),
        subtype_count=subtype_count,
    )


def detect_theme(query: PlacementQuery, index: LevelIndex) -> Optional[tuple[CurriculumTheme, str]]:
    """The query's theme and the evidence for it, if it has one."""
    for tag in query.tags:
        tagged = THEMES_BY_NAME.get(tag)
        if tagged is not None:
            return tagged, f"tagged {tag}"
    if query.rank < THEME_MIN_GENERAL_RANK:
        return None
    by_subtype = theme_for_subtype(query.pos_subtype)
    if by_subtype is not None:
        return by_subtype, f"{query.pos_subtype} is a {by_subtype.name} subtype"

    general = index.general_rank(query)
    best: Optional[tuple[float, CurriculumTheme, str, int]] = None
    for theme in CURRICULUM_THEMES:
        ranked = [
            (query.corpus_ranks[name], name) for name in theme.corpora if name in query.corpus_ranks
        ]
        if not ranked:
            continue
        theme_rank, corpus = min(ranked)
        enrichment = general / max(theme_rank, 1)
        if theme_rank <= THEME_MAX_CORPUS_RANK and enrichment >= THEME_ENRICHMENT:
            if best is None or enrichment > best[0]:
                best = (enrichment, theme, corpus, theme_rank)
    if best is None:
        return None
    enrichment, theme, corpus, theme_rank = best
    return theme, f"rank {theme_rank} in {corpus} vs {general} general ({enrichment:.1f}x)"


def core_evidence(query: PlacementQuery, index: LevelIndex) -> Optional[str]:
    """Why the query may not join the core, or None when it may.

    The rebalancer's rules for keeping a word in the core, applied to a new
    one; both the rank and the learner-list test apply to every subtype,
    since a new word has no current level to give it the benefit of the doubt.
    """
    subtype = query.pos_subtype or query.pos_type
    ceiling = CORE_RANK_CEILINGS.get(subtype, CORE_LOW_FREQUENCY_RANK)
    if query.rank >= ceiling:
        return f"rank {query.rank} not under {ceiling}"
    on_learner_list = any(
        source == "cambridge_yle"
        or (source == "cefr" and TIER_ORDER.get(tier, NO_TIER) <= TIER_ORDER[CORE_MAX_CEFR])
        for source, tier in query.tiers
    )
    if not on_learner_list:
        return f"not on YLE or CEFR {CORE_MAX_CEFR}-or-easier"
    cap = CORE_SUBTYPE_CAPS.get(subtype, CORE_SUBTYPE_CAP)
    if index.core_subtype_count(query) >= cap:
        return f"core already holds {cap} {subtype}"
    return None


def _log_distance(rank: int, peers: Sequence[int]) -> float:
    if not peers:
        return math.inf
    peer_median = statistics.median(math.log2(max(peer, 1)) for peer in peers)
    return abs(math.log2(max(rank, 1)) - peer_median)


def _subtype_candidates(
    query: PlacementQuery, index: LevelIndex, allow_core: bool
) -> list[LevelCandidate]:
    counts = index.subtype_counts(query)
    subtype = query.pos_subtype or query.pos_type
    core_levels = [
        level
        for level in counts
        if band_of(level) == "core" and level > PRESERVED_LEVEL_MAX and allow_core
    ]
    named_levels = [level for level in counts if band_of(level) == "named"]

    core = sorted(
        (
            _candidate(
                index,
                query,
                level,
                f"core level with {counts[level]} {subtype}; ranks nearest",
                counts[level],
            )
            for level in core_levels
        ),
        key=lambda item: (
            item.full,
            _log_distance(query.rank, index.peer_ranks(query, item.level)),
            item.level,
        ),
    )
    named = sorted(
        (
            _candidate(
                index, query, level, f"named unit with {counts[level]} {subtype}", counts[level]
            )
            for level in named_levels
        ),
        key=lambda item: (item.full, -item.subtype_count, item.level),
    )
    return [*core, *named]


def _theme_fallback(query: PlacementQuery, index: LevelIndex) -> list[LevelCandidate]:
    theme = theme_of(query.pos_type, query.pos_subtype)
    counts = index.theme_levels.get(theme, Counter())
    return sorted(
        (
            _candidate(index, query, level, f"no unit holds the subtype; same theme {theme}")
            for level in counts
        ),
        key=lambda item: (item.full, -counts[item.level], item.level),
    )


def level_candidates(
    query: PlacementQuery, index: LevelIndex, *, limit: int = DEFAULT_LIMIT
) -> list[LevelCandidate]:
    """Rank the levels ``query`` could join, best first."""
    candidates: list[LevelCandidate] = []
    theme_match = detect_theme(query, index)
    if theme_match is not None:
        theme, evidence = theme_match
        candidates.extend(
            _candidate(index, query, level, f"theme {theme.name}: {evidence}")
            for level in theme.levels
        )

    core_block = core_evidence(query, index)
    general = _subtype_candidates(query, index, allow_core=core_block is None)
    if not general:
        general = _theme_fallback(query, index)
    candidates.extend(general)

    seen: set[int] = set()
    unique: list[LevelCandidate] = []
    for candidate in candidates:
        if candidate.level not in seen and candidate.level not in COHORT_LEVELS:
            seen.add(candidate.level)
            unique.append(candidate)
    return unique[:limit]


# -- Loading from the database ----------------------------------------------


def load_level_index(session: Session) -> LevelIndex:
    """Index every lemma with a positive level."""
    lemmas = session.query(Lemma).filter(Lemma.guid.isnot(None), Lemma.difficulty_level > 0).all()
    evidence = load_rank_evidence(session, lemmas)
    rows = [
        IndexRow(
            lemma_id=lemma.id,
            pos_type=lemma.pos_type,
            pos_subtype=lemma.pos_subtype,
            level=int(lemma.difficulty_level or 0),
            rank=effective_rank(lemma, evidence),
        )
        for lemma in lemmas
    ]
    unknown = {
        corpus.name: int(corpus.max_unknown_rank or UNRANKED_SENTINEL)
        for corpus in session.query(Corpus).all()
    }
    return LevelIndex(rows, unknown)


def token_evidence(
    session: Session, lemma_text: str
) -> tuple[tuple[tuple[str, str], ...], dict[str, int]]:
    """Learner-list tiers and per-corpus ranks for an English surface form."""
    token = (
        session.query(WordToken)
        .filter(WordToken.token == lemma_text.casefold(), WordToken.language_code == "en")
        .first()
    )
    if token is None:
        return (), {}
    tiers: list[tuple[str, str]] = []
    corpus_ranks: dict[str, int] = {}
    for annotation in session.query(ExternalLexemeAnnotation).filter(
        ExternalLexemeAnnotation.word_token_id == token.id
    ):
        if annotation.source in TIER_SOURCES:
            tiers.append((annotation.source, annotation.tier_name))
        elif (
            annotation.source.startswith(CORPUS_SOURCE_PREFIX)
            and annotation.ordinal_rank is not None
        ):
            corpus = annotation.source[len(CORPUS_SOURCE_PREFIX) :]
            corpus_ranks[corpus] = min(
                corpus_ranks.get(corpus, annotation.ordinal_rank), annotation.ordinal_rank
            )
    return tuple(sorted(tiers)), corpus_ranks


def query_for_pending(session: Session, pending: PendingImport) -> PlacementQuery:
    """A placement query for a staged term."""
    tiers, corpus_ranks = token_evidence(session, pending.english_word)
    return PlacementQuery(
        lemma_text=pending.english_word,
        pos_type=pending.pos_type or "noun",
        pos_subtype=pending.pos_subtype,
        definition=pending.definition,
        rank=int(pending.frequency_rank or UNRANKED_SENTINEL),
        tags=tuple(read_pending_import_tags(pending)),
        tiers=tiers,
        corpus_ranks=corpus_ranks,
    )


def query_for_lemma(session: Session, lemma: Lemma, index: LevelIndex) -> PlacementQuery:
    """A placement query for a stored lemma, scored as if it were new."""
    tiers, corpus_ranks = token_evidence(session, lemma.lemma_text)
    row = index.rows_by_id.get(lemma.id)
    return PlacementQuery(
        lemma_text=lemma.lemma_text,
        pos_type=lemma.pos_type,
        pos_subtype=lemma.pos_subtype,
        definition=lemma.definition_text,
        rank=row.rank if row else int(lemma.frequency_rank or UNRANKED_SENTINEL),
        tags=tuple(read_tags(lemma)),
        tiers=tiers,
        corpus_ranks=corpus_ranks,
        exclude_lemma_id=lemma.id,
    )


def _format(candidates: Sequence[LevelCandidate]) -> str:
    return " | ".join(
        f"{item.level}{' (full)' if item.full else ''}: {item.reason}" for item in candidates
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--pending", action="store_true", help="Every pending lemma import")
    target.add_argument("--pending-id", type=int, help="One pending import")
    target.add_argument("--lemma-guid", help="A stored lemma, scored as if new")
    parser.add_argument("--limit", type=int, help="Most pending rows to score")
    parser.add_argument("--candidates", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--output", type=Path, help="TSV path (default: stdout)")
    parser.add_argument("--db-path", type=Path, default=Path(constants.WORDFREQ_DB_PATH))
    args = parser.parse_args()

    config = DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=str(args.db_path))
    session = create_session(config)
    index = load_level_index(session)

    rows: list[tuple[str, str, str, int, str]] = []
    if args.lemma_guid:
        lemma = session.query(Lemma).filter(Lemma.guid == args.lemma_guid).one()
        query = query_for_lemma(session, lemma, index)
        found = level_candidates(query, index, limit=args.candidates)
        rows.append(
            (lemma.guid or "", lemma.lemma_text, str(lemma.pos_subtype), query.rank, _format(found))
        )
    else:
        pending_query = session.query(PendingImport).filter(
            PendingImport.target_kind == TARGET_KIND_LEMMA
        )
        if args.pending_id is not None:
            pending_query = pending_query.filter(PendingImport.id == args.pending_id)
        pending_query = pending_query.order_by(PendingImport.id)
        if args.limit:
            pending_query = pending_query.limit(args.limit)
        for pending in pending_query:
            query = query_for_pending(session, pending)
            found = level_candidates(query, index, limit=args.candidates)
            rows.append(
                (
                    str(pending.id),
                    pending.english_word,
                    str(pending.pos_subtype),
                    query.rank,
                    _format(found),
                )
            )

    handle = args.output.open("w", encoding="utf-8", newline="") if args.output else sys.stdout
    writer = csv.writer(handle, delimiter="\t")
    writer.writerow(["id", "word", "subtype", "rank", "candidates"])
    writer.writerows(rows)
    if args.output:
        handle.close()


if __name__ == "__main__":
    main()
