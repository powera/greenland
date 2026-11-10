#!/usr/bin/env python3

"""
Family Relations Section Definitions

This module contains all family relation section and variant definitions.

GUIDs are the live lemmas' GUIDs (N35_*), not reservations.  They were once
allocated in 10-slot ranges per section, but the database was numbered
independently and the two drifted apart until almost every GUID here named a
different word.  storage.utils.guid.generate_guid works out the next N35 number
from the lemmas and tombstones that exist and knows nothing about this file,
so a GUID listed here before its lemma exists is a collision waiting to
happen.  Add a variant only once its lemma exists, and copy that lemma's GUID.

Consumers key on ``lemma_text`` and ``tier`` (``reports.curriculum_bands``);
the GUID is for cross-checking against the database.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set

# The curriculum level each family tier is taught at. Tier 1 (mother, father)
# comes at level 5, after the noun-only opening; tier 2 is at 18, and
# the remaining tiers are outside the core. Outside the core the last two
# digits match (102, 302, 1002: roughly B1, B2, C1) by convention only. A tier
# is a teaching order, not a level: per-language
# overrides then drop the terms a language does not use (older brother
# outside CJK, maternal/paternal aunt in most languages).
FAMILY_TIER_LEVELS: Dict[int, int] = {1: 5, 2: 18, 3: 102, 4: 302, 5: 1002}


@dataclass
class FamilyRelationVariant:
    """A single variant within a family relation section."""

    guid: str  # The live lemma's GUID (e.g., "N35_032")
    lemma_text: str  # English term (base form)
    definition: str  # English definition

    # Optional notes about this variant (usage patterns, NOT translations)
    notes: Optional[str] = None

    # Teaching tier (1-5), mapped to a level by FAMILY_TIER_LEVELS; None for
    # auto-assignment.
    tier: Optional[int] = None

    # Tags for additional categorization
    tags: Optional[List[str]] = None

    @property
    def curriculum_level(self) -> Optional[int]:
        """The curriculum level this variant's tier is taught at."""
        return FAMILY_TIER_LEVELS[self.tier] if self.tier is not None else None


@dataclass
class FamilyRelationSection:
    """A section representing a family relation concept with multiple variants."""

    section_name: str  # Human-readable name (e.g., "Sibling")
    description: str  # Description of this section
    variants: List[FamilyRelationVariant]  # All variants in this section

    def get_variant_guids(self) -> Set[str]:
        """Get all GUIDs in this section."""
        return {v.guid for v in self.variants}


# =============================================================================
# FAMILY RELATION SECTIONS
# =============================================================================

PARENT_SECTION = FamilyRelationSection(
    section_name="Parent",
    description="Parent and related terms",
    variants=[
        FamilyRelationVariant(
            guid="N35_099",
            lemma_text="parent",
            definition="A mother or father",
            tier=1,
            tags=["nuclear_family", "gender_neutral"],
        ),
        FamilyRelationVariant(
            guid="N35_032",
            lemma_text="mother",
            definition="A female parent",
            tier=1,
            tags=["nuclear_family", "female"],
        ),
        FamilyRelationVariant(
            guid="N35_033",
            lemma_text="father",
            definition="A male parent",
            tier=1,
            tags=["nuclear_family", "male"],
        ),
    ],
)

CHILD_SECTION = FamilyRelationSection(
    section_name="Child",
    description="Child and related terms",
    variants=[
        FamilyRelationVariant(
            guid="N35_100",
            lemma_text="child",
            definition="A son or daughter",
            tier=5,
            tags=["nuclear_family", "gender_neutral"],
            notes="Offspring sense; child (young person) is taught early as a human noun",
        ),
        FamilyRelationVariant(
            guid="N35_036",
            lemma_text="son",
            definition="A male child",
            tier=1,
            tags=["nuclear_family", "male"],
        ),
        FamilyRelationVariant(
            guid="N35_037",
            lemma_text="daughter",
            definition="A female child",
            tier=1,
            tags=["nuclear_family", "female"],
        ),
    ],
)

SIBLING_SECTION = FamilyRelationSection(
    section_name="Sibling",
    description="Sibling terms including gendered and age-distinguished variants",
    variants=[
        FamilyRelationVariant(
            guid="N35_034",
            lemma_text="brother",
            definition="A male sibling",
            tier=1,
            tags=["nuclear_family", "male"],
            notes="General term; some languages only use age-distinguished variants",
        ),
        FamilyRelationVariant(
            guid="N35_035",
            lemma_text="sister",
            definition="A female sibling",
            tier=1,
            tags=["nuclear_family", "female"],
            notes="General term; some languages only use age-distinguished variants",
        ),
        FamilyRelationVariant(
            guid="N35_077",
            lemma_text="older brother",
            definition="A male sibling who is older than oneself",
            tier=5,
            tags=["nuclear_family", "male", "age_distinguished"],
            notes="Distinct term in Chinese, Korean, Vietnamese",
        ),
        FamilyRelationVariant(
            guid="N35_078",
            lemma_text="younger brother",
            definition="A male sibling who is younger than oneself",
            tier=5,
            tags=["nuclear_family", "male", "age_distinguished"],
            notes="Distinct term in Chinese, Korean, Vietnamese",
        ),
        FamilyRelationVariant(
            guid="N35_079",
            lemma_text="older sister",
            definition="A female sibling who is older than oneself",
            tier=5,
            tags=["nuclear_family", "female", "age_distinguished"],
            notes="Distinct term in Chinese, Korean, Vietnamese",
        ),
        FamilyRelationVariant(
            guid="N35_080",
            lemma_text="younger sister",
            definition="A female sibling who is younger than oneself",
            tier=5,
            tags=["nuclear_family", "female", "age_distinguished"],
            notes="Distinct term in Chinese, Korean, Vietnamese",
        ),
    ],
)

HALF_SIBLING_SECTION = FamilyRelationSection(
    section_name="Half-sibling",
    description="Half-sibling terms",
    variants=[
        FamilyRelationVariant(
            guid="N35_104",
            lemma_text="half-brother",
            definition="A brother with whom one shares only one parent",
            tier=4,
            tags=["step_family", "male"],
        ),
        FamilyRelationVariant(
            guid="N35_107",
            lemma_text="half-sister",
            definition="A sister with whom one shares only one parent",
            tier=4,
            tags=["step_family", "female"],
        ),
    ],
)

GRANDPARENT_SECTION = FamilyRelationSection(
    section_name="Grandparent",
    description="Grandparent and related terms including maternal/paternal variants",
    variants=[
        FamilyRelationVariant(
            guid="N35_102",
            lemma_text="grandparent",
            definition="A parent of one's parent",
            tier=2,
            tags=["extended_family", "gender_neutral"],
        ),
        FamilyRelationVariant(
            guid="N35_044",
            lemma_text="grandmother",
            definition="A mother of one's parent",
            tier=2,
            tags=["extended_family", "female"],
            notes="General term; some languages distinguish maternal/paternal",
        ),
        FamilyRelationVariant(
            guid="N35_043",
            lemma_text="grandfather",
            definition="A father of one's parent",
            tier=2,
            tags=["extended_family", "male"],
            notes="General term; some languages distinguish maternal/paternal",
        ),
        FamilyRelationVariant(
            guid="N35_083",
            lemma_text="maternal grandmother",
            definition="The mother of one's mother",
            tier=5,
            tags=["extended_family", "female", "maternal"],
            notes="Distinct from paternal grandmother in some languages",
        ),
        FamilyRelationVariant(
            guid="N35_084",
            lemma_text="paternal grandmother",
            definition="The mother of one's father",
            tier=5,
            tags=["extended_family", "female", "paternal"],
            notes="Distinct from maternal grandmother in some languages",
        ),
        FamilyRelationVariant(
            guid="N35_081",
            lemma_text="maternal grandfather",
            definition="The father of one's mother",
            tier=5,
            tags=["extended_family", "male", "maternal"],
            notes="Distinct from paternal grandfather in some languages",
        ),
        FamilyRelationVariant(
            guid="N35_082",
            lemma_text="paternal grandfather",
            definition="The father of one's father",
            tier=5,
            tags=["extended_family", "male", "paternal"],
            notes="Distinct from maternal grandfather in some languages",
        ),
    ],
)

GRANDCHILD_SECTION = FamilyRelationSection(
    section_name="Grandchild",
    description="Grandchild and related terms",
    variants=[
        FamilyRelationVariant(
            guid="N35_101",
            lemma_text="grandchild",
            definition="A child of one's child",
            tier=3,
            tags=["extended_family", "gender_neutral"],
        ),
        FamilyRelationVariant(
            guid="N35_045",
            lemma_text="grandson",
            definition="A son of one's child",
            tier=3,
            tags=["extended_family", "male"],
        ),
        FamilyRelationVariant(
            guid="N35_046",
            lemma_text="granddaughter",
            definition="A daughter of one's child",
            tier=3,
            tags=["extended_family", "female"],
        ),
    ],
)

AUNT_UNCLE_SECTION = FamilyRelationSection(
    section_name="Aunt/Uncle",
    description="Aunt and uncle terms including maternal/paternal variants",
    variants=[
        FamilyRelationVariant(
            guid="N35_039",
            lemma_text="aunt",
            definition="A sister of one's parent, or the wife of one's uncle",
            tier=2,
            tags=["extended_family", "female"],
            notes="General term; many languages distinguish maternal/paternal",
        ),
        FamilyRelationVariant(
            guid="N35_038",
            lemma_text="uncle",
            definition="A brother of one's parent, or the husband of one's aunt",
            tier=2,
            tags=["extended_family", "male"],
            notes="General term; many languages distinguish maternal/paternal",
        ),
        FamilyRelationVariant(
            guid="N35_087",
            lemma_text="maternal aunt",
            definition="A sister of one's mother",
            tier=5,
            tags=["extended_family", "female", "maternal"],
            notes="Distinct from paternal aunt in some languages",
        ),
        FamilyRelationVariant(
            guid="N35_088",
            lemma_text="paternal aunt",
            definition="A sister of one's father",
            tier=5,
            tags=["extended_family", "female", "paternal"],
            notes="Distinct from maternal aunt in some languages",
        ),
        FamilyRelationVariant(
            guid="N35_085",
            lemma_text="maternal uncle",
            definition="A brother of one's mother",
            tier=5,
            tags=["extended_family", "male", "maternal"],
            notes="Distinct from paternal uncle in some languages",
        ),
        FamilyRelationVariant(
            guid="N35_086",
            lemma_text="paternal uncle",
            definition="A brother of one's father",
            tier=5,
            tags=["extended_family", "male", "paternal"],
            notes="Distinct from maternal uncle in some languages",
        ),
    ],
)

NIECE_NEPHEW_SECTION = FamilyRelationSection(
    section_name="Niece/Nephew",
    description="Niece and nephew terms",
    variants=[
        FamilyRelationVariant(
            guid="N35_050",
            lemma_text="niece",
            definition="A daughter of one's sibling",
            tier=3,
            tags=["extended_family", "female"],
        ),
        FamilyRelationVariant(
            guid="N35_049",
            lemma_text="nephew",
            definition="A son of one's sibling",
            tier=3,
            tags=["extended_family", "male"],
        ),
    ],
)

COUSIN_SECTION = FamilyRelationSection(
    section_name="Cousin",
    description="One cousin concept with language-specific gender variants",
    variants=[
        FamilyRelationVariant(
            guid="N35_076",
            lemma_text="cousin",
            definition="A child of one's aunt or uncle",
            tier=2,
            tags=["extended_family", "gender_neutral"],
            notes="Unspecified default; male/female words are gender variants of this lemma",
        ),
    ],
)

SPOUSE_SECTION = FamilyRelationSection(
    section_name="Spouse",
    description="Spouse and related terms",
    variants=[
        FamilyRelationVariant(
            guid="N35_042",
            lemma_text="spouse",
            definition="A husband or wife",
            tier=4,
            tags=["marriage", "gender_neutral"],
            notes="Gender-neutral and formal; husband and wife are the early words",
        ),
        FamilyRelationVariant(
            guid="N35_075",
            lemma_text="husband",
            definition="A married man; a woman's male spouse",
            tier=1,
            tags=["marriage", "male"],
        ),
        FamilyRelationVariant(
            guid="N35_071",
            lemma_text="wife",
            definition="A married woman; a man's female spouse",
            tier=1,
            tags=["marriage", "female"],
        ),
        FamilyRelationVariant(
            guid="N35_041",
            lemma_text="partner",
            definition="A person in a romantic relationship (married or unmarried)",
            tier=2,
            tags=["marriage", "gender_neutral", "modern"],
            notes="Modern term; may not have direct equivalents in all languages",
        ),
    ],
)

ROMANTIC_SECTION = FamilyRelationSection(
    section_name="Romantic",
    description="Engagement and unmarried romantic partners",
    variants=[
        FamilyRelationVariant(
            guid="N35_051",
            lemma_text="fiancé",
            definition="A man who is engaged to be married",
            tier=4,
            tags=["romantic", "male"],
        ),
        FamilyRelationVariant(
            guid="N35_052",
            lemma_text="fiancée",
            definition="A woman who is engaged to be married",
            tier=4,
            tags=["romantic", "female"],
        ),
        FamilyRelationVariant(
            guid="N35_053",
            lemma_text="boyfriend",
            definition="A man with whom one has a romantic relationship",
            tier=4,
            tags=["romantic", "male"],
        ),
        FamilyRelationVariant(
            guid="N35_054",
            lemma_text="girlfriend",
            definition="A woman with whom one has a romantic relationship",
            tier=4,
            tags=["romantic", "female"],
        ),
    ],
)

IN_LAW_SECTION = FamilyRelationSection(
    section_name="In-law",
    description="In-law family terms",
    variants=[
        FamilyRelationVariant(
            guid="N35_090",
            lemma_text="mother-in-law",
            definition="The mother of one's spouse",
            tier=3,
            tags=["in_law", "female"],
        ),
        FamilyRelationVariant(
            guid="N35_089",
            lemma_text="father-in-law",
            definition="The father of one's spouse",
            tier=3,
            tags=["in_law", "male"],
        ),
        FamilyRelationVariant(
            guid="N35_091",
            lemma_text="son-in-law",
            definition="The husband of one's daughter",
            tier=4,
            tags=["in_law", "male"],
        ),
        FamilyRelationVariant(
            guid="N35_092",
            lemma_text="daughter-in-law",
            definition="The wife of one's son",
            tier=4,
            tags=["in_law", "female"],
        ),
        FamilyRelationVariant(
            guid="N35_093",
            lemma_text="brother-in-law",
            definition="The brother of one's spouse, or the husband of one's sibling",
            tier=4,
            tags=["in_law", "male"],
        ),
        FamilyRelationVariant(
            guid="N35_094",
            lemma_text="sister-in-law",
            definition="The sister of one's spouse, or the wife of one's sibling",
            tier=4,
            tags=["in_law", "female"],
        ),
    ],
)

STEP_PARENT_SECTION = FamilyRelationSection(
    section_name="Step-parent",
    description="Step-parent terms",
    variants=[
        FamilyRelationVariant(
            guid="N35_096",
            lemma_text="stepmother",
            definition="The wife of one's father who is not one's biological mother",
            tier=4,
            tags=["step_family", "female"],
        ),
        FamilyRelationVariant(
            guid="N35_095",
            lemma_text="stepfather",
            definition="The husband of one's mother who is not one's biological father",
            tier=4,
            tags=["step_family", "male"],
        ),
    ],
)

STEP_CHILD_SECTION = FamilyRelationSection(
    section_name="Step-child",
    description="Step-child terms",
    variants=[
        FamilyRelationVariant(
            guid="N35_097",
            lemma_text="stepson",
            definition="A male child of one's spouse from a previous relationship",
            tier=4,
            tags=["step_family", "male"],
        ),
        FamilyRelationVariant(
            guid="N35_098",
            lemma_text="stepdaughter",
            definition="A female child of one's spouse from a previous relationship",
            tier=4,
            tags=["step_family", "female"],
        ),
    ],
)

# All sections in order (note: half-sibling is adjacent to sibling)
ALL_SECTIONS = [
    PARENT_SECTION,
    CHILD_SECTION,
    SIBLING_SECTION,
    HALF_SIBLING_SECTION,  # Adjacent to sibling
    GRANDPARENT_SECTION,
    GRANDCHILD_SECTION,
    AUNT_UNCLE_SECTION,  # Combined aunt/uncle
    NIECE_NEPHEW_SECTION,  # Combined niece/nephew
    COUSIN_SECTION,
    SPOUSE_SECTION,
    ROMANTIC_SECTION,
    IN_LAW_SECTION,  # Combined all in-laws
    STEP_PARENT_SECTION,
    STEP_CHILD_SECTION,
]

# Create a lookup map: section_name -> section
SECTION_MAP = {section.section_name: section for section in ALL_SECTIONS}
