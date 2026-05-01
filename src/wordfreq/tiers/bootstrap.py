"""Bootstrap defaults for TierDefinition rows.

The database is authoritative at runtime, but these constants supply the
initial set of tier names and ordinals so a fresh DB has a usable starting
state and importers can fall back to a known scale if their source's
TierDefinition rows are missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from sqlalchemy.orm import Session

from storage.models.schema import TierDefinition


@dataclass(frozen=True)
class _TierSpec:
    tier_name: str
    ordinal: int
    display_name: str
    description: str


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
