"""Bootstrap defaults for TierDefinition rows.

The database is authoritative at runtime, but these constants supply the
initial set of tier names and ordinals so a fresh DB has a usable starting
state and importers can fall back to a known scale if their source's
TierDefinition rows are missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from storage.models.schema import TierDefinition


@dataclass(frozen=True)
class _TierSpec:
    tier_name: str
    ordinal: int
    display_name: str
    description: str


# Wordfreq rank-bucket tiers, applied to every source ``wordfreq_<corpus>``.
# Buckets use lower-exclusive / upper-inclusive ranges (rank 50 in r1-50; rank 51 in r51-100)
# so the boundary in the name names the highest rank in that bucket.
_WORDFREQ_BUCKETS: Tuple[Tuple[str, Optional[int], Optional[int]], ...] = (
    ("r1-50", 1, 50),
    ("r51-100", 51, 100),
    ("r101-200", 101, 200),
    ("r201-300", 201, 300),
    ("r301-500", 301, 500),
    ("r501-750", 501, 750),
    ("r751-1000", 751, 1000),
    ("r1001-1500", 1001, 1500),
    ("r1501-2000", 1501, 2000),
    ("r2001-3000", 2001, 3000),
    ("r3001-5000", 3001, 5000),
    ("r5001+", 5001, None),
)

WORDFREQ_TIER_SPECS: Tuple[_TierSpec, ...] = tuple(
    _TierSpec(
        tier_name=name,
        ordinal=i + 1,
        display_name=name,
        description=(
            f"Wordfreq corpus rank {lo}+" if hi is None else f"Wordfreq corpus rank {lo}-{hi}"
        ),
    )
    for i, (name, lo, hi) in enumerate(_WORDFREQ_BUCKETS)
)

WORDFREQ_SOURCES: Tuple[str, ...] = (
    "wordfreq_19th_books",
    "wordfreq_20th_books",
    "wordfreq_wiki_vital",
    "wordfreq_cooking",
)


def rank_to_wordfreq_tier_name(rank: Optional[int]) -> str:
    """Map an ordinal rank to a wordfreq tier-bucket name. Falls back to ``r5001+``."""
    if rank is None or rank <= 0:
        return "r5001+"
    for name, _lo, hi in _WORDFREQ_BUCKETS:
        if hi is None or rank <= hi:
            return name
    return "r5001+"


# source -> ordered list of tier specs (ordinal must be unique within a source)
BOOTSTRAP_TIER_DEFINITIONS: Dict[str, Tuple[_TierSpec, ...]] = {
    "cambridge_yle": (
        _TierSpec("starters", 1, "Starters", "Cambridge YLE Starters (pre-A1)"),
        _TierSpec("movers", 2, "Movers", "Cambridge YLE Movers (A1)"),
        _TierSpec("flyers", 3, "Flyers", "Cambridge YLE Flyers (A2)"),
    ),
    "cefr": (
        _TierSpec("A1", 1, "A1", "CEFR A1 (Breakthrough)"),
        _TierSpec("A2", 2, "A2", "CEFR A2 (Waystage)"),
        _TierSpec("B1", 3, "B1", "CEFR B1 (Threshold)"),
        _TierSpec("B2", 4, "B2", "CEFR B2 (Vantage)"),
        _TierSpec("C1", 5, "C1", "CEFR C1 (Effective Operational Proficiency)"),
        _TierSpec("C2", 6, "C2", "CEFR C2 (Mastery)"),
    ),
    **{source: WORDFREQ_TIER_SPECS for source in WORDFREQ_SOURCES},
}


def bootstrap_tier_definitions(session: Session, sources: List[str] | None = None) -> int:
    """Insert any missing TierDefinition rows for the given sources.

    Existing rows are left untouched (DB is authoritative). Returns the number
    of rows inserted. If ``sources`` is None, bootstraps every known source.
    """
    target_sources = sources if sources is not None else list(BOOTSTRAP_TIER_DEFINITIONS.keys())
    inserted = 0
    for source in target_sources:
        specs = BOOTSTRAP_TIER_DEFINITIONS.get(source)
        if specs is None:
            continue
        existing_names = {
            row.tier_name
            for row in session.query(TierDefinition).filter(TierDefinition.source == source).all()
        }
        for spec in specs:
            if spec.tier_name in existing_names:
                continue
            session.add(
                TierDefinition(
                    source=source,
                    tier_name=spec.tier_name,
                    ordinal=spec.ordinal,
                    display_name=spec.display_name,
                    description=spec.description,
                )
            )
            inserted += 1
    if inserted:
        session.commit()
    return inserted
