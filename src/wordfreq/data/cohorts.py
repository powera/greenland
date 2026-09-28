"""Fixed word sets that are placed as one unit.

This is the one source of truth for them. A cohort is a closed set -- the
days and months, every US state, every chemical element -- that owns its level
outright: whatever is stored at that level is the set, and nothing there is
ever moved by the rebalancer or offered to a new word by placement. A set in
the core is numbered around, not packed into.

A cohort is completed when it is defined, by hand or in the commit adding it,
so no code recognizes new members. A stored word at the level with some other
subtype is a data error, reported by ``curriculum_relevel``'s warnings. A
member of the set taught earlier -- gold, in a general metals unit -- is not
at the level, so it is ordinary vocabulary there.

Only genuinely closed sets belong here. Animals or appliances have no last
member, and even countries are not one: most never enter the app.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Cohort:
    """One closed word set and the level it owns."""

    name: str
    description: str
    #: The subtype every member is stored under.
    pos_subtype: str
    level: int


DAYS_AND_MONTHS = Cohort(
    "days_and_months", "the seven days of the week and twelve months", "temporal_name", 21
)
US_STATES = Cohort("us_states", "the fifty US states", "region", 240)
CHEMICAL_ELEMENTS = Cohort(
    "chemical_elements",
    "chemical elements not taught in an earlier unit",
    "chemical_compound",
    1100,
)

CONSTELLATIONS = Cohort("constellations", "the 88 IAU constellations", "celestial_object", 1055)

COHORTS: tuple[Cohort, ...] = (DAYS_AND_MONTHS, US_STATES, CHEMICAL_ELEMENTS, CONSTELLATIONS)

COHORT_LEVELS: frozenset[int] = frozenset(cohort.level for cohort in COHORTS)


def cohort_at(level: Optional[int]) -> Optional[Cohort]:
    """The cohort owning ``level``, if any."""
    for cohort in COHORTS:
        if cohort.level == level:
            return cohort
    return None
