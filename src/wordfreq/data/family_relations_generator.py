#!/usr/bin/env python3

"""
Family Relations Generator

This module manages family relation lemmas across different languages, handling
the complexity that family terms vary significantly between languages:
- Some languages gender cousins, siblings, or other relations
- Some languages distinguish older/younger siblings (Korean, Chinese, etc.)
- Some languages distinguish maternal/paternal grandparents, aunts, uncles

This generator uses:
1. Section-based approach: each family relation concept (e.g., "sibling") is
   organized as a section containing multiple variants
2. Hardcoded GUIDs: each variant has an explicit GUID (e.g., N35_013)
3. Explicit language configs: each language declares which variants it uses

Usage:
    PYTHONPATH=src python src/wordfreq/data/family_relations_generator.py --help
    PYTHONPATH=src python src/wordfreq/data/family_relations_generator.py --dry-run
    PYTHONPATH=src python src/wordfreq/data/family_relations_generator.py --apply
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Add parent directory to path for imports
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from wordfreq.storage.backend.config import BackendType, DataSourceConfig
from wordfreq.storage.backend.factory import create_session
from wordfreq.storage.crud.difficulty_override import add_difficulty_override
from wordfreq.storage.crud.lemma import get_lemma_by_guid
from wordfreq.storage.models.schema import Lemma
from wordfreq.storage.translation_helpers import LANGUAGE_HIERARCHY


@dataclass
class FamilyRelationVariant:
    """A single variant within a family relation section."""

    guid: str  # Hardcoded GUID (e.g., "N35_010")
    lemma_text: str  # English term (base form)
    definition: str  # English definition

    # Optional notes about this variant
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
# Each section represents a related group of family terms.
# GUIDs are hardcoded and must be unique across all sections.
# GUID range: N35_001 - N35_999 (family_relation subtype uses N35 prefix)
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
            guid="N35_004",
            lemma_text="child",
            definition="A son or daughter",
            difficulty_level=1,
            tags=["nuclear_family", "gender_neutral"],
        ),
        FamilyRelationVariant(
            guid="N35_005",
            lemma_text="son",
            definition="A male child",
            difficulty_level=1,
            tags=["nuclear_family", "male"],
        ),
        FamilyRelationVariant(
            guid="N35_006",
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
            guid="N35_010",
            lemma_text="sibling",
            definition="A brother or sister",
            difficulty_level=2,
            tags=["nuclear_family", "gender_neutral"],
            notes="Gender-neutral term; less common in some languages",
        ),
        FamilyRelationVariant(
            guid="N35_011",
            lemma_text="brother",
            definition="A male sibling",
            difficulty_level=1,
            tags=["nuclear_family", "male"],
            notes="General term; some languages only use age-distinguished variants",
        ),
        FamilyRelationVariant(
            guid="N35_012",
            lemma_text="sister",
            definition="A female sibling",
            difficulty_level=1,
            tags=["nuclear_family", "female"],
            notes="General term; some languages only use age-distinguished variants",
        ),
        FamilyRelationVariant(
            guid="N35_013",
            lemma_text="older brother",
            definition="A male sibling who is older than oneself",
            difficulty_level=2,
            tags=["nuclear_family", "male", "age_distinguished"],
            notes="Distinct term in Chinese (哥哥/gēge), Korean (형/오빠), Vietnamese (anh)",
        ),
        FamilyRelationVariant(
            guid="N35_014",
            lemma_text="younger brother",
            definition="A male sibling who is younger than oneself",
            difficulty_level=3,
            tags=["nuclear_family", "male", "age_distinguished"],
            notes="Distinct term in Chinese (弟弟/dìdi), Korean (남동생), Vietnamese (em trai)",
        ),
        FamilyRelationVariant(
            guid="N35_015",
            lemma_text="older sister",
            definition="A female sibling who is older than oneself",
            difficulty_level=2,
            tags=["nuclear_family", "female", "age_distinguished"],
            notes="Distinct term in Chinese (姐姐/jiějie), Korean (누나/언니), Vietnamese (chị)",
        ),
        FamilyRelationVariant(
            guid="N35_016",
            lemma_text="younger sister",
            definition="A female sibling who is younger than oneself",
            difficulty_level=3,
            tags=["nuclear_family", "female", "age_distinguished"],
            notes="Distinct term in Chinese (妹妹/mèimei), Korean (여동생), Vietnamese (em gái)",
        ),
    ],
)

GRANDPARENT_SECTION = FamilyRelationSection(
    section_name="Grandparent",
    description="Grandparent and related terms",
    variants=[
        FamilyRelationVariant(
            guid="N35_020",
            lemma_text="grandparent",
            definition="A parent of one's parent",
            difficulty_level=2,
            tags=["extended_family", "gender_neutral"],
        ),
        FamilyRelationVariant(
            guid="N35_021",
            lemma_text="grandmother",
            definition="A mother of one's parent",
            difficulty_level=2,
            tags=["extended_family", "female"],
            notes="General term; some languages distinguish maternal/paternal",
        ),
        FamilyRelationVariant(
            guid="N35_022",
            lemma_text="grandfather",
            definition="A father of one's parent",
            difficulty_level=2,
            tags=["extended_family", "male"],
            notes="General term; some languages distinguish maternal/paternal",
        ),
        FamilyRelationVariant(
            guid="N35_021a",
            lemma_text="maternal grandmother",
            definition="The mother of one's mother",
            difficulty_level=3,
            tags=["extended_family", "female", "maternal"],
            notes="Chinese: 外婆 (wàipó), distinct from paternal grandmother",
        ),
        FamilyRelationVariant(
            guid="N35_021b",
            lemma_text="paternal grandmother",
            definition="The mother of one's father",
            difficulty_level=3,
            tags=["extended_family", "female", "paternal"],
            notes="Chinese: 奶奶 (nǎinai), distinct from maternal grandmother",
        ),
        FamilyRelationVariant(
            guid="N35_022a",
            lemma_text="maternal grandfather",
            definition="The father of one's mother",
            difficulty_level=3,
            tags=["extended_family", "male", "maternal"],
            notes="Chinese: 外公 (wàigōng), distinct from paternal grandfather",
        ),
        FamilyRelationVariant(
            guid="N35_022b",
            lemma_text="paternal grandfather",
            definition="The father of one's father",
            difficulty_level=3,
            tags=["extended_family", "male", "paternal"],
            notes="Chinese: 爷爷 (yéye), distinct from paternal grandfather",
        ),
    ],
)

GRANDCHILD_SECTION = FamilyRelationSection(
    section_name="Grandchild",
    description="Grandchild and related terms",
    variants=[
        FamilyRelationVariant(
            guid="N35_023",
            lemma_text="grandchild",
            definition="A child of one's child",
            difficulty_level=3,
            tags=["extended_family", "gender_neutral"],
        ),
        FamilyRelationVariant(
            guid="N35_024",
            lemma_text="grandson",
            definition="A son of one's child",
            difficulty_level=3,
            tags=["extended_family", "male"],
        ),
        FamilyRelationVariant(
            guid="N35_025",
            lemma_text="granddaughter",
            definition="A daughter of one's child",
            difficulty_level=3,
            tags=["extended_family", "female"],
        ),
    ],
)

UNCLE_SECTION = FamilyRelationSection(
    section_name="Uncle",
    description="Uncle terms including general and maternal/paternal variants",
    variants=[
        FamilyRelationVariant(
            guid="N35_030",
            lemma_text="uncle",
            definition="A brother of one's parent, or the husband of one's aunt",
            difficulty_level=2,
            tags=["extended_family", "male"],
            notes="General term; many languages distinguish maternal/paternal",
        ),
        FamilyRelationVariant(
            guid="N35_030a",
            lemma_text="maternal uncle",
            definition="A brother of one's mother",
            difficulty_level=3,
            tags=["extended_family", "male", "maternal"],
            notes="Chinese: 舅舅 (jiùjiu), distinct from paternal uncle",
        ),
        FamilyRelationVariant(
            guid="N35_030b",
            lemma_text="paternal uncle",
            definition="A brother of one's father",
            difficulty_level=3,
            tags=["extended_family", "male", "paternal"],
            notes="Chinese: 伯伯 (bóbo) for older, 叔叔 (shūshu) for younger",
        ),
    ],
)

AUNT_SECTION = FamilyRelationSection(
    section_name="Aunt",
    description="Aunt terms including general and maternal/paternal variants",
    variants=[
        FamilyRelationVariant(
            guid="N35_031",
            lemma_text="aunt",
            definition="A sister of one's parent, or the wife of one's uncle",
            difficulty_level=2,
            tags=["extended_family", "female"],
            notes="General term; many languages distinguish maternal/paternal",
        ),
        FamilyRelationVariant(
            guid="N35_031a",
            lemma_text="maternal aunt",
            definition="A sister of one's mother",
            difficulty_level=3,
            tags=["extended_family", "female", "maternal"],
            notes="Chinese: 姨 (yí) or 姨妈 (yímā), distinct from paternal aunt",
        ),
        FamilyRelationVariant(
            guid="N35_031b",
            lemma_text="paternal aunt",
            definition="A sister of one's father",
            difficulty_level=3,
            tags=["extended_family", "female", "paternal"],
            notes="Chinese: 姑姑 (gūgu) or 姑妈 (gūmā), distinct from maternal aunt",
        ),
    ],
)

NEPHEW_SECTION = FamilyRelationSection(
    section_name="Nephew",
    description="Nephew term",
    variants=[
        FamilyRelationVariant(
            guid="N35_032",
            lemma_text="nephew",
            definition="A son of one's sibling",
            difficulty_level=3,
            tags=["extended_family", "male"],
        ),
    ],
)

NIECE_SECTION = FamilyRelationSection(
    section_name="Niece",
    description="Niece term",
    variants=[
        FamilyRelationVariant(
            guid="N35_033",
            lemma_text="niece",
            definition="A daughter of one's sibling",
            difficulty_level=3,
            tags=["extended_family", "female"],
        ),
    ],
)

COUSIN_SECTION = FamilyRelationSection(
    section_name="Cousin",
    description="Cousin terms including gender-neutral and gendered variants",
    variants=[
        FamilyRelationVariant(
            guid="N35_040",
            lemma_text="cousin",
            definition="A child of one's aunt or uncle",
            difficulty_level=2,
            tags=["extended_family", "gender_neutral"],
            notes="Gender-neutral in some languages (English, German, Chinese); gendered in others",
        ),
        FamilyRelationVariant(
            guid="N35_041",
            lemma_text="male cousin",
            definition="A male child of one's aunt or uncle",
            difficulty_level=3,
            tags=["extended_family", "male", "gendered"],
            notes="Spanish: primo, French: cousin (m), Italian: cugino, Portuguese: primo",
        ),
        FamilyRelationVariant(
            guid="N35_042",
            lemma_text="female cousin",
            definition="A female child of one's aunt or uncle",
            difficulty_level=3,
            tags=["extended_family", "female", "gendered"],
            notes="Spanish: prima, French: cousine, Italian: cugina, Portuguese: prima",
        ),
    ],
)

SPOUSE_SECTION = FamilyRelationSection(
    section_name="Spouse",
    description="Spouse and related terms",
    variants=[
        FamilyRelationVariant(
            guid="N35_050",
            lemma_text="spouse",
            definition="A husband or wife",
            difficulty_level=2,
            tags=["marriage", "gender_neutral"],
        ),
        FamilyRelationVariant(
            guid="N35_051",
            lemma_text="husband",
            definition="A married man; a woman's male spouse",
            difficulty_level=1,
            tags=["marriage", "male"],
        ),
        FamilyRelationVariant(
            guid="N35_052",
            lemma_text="wife",
            definition="A married woman; a man's female spouse",
            difficulty_level=1,
            tags=["marriage", "female"],
        ),
        FamilyRelationVariant(
            guid="N35_053",
            lemma_text="partner",
            definition="A person in a romantic relationship (married or unmarried)",
            difficulty_level=2,
            tags=["marriage", "gender_neutral", "modern"],
            notes="Modern term; may not have direct equivalents in all languages",
        ),
    ],
)

PARENT_IN_LAW_SECTION = FamilyRelationSection(
    section_name="Parent-in-law",
    description="Parent-in-law and related terms",
    variants=[
        FamilyRelationVariant(
            guid="N35_060",
            lemma_text="parent-in-law",
            definition="A parent of one's spouse",
            difficulty_level=4,
            tags=["in_law", "gender_neutral"],
        ),
        FamilyRelationVariant(
            guid="N35_061",
            lemma_text="mother-in-law",
            definition="The mother of one's spouse",
            difficulty_level=3,
            tags=["in_law", "female"],
        ),
        FamilyRelationVariant(
            guid="N35_062",
            lemma_text="father-in-law",
            definition="The father of one's spouse",
            difficulty_level=3,
            tags=["in_law", "male"],
        ),
    ],
)

CHILD_IN_LAW_SECTION = FamilyRelationSection(
    section_name="Child-in-law",
    description="Child-in-law terms",
    variants=[
        FamilyRelationVariant(
            guid="N35_063",
            lemma_text="son-in-law",
            definition="The husband of one's daughter",
            difficulty_level=4,
            tags=["in_law", "male"],
        ),
        FamilyRelationVariant(
            guid="N35_064",
            lemma_text="daughter-in-law",
            definition="The wife of one's son",
            difficulty_level=4,
            tags=["in_law", "female"],
        ),
    ],
)

SIBLING_IN_LAW_SECTION = FamilyRelationSection(
    section_name="Sibling-in-law",
    description="Sibling-in-law terms",
    variants=[
        FamilyRelationVariant(
            guid="N35_065",
            lemma_text="brother-in-law",
            definition="The brother of one's spouse, or the husband of one's sibling",
            difficulty_level=4,
            tags=["in_law", "male"],
        ),
        FamilyRelationVariant(
            guid="N35_066",
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
            guid="N35_070",
            lemma_text="stepmother",
            definition="The wife of one's father who is not one's biological mother",
            difficulty_level=5,
            tags=["step_family", "female"],
        ),
        FamilyRelationVariant(
            guid="N35_071",
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
            guid="N35_072",
            lemma_text="stepchild",
            definition="A child of one's spouse from a previous relationship",
            difficulty_level=5,
            tags=["step_family", "gender_neutral"],
        ),
        FamilyRelationVariant(
            guid="N35_073",
            lemma_text="stepson",
            definition="A male child of one's spouse from a previous relationship",
            difficulty_level=5,
            tags=["step_family", "male"],
        ),
        FamilyRelationVariant(
            guid="N35_074",
            lemma_text="stepdaughter",
            definition="A female child of one's spouse from a previous relationship",
            difficulty_level=5,
            tags=["step_family", "female"],
        ),
    ],
)

HALF_SIBLING_SECTION = FamilyRelationSection(
    section_name="Half-sibling",
    description="Half-sibling terms",
    variants=[
        FamilyRelationVariant(
            guid="N35_075",
            lemma_text="half-brother",
            definition="A brother with whom one shares only one parent",
            difficulty_level=5,
            tags=["step_family", "male"],
        ),
        FamilyRelationVariant(
            guid="N35_076",
            lemma_text="half-sister",
            definition="A sister with whom one shares only one parent",
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
            guid="N35_080",
            lemma_text="twin",
            definition="One of two children born to the same mother at the same time",
            difficulty_level=4,
            tags=["nuclear_family", "gender_neutral"],
        ),
    ],
)

# All sections in order
ALL_SECTIONS = [
    PARENT_SECTION,
    CHILD_SECTION,
    SIBLING_SECTION,
    GRANDPARENT_SECTION,
    GRANDCHILD_SECTION,
    UNCLE_SECTION,
    AUNT_SECTION,
    NEPHEW_SECTION,
    NIECE_SECTION,
    COUSIN_SECTION,
    SPOUSE_SECTION,
    PARENT_IN_LAW_SECTION,
    CHILD_IN_LAW_SECTION,
    SIBLING_IN_LAW_SECTION,
    STEP_PARENT_SECTION,
    STEP_CHILD_SECTION,
    HALF_SIBLING_SECTION,
    OTHER_RELATIONS_SECTION,
]

# Create a lookup map: section_name -> section
SECTION_MAP = {section.section_name: section for section in ALL_SECTIONS}


# =============================================================================
# LANGUAGE CONFIGURATIONS
# =============================================================================
# For each language, explicitly specify which GUIDs from each section to use.
# This makes it crystal clear which variants are applicable.
# =============================================================================

LANGUAGE_CONFIGS: Dict[str, Dict[str, List[str]]] = {
    "en": {
        # English uses all standard terms
        "Parent": ["N35_001", "N35_002", "N35_003"],
        "Child": ["N35_004", "N35_005", "N35_006"],
        "Sibling": ["N35_010", "N35_011", "N35_012"],  # sibling, brother, sister
        "Grandparent": [
            "N35_020",
            "N35_021",
            "N35_022",
            "N35_021a",
            "N35_021b",
            "N35_022a",
            "N35_022b",
        ],  # all variants
        "Grandchild": ["N35_023", "N35_024", "N35_025"],
        "Uncle": ["N35_030", "N35_030a", "N35_030b"],  # all variants
        "Aunt": ["N35_031", "N35_031a", "N35_031b"],  # all variants
        "Nephew": ["N35_032"],
        "Niece": ["N35_033"],
        "Cousin": ["N35_040"],  # gender-neutral only
        "Spouse": ["N35_050", "N35_051", "N35_052", "N35_053"],
        "Parent-in-law": ["N35_060", "N35_061", "N35_062"],
        "Child-in-law": ["N35_063", "N35_064"],
        "Sibling-in-law": ["N35_065", "N35_066"],
        "Step-parent": ["N35_070", "N35_071"],
        "Step-child": ["N35_072", "N35_073", "N35_074"],
        "Half-sibling": ["N35_075", "N35_076"],
        "Other relations": ["N35_080"],
    },
    "zh": {
        # Chinese distinguishes heavily by age and maternal/paternal
        "Parent": ["N35_002", "N35_003"],  # mother, father (no gender-neutral "parent")
        "Child": ["N35_005", "N35_006"],  # son, daughter (no "child")
        "Sibling": [
            "N35_013",
            "N35_014",
            "N35_015",
            "N35_016",
        ],  # age-distinguished only
        "Grandparent": [
            "N35_021a",
            "N35_021b",
            "N35_022a",
            "N35_022b",
        ],  # maternal/paternal only
        "Grandchild": ["N35_024", "N35_025"],  # grandson, granddaughter (no "grandchild")
        "Uncle": ["N35_030a", "N35_030b"],  # maternal/paternal only
        "Aunt": ["N35_031a", "N35_031b"],  # maternal/paternal only
        "Nephew": ["N35_032"],
        "Niece": ["N35_033"],
        "Cousin": ["N35_040"],  # gender-neutral
        "Spouse": ["N35_051", "N35_052"],  # husband, wife (no "spouse" or "partner")
        "Parent-in-law": ["N35_061", "N35_062"],  # mother/father-in-law (no "parent-in-law")
        "Child-in-law": ["N35_063", "N35_064"],
        "Sibling-in-law": ["N35_065", "N35_066"],
        "Step-parent": ["N35_070", "N35_071"],
        "Step-child": ["N35_073", "N35_074"],  # stepson, stepdaughter (no "stepchild")
        "Half-sibling": ["N35_075", "N35_076"],
        "Other relations": ["N35_080"],
    },
    "ko": {
        # Korean also uses age-distinguished siblings
        "Parent": ["N35_001", "N35_002", "N35_003"],
        "Child": ["N35_004", "N35_005", "N35_006"],
        "Sibling": [
            "N35_013",
            "N35_014",
            "N35_015",
            "N35_016",
        ],  # age-distinguished
        "Grandparent": ["N35_020", "N35_021", "N35_022"],
        "Grandchild": ["N35_023", "N35_024", "N35_025"],
        "Uncle": ["N35_030"],
        "Aunt": ["N35_031"],
        "Nephew": ["N35_032"],
        "Niece": ["N35_033"],
        "Cousin": ["N35_040"],
        "Spouse": ["N35_050", "N35_051", "N35_052", "N35_053"],
        "Parent-in-law": ["N35_060", "N35_061", "N35_062"],
        "Child-in-law": ["N35_063", "N35_064"],
        "Sibling-in-law": ["N35_065", "N35_066"],
        "Step-parent": ["N35_070", "N35_071"],
        "Step-child": ["N35_072", "N35_073", "N35_074"],
        "Half-sibling": ["N35_075", "N35_076"],
        "Other relations": ["N35_080"],
    },
    "vi": {
        # Vietnamese also uses age-distinguished siblings
        "Parent": ["N35_001", "N35_002", "N35_003"],
        "Child": ["N35_004", "N35_005", "N35_006"],
        "Sibling": [
            "N35_013",
            "N35_014",
            "N35_015",
            "N35_016",
        ],  # age-distinguished
        "Grandparent": ["N35_020", "N35_021", "N35_022"],
        "Grandchild": ["N35_023", "N35_024", "N35_025"],
        "Uncle": ["N35_030"],
        "Aunt": ["N35_031"],
        "Nephew": ["N35_032"],
        "Niece": ["N35_033"],
        "Cousin": ["N35_040"],
        "Spouse": ["N35_050", "N35_051", "N35_052", "N35_053"],
        "Parent-in-law": ["N35_060", "N35_061", "N35_062"],
        "Child-in-law": ["N35_063", "N35_064"],
        "Sibling-in-law": ["N35_065", "N35_066"],
        "Step-parent": ["N35_070", "N35_071"],
        "Step-child": ["N35_072", "N35_073", "N35_074"],
        "Half-sibling": ["N35_075", "N35_076"],
        "Other relations": ["N35_080"],
    },
    "es": {
        # Spanish uses gendered cousins
        "Parent": ["N35_001", "N35_002", "N35_003"],
        "Child": ["N35_004", "N35_005", "N35_006"],
        "Sibling": ["N35_010", "N35_011", "N35_012"],
        "Grandparent": ["N35_020", "N35_021", "N35_022"],
        "Grandchild": ["N35_023", "N35_024", "N35_025"],
        "Uncle": ["N35_030"],
        "Aunt": ["N35_031"],
        "Nephew": ["N35_032"],
        "Niece": ["N35_033"],
        "Cousin": ["N35_041", "N35_042"],  # primo, prima (gendered)
        "Spouse": ["N35_050", "N35_051", "N35_052", "N35_053"],
        "Parent-in-law": ["N35_060", "N35_061", "N35_062"],
        "Child-in-law": ["N35_063", "N35_064"],
        "Sibling-in-law": ["N35_065", "N35_066"],
        "Step-parent": ["N35_070", "N35_071"],
        "Step-child": ["N35_072", "N35_073", "N35_074"],
        "Half-sibling": ["N35_075", "N35_076"],
        "Other relations": ["N35_080"],
    },
    "fr": {
        # French uses gendered cousins
        "Parent": ["N35_001", "N35_002", "N35_003"],
        "Child": ["N35_004", "N35_005", "N35_006"],
        "Sibling": ["N35_010", "N35_011", "N35_012"],
        "Grandparent": ["N35_020", "N35_021", "N35_022"],
        "Grandchild": ["N35_023", "N35_024", "N35_025"],
        "Uncle": ["N35_030"],
        "Aunt": ["N35_031"],
        "Nephew": ["N35_032"],
        "Niece": ["N35_033"],
        "Cousin": ["N35_041", "N35_042"],  # cousin (m), cousine (gendered)
        "Spouse": ["N35_050", "N35_051", "N35_052", "N35_053"],
        "Parent-in-law": ["N35_060", "N35_061", "N35_062"],
        "Child-in-law": ["N35_063", "N35_064"],
        "Sibling-in-law": ["N35_065", "N35_066"],
        "Step-parent": ["N35_070", "N35_071"],
        "Step-child": ["N35_072", "N35_073", "N35_074"],
        "Half-sibling": ["N35_075", "N35_076"],
        "Other relations": ["N35_080"],
    },
    "pt": {
        # Portuguese uses gendered cousins
        "Parent": ["N35_001", "N35_002", "N35_003"],
        "Child": ["N35_004", "N35_005", "N35_006"],
        "Sibling": ["N35_010", "N35_011", "N35_012"],
        "Grandparent": ["N35_020", "N35_021", "N35_022"],
        "Grandchild": ["N35_023", "N35_024", "N35_025"],
        "Uncle": ["N35_030"],
        "Aunt": ["N35_031"],
        "Nephew": ["N35_032"],
        "Niece": ["N35_033"],
        "Cousin": ["N35_041", "N35_042"],  # primo, prima (gendered)
        "Spouse": ["N35_050", "N35_051", "N35_052", "N35_053"],
        "Parent-in-law": ["N35_060", "N35_061", "N35_062"],
        "Child-in-law": ["N35_063", "N35_064"],
        "Sibling-in-law": ["N35_065", "N35_066"],
        "Step-parent": ["N35_070", "N35_071"],
        "Step-child": ["N35_072", "N35_073", "N35_074"],
        "Half-sibling": ["N35_075", "N35_076"],
        "Other relations": ["N35_080"],
    },
    "it": {
        # Italian uses gendered cousins
        "Parent": ["N35_001", "N35_002", "N35_003"],
        "Child": ["N35_004", "N35_005", "N35_006"],
        "Sibling": ["N35_010", "N35_011", "N35_012"],
        "Grandparent": ["N35_020", "N35_021", "N35_022"],
        "Grandchild": ["N35_023", "N35_024", "N35_025"],
        "Uncle": ["N35_030"],
        "Aunt": ["N35_031"],
        "Nephew": ["N35_032"],
        "Niece": ["N35_033"],
        "Cousin": ["N35_041", "N35_042"],  # cugino, cugina (gendered)
        "Spouse": ["N35_050", "N35_051", "N35_052", "N35_053"],
        "Parent-in-law": ["N35_060", "N35_061", "N35_062"],
        "Child-in-law": ["N35_063", "N35_064"],
        "Sibling-in-law": ["N35_065", "N35_066"],
        "Step-parent": ["N35_070", "N35_071"],
        "Step-child": ["N35_072", "N35_073", "N35_074"],
        "Half-sibling": ["N35_075", "N35_076"],
        "Other relations": ["N35_080"],
    },
}

# Default config for languages not explicitly configured
# Uses all general terms, no special variants
DEFAULT_LANGUAGE_CONFIG = {
    "Parent": ["N35_001", "N35_002", "N35_003"],
    "Child": ["N35_004", "N35_005", "N35_006"],
    "Sibling": ["N35_010", "N35_011", "N35_012"],
    "Grandparent": ["N35_020", "N35_021", "N35_022"],
    "Grandchild": ["N35_023", "N35_024", "N35_025"],
    "Uncle": ["N35_030"],
    "Aunt": ["N35_031"],
    "Nephew": ["N35_032"],
    "Niece": ["N35_033"],
    "Cousin": ["N35_040"],
    "Spouse": ["N35_050", "N35_051", "N35_052", "N35_053"],
    "Parent-in-law": ["N35_060", "N35_061", "N35_062"],
    "Child-in-law": ["N35_063", "N35_064"],
    "Sibling-in-law": ["N35_065", "N35_066"],
    "Step-parent": ["N35_070", "N35_071"],
    "Step-child": ["N35_072", "N35_073", "N35_074"],
    "Half-sibling": ["N35_075", "N35_076"],
    "Other relations": ["N35_080"],
}


def get_language_config(lang_code: str) -> Dict[str, List[str]]:
    """Get the configuration for a language, or default if not configured."""
    return LANGUAGE_CONFIGS.get(lang_code, DEFAULT_LANGUAGE_CONFIG)


def get_excluded_guids_for_language(
    lang_code: str, all_sections: List[FamilyRelationSection]
) -> Set[str]:
    """
    Get all GUIDs that should be excluded for this language.

    Returns GUIDs that exist in sections but are not in the language's config.
    """
    config = get_language_config(lang_code)
    included_guids = set()

    for section_name, guids in config.items():
        included_guids.update(guids)

    # Get all GUIDs from all sections
    all_guids = set()
    for section in all_sections:
        all_guids.update(section.get_variant_guids())

    # Excluded = all GUIDs - included GUIDs
    return all_guids - included_guids


def generate_family_relations(
    config: DataSourceConfig, dry_run: bool = True, verbose: bool = False
) -> Dict[str, Any]:
    """
    Generate or update family relation lemmas in the database.

    Args:
        config: Database configuration
        dry_run: If True, don't commit changes
        verbose: If True, print detailed output

    Returns:
        Dictionary with statistics about the operation
    """
    stats: Dict[str, Any] = {
        "total_sections": len(ALL_SECTIONS),
        "total_variants": sum(len(section.variants) for section in ALL_SECTIONS),
        "created": 0,
        "existing": 0,
        "updated": 0,
        "overrides_created": 0,
        "errors": [],
    }

    session = create_session(config)
    try:
        # First pass: create/update all lemmas
        for section in ALL_SECTIONS:
            if verbose:
                print(f"\n{'=' * 70}")
                print(f"Section: {section.section_name}")
                print(f"  {section.description}")
                print(f"  Variants: {len(section.variants)}")
                print(f"{'=' * 70}")

            for variant in section.variants:
                try:
                    if verbose:
                        print(f"\n  Processing: {variant.lemma_text} (GUID: {variant.guid})")
                        print(f"    Definition: {variant.definition}")

                    # Check if lemma already exists with this GUID
                    existing = get_lemma_by_guid(session, variant.guid)

                    if existing:
                        # Lemma exists, check if we need to update it
                        needs_update = False
                        if existing.lemma_text != variant.lemma_text:
                            needs_update = True
                            if verbose:
                                print(
                                    f"    ! Lemma text changed: '{existing.lemma_text}' -> '{variant.lemma_text}'"
                                )
                        if existing.definition_text != variant.definition:
                            needs_update = True
                            if verbose:
                                print(
                                    f"    ! Definition changed: '{existing.definition_text}' -> '{variant.definition}'"
                                )

                        if needs_update:
                            existing.lemma_text = variant.lemma_text
                            existing.definition_text = variant.definition
                            if variant.difficulty_level is not None:
                                existing.difficulty_level = variant.difficulty_level
                            if variant.notes:
                                existing.notes = variant.notes
                            stats["updated"] += 1
                            if verbose:
                                print(f"    → Updated existing lemma")
                        else:
                            stats["existing"] += 1
                            if verbose:
                                print(f"    → Already exists (no changes)")

                        lemma = existing
                    else:
                        # Create new lemma with hardcoded GUID
                        lemma = Lemma(
                            guid=variant.guid,
                            lemma_text=variant.lemma_text,
                            definition_text=variant.definition,
                            pos_type="noun",
                            pos_subtype="family_relation",
                            difficulty_level=variant.difficulty_level,
                            tags=(
                                str(variant.tags)
                                if variant.tags
                                else None  # Simple string representation
                            ),
                            notes=variant.notes,
                        )
                        session.add(lemma)
                        session.flush()  # Ensure ID is assigned
                        stats["created"] += 1
                        if verbose:
                            print(f"    ✓ Created new lemma")

                except Exception as e:
                    error_msg = f"Error processing {variant.lemma_text} ({variant.guid}): {str(e)}"
                    stats["errors"].append(error_msg)
                    print(f"    ✗ {error_msg}")
                    if verbose:
                        import traceback

                        traceback.print_exc()

        # Second pass: create language-specific overrides
        if verbose:
            print(f"\n{'=' * 70}")
            print("Creating language-specific overrides")
            print(f"{'=' * 70}")

        for lang_code in LANGUAGE_HIERARCHY:
            excluded_guids = get_excluded_guids_for_language(lang_code, ALL_SECTIONS)

            if verbose and excluded_guids:
                print(f"\n  Language: {lang_code}")
                print(f"    Excluding {len(excluded_guids)} variants")

            for guid in excluded_guids:
                try:
                    existing_lemma = get_lemma_by_guid(session, guid)
                    if existing_lemma:
                        override = add_difficulty_override(
                            session=session,
                            lemma_id=existing_lemma.id,
                            language_code=lang_code,
                            difficulty_level=-1,  # -1 means exclude
                            notes=f"Not applicable in {lang_code}",
                        )
                        stats["overrides_created"] += 1
                except Exception as e:
                    error_msg = f"Error creating override for {guid} in {lang_code}: {str(e)}"
                    stats["errors"].append(error_msg)
                    if verbose:
                        print(f"    ✗ {error_msg}")

        if dry_run:
            print("\n" + "=" * 70)
            print("DRY RUN MODE - Rolling back changes")
            print("=" * 70)
            session.rollback()
        else:
            print("\n" + "=" * 70)
            print("APPLYING CHANGES - Committing to database")
            print("=" * 70)
            session.commit()
    finally:
        session.close()

    return stats


def print_summary(stats: Dict[str, Any]) -> None:
    """Print a summary of the operation."""
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total sections processed:   {stats['total_sections']}")
    print(f"Total variants processed:   {stats['total_variants']}")
    print(f"New lemmas created:         {stats['created']}")
    print(f"Existing lemmas found:      {stats['existing']}")
    print(f"Lemmas updated:             {stats['updated']}")
    print(f"Language overrides created: {stats['overrides_created']}")

    if stats["errors"]:
        print(f"\nErrors encountered: {len(stats['errors'])}")
        for error in stats["errors"]:
            print(f"  - {error}")
    else:
        print("\n✓ No errors encountered")
    print("=" * 70)


def print_language_report() -> None:
    """Print a report showing which variants each language uses."""
    print("\n" + "=" * 70)
    print("LANGUAGE CONFIGURATION REPORT")
    print("=" * 70)

    for lang_code in sorted(LANGUAGE_CONFIGS.keys()):
        config = LANGUAGE_CONFIGS[lang_code]
        total_variants = sum(len(guids) for guids in config.values())
        print(f"\n{lang_code.upper()}: {total_variants} variants")

        for section_name, guids in config.items():
            if guids:
                section = SECTION_MAP.get(section_name)
                if section:
                    variant_names = []
                    for guid in guids:
                        for variant in section.variants:
                            if variant.guid == guid:
                                variant_names.append(variant.lemma_text)
                                break
                    print(f"  {section_name}: {', '.join(variant_names)}")

    print("=" * 70)


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate or update family relation lemmas in the database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show what would be created (dry run)
  PYTHONPATH=src python src/wordfreq/data/family_relations_generator.py --dry-run

  # Show detailed output with dry run
  PYTHONPATH=src python src/wordfreq/data/family_relations_generator.py --dry-run --verbose

  # Show language configuration report
  PYTHONPATH=src python src/wordfreq/data/family_relations_generator.py --report

  # Actually create/update the lemmas
  PYTHONPATH=src python src/wordfreq/data/family_relations_generator.py --apply

  # Apply with verbose output
  PYTHONPATH=src python src/wordfreq/data/family_relations_generator.py --apply --verbose

  # Use custom database path
  PYTHONPATH=src python src/wordfreq/data/family_relations_generator.py --apply --db-path /path/to/db.sqlite
        """,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes (default if neither --dry-run nor --apply specified)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually apply the changes to the database",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print detailed output for each term",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print a report of which variants each language uses (no database changes)",
    )
    parser.add_argument(
        "--db-path",
        default="src/wordfreq/data/linguistics.sqlite",
        help="Path to the database file (default: src/wordfreq/data/linguistics.sqlite)",
    )

    args = parser.parse_args()

    # If report requested, just print and exit
    if args.report:
        print_language_report()
        return 0

    # Default to dry-run if neither flag specified
    if not args.dry_run and not args.apply:
        args.dry_run = True
        print("No mode specified, defaulting to --dry-run")

    # Create config
    config = DataSourceConfig(
        backend_type=BackendType.SQLITE,
        sqlite_path=args.db_path,
    )

    print("=" * 70)
    print("FAMILY RELATIONS GENERATOR")
    print("=" * 70)
    print(f"Database: {config.sqlite_path}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'APPLY CHANGES'}")
    print(f"Verbose: {args.verbose}")
    total_variants = sum(len(section.variants) for section in ALL_SECTIONS)
    print(f"Total sections: {len(ALL_SECTIONS)}")
    print(f"Total variants: {total_variants}")
    print(f"Configured languages: {len(LANGUAGE_CONFIGS)}")
    print("=" * 70)

    # Generate the family relations
    stats = generate_family_relations(
        config=config,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    # Print summary
    print_summary(stats)

    if args.dry_run:
        print("\n💡 To apply these changes, run with --apply flag")
        print("💡 To see language configurations, run with --report flag")

    return 0 if not stats["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
