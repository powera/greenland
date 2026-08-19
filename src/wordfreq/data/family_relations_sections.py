#!/usr/bin/env python3

"""
Family Relations Section Definitions

This module contains all family relation section and variant definitions.
Each section uses a 10-slot GUID range for organization and future expansion.

GUID Allocation (10 slots per section):
  N35_001-010: Parent
  N35_011-020: Child
  N35_021-030: Sibling
  N35_031-040: Half-sibling
  N35_041-050: Grandparent
  N35_051-060: Grandchild
  N35_061-070: Aunt/Uncle
  N35_071-080: Niece/Nephew
  N35_081-090: Cousin
  N35_091-100: Spouse
  N35_101-110: In-law
  N35_111-120: Step-parent
  N35_121-130: Step-child
  N35_131-140: Other relations

KNOWN ISSUE - these reservations are invisible to the GUID allocator.

storage.utils.guid.generate_guid works out the next N35 number from the lemmas
and tombstones that exist, and knows nothing about this file.  The ranges above
run to N35_140 while the live data reaches only N35_102, so the next
family-relation noun added through Barsukas is handed N35_103 - already spoken
for here, as are 104-107, 111, 112, 121-123 and 131.  Emitting that section
later would then hit the UNIQUE constraint on lemmas.guid.

Nothing enforces this yet; it is recorded rather than fixed because the fix is a
layering decision (teach storage about this module, or generate the reserved
words so they stop being reservations).  Until then, when adding a variant here,
check that its GUID is not already live.
"""

from dataclasses import dataclass
from typing import List, Optional, Set


@dataclass
class FamilyRelationVariant:
    """A single variant within a family relation section."""

    guid: str  # Hardcoded GUID (e.g., "N35_001") - must be unique number, no suffixes
    lemma_text: str  # English term (base form)
    definition: str  # English definition

    # Optional notes about this variant (usage patterns, NOT translations)
    notes: Optional[str] = None

    # Difficulty level (1-20 for Trakaido, or None for auto-assignment)
    difficulty_level: Optional[int] = None

    # Tags for additional categorization
    tags: Optional[List[str]] = None


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
            guid="N35_001",
            lemma_text="parent",
            definition="A mother or father",
            difficulty_level=1,
            tags=["nuclear_family", "gender_neutral"],
        ),
        FamilyRelationVariant(
            guid="N35_002",
            lemma_text="mother",
            definition="A female parent",
            difficulty_level=1,
            tags=["nuclear_family", "female"],
        ),
        FamilyRelationVariant(
            guid="N35_003",
            lemma_text="father",
            definition="A male parent",
            difficulty_level=1,
            tags=["nuclear_family", "male"],
        ),
    ],
)

CHILD_SECTION = FamilyRelationSection(
    section_name="Child",
    description="Child and related terms",
    variants=[
        FamilyRelationVariant(
            guid="N35_011",
            lemma_text="child",
            definition="A son or daughter",
            difficulty_level=1,
            tags=["nuclear_family", "gender_neutral"],
        ),
        FamilyRelationVariant(
            guid="N35_012",
            lemma_text="son",
            definition="A male child",
            difficulty_level=1,
            tags=["nuclear_family", "male"],
        ),
        FamilyRelationVariant(
            guid="N35_013",
            lemma_text="daughter",
            definition="A female child",
            difficulty_level=1,
            tags=["nuclear_family", "female"],
        ),
    ],
)

SIBLING_SECTION = FamilyRelationSection(
    section_name="Sibling",
    description="Sibling terms including gender-neutral, gendered, and age-distinguished variants",
    variants=[
        FamilyRelationVariant(
            guid="N35_021",
            lemma_text="sibling",
            definition="A brother or sister",
            difficulty_level=2,
            tags=["nuclear_family", "gender_neutral"],
            notes="Gender-neutral term; less common in some languages",
        ),
        FamilyRelationVariant(
            guid="N35_022",
            lemma_text="brother",
            definition="A male sibling",
            difficulty_level=1,
            tags=["nuclear_family", "male"],
            notes="General term; some languages only use age-distinguished variants",
        ),
        FamilyRelationVariant(
            guid="N35_023",
            lemma_text="sister",
            definition="A female sibling",
            difficulty_level=1,
            tags=["nuclear_family", "female"],
            notes="General term; some languages only use age-distinguished variants",
        ),
        FamilyRelationVariant(
            guid="N35_024",
            lemma_text="older brother",
            definition="A male sibling who is older than oneself",
            difficulty_level=2,
            tags=["nuclear_family", "male", "age_distinguished"],
            notes="Distinct term in Chinese, Korean, Vietnamese",
        ),
        FamilyRelationVariant(
            guid="N35_025",
            lemma_text="younger brother",
            definition="A male sibling who is younger than oneself",
            difficulty_level=3,
            tags=["nuclear_family", "male", "age_distinguished"],
            notes="Distinct term in Chinese, Korean, Vietnamese",
        ),
        FamilyRelationVariant(
            guid="N35_026",
            lemma_text="older sister",
            definition="A female sibling who is older than oneself",
            difficulty_level=2,
            tags=["nuclear_family", "female", "age_distinguished"],
            notes="Distinct term in Chinese, Korean, Vietnamese",
        ),
        FamilyRelationVariant(
            guid="N35_027",
            lemma_text="younger sister",
            definition="A female sibling who is younger than oneself",
            difficulty_level=3,
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
            guid="N35_031",
            lemma_text="half-brother",
            definition="A brother with whom one shares only one parent",
            difficulty_level=5,
            tags=["step_family", "male"],
        ),
        FamilyRelationVariant(
            guid="N35_032",
            lemma_text="half-sister",
            definition="A sister with whom one shares only one parent",
            difficulty_level=5,
            tags=["step_family", "female"],
        ),
    ],
)

GRANDPARENT_SECTION = FamilyRelationSection(
    section_name="Grandparent",
    description="Grandparent and related terms including maternal/paternal variants",
    variants=[
        FamilyRelationVariant(
            guid="N35_041",
            lemma_text="grandparent",
            definition="A parent of one's parent",
            difficulty_level=2,
            tags=["extended_family", "gender_neutral"],
        ),
        FamilyRelationVariant(
            guid="N35_042",
            lemma_text="grandmother",
            definition="A mother of one's parent",
            difficulty_level=2,
            tags=["extended_family", "female"],
            notes="General term; some languages distinguish maternal/paternal",
        ),
        FamilyRelationVariant(
            guid="N35_043",
            lemma_text="grandfather",
            definition="A father of one's parent",
            difficulty_level=2,
            tags=["extended_family", "male"],
            notes="General term; some languages distinguish maternal/paternal",
        ),
        FamilyRelationVariant(
            guid="N35_044",
            lemma_text="maternal grandmother",
            definition="The mother of one's mother",
            difficulty_level=3,
            tags=["extended_family", "female", "maternal"],
            notes="Distinct from paternal grandmother in some languages",
        ),
        FamilyRelationVariant(
            guid="N35_045",
            lemma_text="paternal grandmother",
            definition="The mother of one's father",
            difficulty_level=3,
            tags=["extended_family", "female", "paternal"],
            notes="Distinct from maternal grandmother in some languages",
        ),
        FamilyRelationVariant(
            guid="N35_046",
            lemma_text="maternal grandfather",
            definition="The father of one's mother",
            difficulty_level=3,
            tags=["extended_family", "male", "maternal"],
            notes="Distinct from paternal grandfather in some languages",
        ),
        FamilyRelationVariant(
            guid="N35_047",
            lemma_text="paternal grandfather",
            definition="The father of one's father",
            difficulty_level=3,
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
            guid="N35_051",
            lemma_text="grandchild",
            definition="A child of one's child",
            difficulty_level=3,
            tags=["extended_family", "gender_neutral"],
        ),
        FamilyRelationVariant(
            guid="N35_052",
            lemma_text="grandson",
            definition="A son of one's child",
            difficulty_level=3,
            tags=["extended_family", "male"],
        ),
        FamilyRelationVariant(
            guid="N35_053",
            lemma_text="granddaughter",
            definition="A daughter of one's child",
            difficulty_level=3,
            tags=["extended_family", "female"],
        ),
    ],
)

AUNT_UNCLE_SECTION = FamilyRelationSection(
    section_name="Aunt/Uncle",
    description="Aunt and uncle terms including maternal/paternal variants",
    variants=[
        FamilyRelationVariant(
            guid="N35_061",
            lemma_text="aunt",
            definition="A sister of one's parent, or the wife of one's uncle",
            difficulty_level=2,
            tags=["extended_family", "female"],
            notes="General term; many languages distinguish maternal/paternal",
        ),
        FamilyRelationVariant(
            guid="N35_062",
            lemma_text="uncle",
            definition="A brother of one's parent, or the husband of one's aunt",
            difficulty_level=2,
            tags=["extended_family", "male"],
            notes="General term; many languages distinguish maternal/paternal",
        ),
        FamilyRelationVariant(
            guid="N35_063",
            lemma_text="maternal aunt",
            definition="A sister of one's mother",
            difficulty_level=3,
            tags=["extended_family", "female", "maternal"],
            notes="Distinct from paternal aunt in some languages",
        ),
        FamilyRelationVariant(
            guid="N35_064",
            lemma_text="paternal aunt",
            definition="A sister of one's father",
            difficulty_level=3,
            tags=["extended_family", "female", "paternal"],
            notes="Distinct from maternal aunt in some languages",
        ),
        FamilyRelationVariant(
            guid="N35_065",
            lemma_text="maternal uncle",
            definition="A brother of one's mother",
            difficulty_level=3,
            tags=["extended_family", "male", "maternal"],
            notes="Distinct from paternal uncle in some languages",
        ),
        FamilyRelationVariant(
            guid="N35_066",
            lemma_text="paternal uncle",
            definition="A brother of one's father",
            difficulty_level=3,
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
            guid="N35_071",
            lemma_text="niece",
            definition="A daughter of one's sibling",
            difficulty_level=3,
            tags=["extended_family", "female"],
        ),
        FamilyRelationVariant(
            guid="N35_072",
            lemma_text="nephew",
            definition="A son of one's sibling",
            difficulty_level=3,
            tags=["extended_family", "male"],
        ),
    ],
)

COUSIN_SECTION = FamilyRelationSection(
    section_name="Cousin",
    description="Cousin terms including gender-neutral and gendered variants",
    variants=[
        FamilyRelationVariant(
            guid="N35_081",
            lemma_text="cousin",
            definition="A child of one's aunt or uncle",
            difficulty_level=2,
            tags=["extended_family", "gender_neutral"],
            notes="Gender-neutral in some languages; gendered in others",
        ),
        FamilyRelationVariant(
            guid="N35_082",
            lemma_text="male cousin",
            definition="A male child of one's aunt or uncle",
            difficulty_level=3,
            tags=["extended_family", "male", "gendered"],
            notes="Used in Romance languages",
        ),
        FamilyRelationVariant(
            guid="N35_083",
            lemma_text="female cousin",
            definition="A female child of one's aunt or uncle",
            difficulty_level=3,
            tags=["extended_family", "female", "gendered"],
            notes="Used in Romance languages",
        ),
    ],
)

SPOUSE_SECTION = FamilyRelationSection(
    section_name="Spouse",
    description="Spouse and related terms",
    variants=[
        FamilyRelationVariant(
            guid="N35_091",
            lemma_text="spouse",
            definition="A husband or wife",
            difficulty_level=2,
            tags=["marriage", "gender_neutral"],
        ),
        FamilyRelationVariant(
            guid="N35_092",
            lemma_text="husband",
            definition="A married man; a woman's male spouse",
            difficulty_level=1,
            tags=["marriage", "male"],
        ),
        FamilyRelationVariant(
            guid="N35_093",
            lemma_text="wife",
            definition="A married woman; a man's female spouse",
            difficulty_level=1,
            tags=["marriage", "female"],
        ),
        FamilyRelationVariant(
            guid="N35_094",
            lemma_text="partner",
            definition="A person in a romantic relationship (married or unmarried)",
            difficulty_level=2,
            tags=["marriage", "gender_neutral", "modern"],
            notes="Modern term; may not have direct equivalents in all languages",
        ),
    ],
)

IN_LAW_SECTION = FamilyRelationSection(
    section_name="In-law",
    description="In-law family terms",
    variants=[
        FamilyRelationVariant(
            guid="N35_101",
            lemma_text="parent-in-law",
            definition="A parent of one's spouse",
            difficulty_level=4,
            tags=["in_law", "gender_neutral"],
            notes="May be awkward in some languages",
        ),
        FamilyRelationVariant(
            guid="N35_102",
            lemma_text="mother-in-law",
            definition="The mother of one's spouse",
            difficulty_level=3,
            tags=["in_law", "female"],
        ),
        FamilyRelationVariant(
            guid="N35_103",
            lemma_text="father-in-law",
            definition="The father of one's spouse",
            difficulty_level=3,
            tags=["in_law", "male"],
        ),
        FamilyRelationVariant(
            guid="N35_104",
            lemma_text="son-in-law",
            definition="The husband of one's daughter",
            difficulty_level=4,
            tags=["in_law", "male"],
        ),
        FamilyRelationVariant(
            guid="N35_105",
            lemma_text="daughter-in-law",
            definition="The wife of one's son",
            difficulty_level=4,
            tags=["in_law", "female"],
        ),
        FamilyRelationVariant(
            guid="N35_106",
            lemma_text="brother-in-law",
            definition="The brother of one's spouse, or the husband of one's sibling",
            difficulty_level=4,
            tags=["in_law", "male"],
        ),
        FamilyRelationVariant(
            guid="N35_107",
            lemma_text="sister-in-law",
            definition="The sister of one's spouse, or the wife of one's sibling",
            difficulty_level=4,
            tags=["in_law", "female"],
        ),
    ],
)

STEP_PARENT_SECTION = FamilyRelationSection(
    section_name="Step-parent",
    description="Step-parent terms",
    variants=[
        FamilyRelationVariant(
            guid="N35_111",
            lemma_text="stepmother",
            definition="The wife of one's father who is not one's biological mother",
            difficulty_level=5,
            tags=["step_family", "female"],
        ),
        FamilyRelationVariant(
            guid="N35_112",
            lemma_text="stepfather",
            definition="The husband of one's mother who is not one's biological father",
            difficulty_level=5,
            tags=["step_family", "male"],
        ),
    ],
)

STEP_CHILD_SECTION = FamilyRelationSection(
    section_name="Step-child",
    description="Step-child and related terms",
    variants=[
        FamilyRelationVariant(
            guid="N35_121",
            lemma_text="stepchild",
            definition="A child of one's spouse from a previous relationship",
            difficulty_level=5,
            tags=["step_family", "gender_neutral"],
        ),
        FamilyRelationVariant(
            guid="N35_122",
            lemma_text="stepson",
            definition="A male child of one's spouse from a previous relationship",
            difficulty_level=5,
            tags=["step_family", "male"],
        ),
        FamilyRelationVariant(
            guid="N35_123",
            lemma_text="stepdaughter",
            definition="A female child of one's spouse from a previous relationship",
            difficulty_level=5,
            tags=["step_family", "female"],
        ),
    ],
)

OTHER_RELATIONS_SECTION = FamilyRelationSection(
    section_name="Other relations",
    description="Other family relations",
    variants=[
        FamilyRelationVariant(
            guid="N35_131",
            lemma_text="twin",
            definition="One of two children born to the same mother at the same time",
            difficulty_level=4,
            tags=["nuclear_family", "gender_neutral"],
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
    IN_LAW_SECTION,  # Combined all in-laws
    STEP_PARENT_SECTION,
    STEP_CHILD_SECTION,
    OTHER_RELATIONS_SECTION,
]

# Create a lookup map: section_name -> section
SECTION_MAP = {section.section_name: section for section in ALL_SECTIONS}
