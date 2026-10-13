"""Fixed word sets that are placed as one unit.

This is the one source of truth for them. A cohort is a closed set -- the
days and months, every US state, every chemical element -- that owns its level
outright: whatever is stored at that level is the set, and nothing there is
ever offered to a new word by placement or held to a level's size range. A
set in the core is numbered around, not packed into.

A cohort is completed when it is defined, by hand or in the commit adding it,
so no code recognizes new members. A stored word at the level with some other
subtype is a data error, and checking for one is done by hand. A
member of the set taught earlier -- gold, in a general metals unit -- is not
at the level, so it is ordinary vocabulary there.

Only genuinely closed sets belong here. Animals or appliances have no last
member. Countries in general are not one either -- most never enter the app --
but the reviewed geography catalog (``words.difficulty.geography_catalog``)
is: its levels hold exactly the catalog, and a new country, nationality or
language joins by being added there. The family-relation tiers outside the
core are the same, owned by ``wordfreq.data.family_relations_sections``.
"""

from dataclasses import dataclass
from typing import Optional

from wordfreq.data.family_relations_sections import FAMILY_TIER_LEVELS


@dataclass(frozen=True)
class Cohort:
    """One closed word set and the level it owns."""

    name: str
    description: str
    #: The subtypes every member is stored under.
    pos_subtypes: tuple[str, ...]
    level: int


DAYS_AND_MONTHS = Cohort(
    "days_and_months", "the seven days of the week and twelve months", ("temporal_name",), 21
)
US_STATES = Cohort("us_states", "the fifty US states", ("region",), 240)
CHEMICAL_ELEMENTS = Cohort(
    "chemical_elements",
    "chemical elements not taught in an earlier unit",
    ("chemical_compound",),
    1100,
)

CONSTELLATIONS = Cohort("constellations", "the 88 IAU constellations", ("celestial_object",), 1055)

# The geography catalog's levels. Literal rather than read from the catalog,
# which lives above this package; a test holds the two in step.
CATALOG_COUNTRIES = Cohort(
    "catalog_countries", "the geography catalog's main countries", ("region",), 231
)
CATALOG_NATIONALITIES = Cohort(
    "catalog_nationalities",
    "origin adjectives and people of the catalog's main countries",
    ("nationality", "origin"),
    232,
)
CATALOG_LANGUAGES = Cohort(
    "catalog_languages",
    "languages of the catalog's main countries",
    ("communication_information",),
    233,
)
CATALOG_EXTENDED = Cohort(
    "catalog_extended",
    "the geography catalog's extended-tier countries and their words",
    ("region", "nationality", "origin", "communication_information"),
    1031,
)

# Tiers 1 and 2 sit in mixed core levels, so only tiers 3-5 own a level.
FAMILY_TIERS: tuple[Cohort, ...] = tuple(
    Cohort(
        f"family_tier_{tier}",
        f"family-relation terms of teaching tier {tier}",
        ("family_relation",),
        FAMILY_TIER_LEVELS[tier],
    )
    for tier in (3, 4, 5)
)

COHORTS: tuple[Cohort, ...] = (
    DAYS_AND_MONTHS,
    US_STATES,
    CHEMICAL_ELEMENTS,
    CONSTELLATIONS,
    CATALOG_COUNTRIES,
    CATALOG_NATIONALITIES,
    CATALOG_LANGUAGES,
    CATALOG_EXTENDED,
    *FAMILY_TIERS,
)

COHORT_LEVELS: frozenset[int] = frozenset(cohort.level for cohort in COHORTS)


def cohort_at(level: Optional[int]) -> Optional[Cohort]:
    """The cohort owning ``level``, if any."""
    for cohort in COHORTS:
        if cohort.level == level:
            return cohort
    return None
