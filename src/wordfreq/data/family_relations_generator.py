#!/usr/bin/env python3

"""
Family Relations Generator

This module manages family relation lemmas across different languages, handling
the complexity that family terms vary significantly between languages:
- Some languages gender cousins, siblings, or other relations
- Some languages distinguish older/younger siblings (Korean, Chinese, etc.)
- Some languages have different levels of formality for family terms

This generator uses a section-based approach where each family relation concept
(e.g., "sibling") is organized as a section containing multiple variants
(e.g., "sibling", "brother", "sister", "older brother", etc.), each with a
hardcoded GUID.

Each language can then select which variants from each section are applicable.

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
from wordfreq.storage.crud.lemma import add_lemma, get_lemma_by_guid
from wordfreq.storage.models.schema import Lemma
from wordfreq.storage.translation_helpers import LANGUAGE_HIERARCHY


@dataclass
class FamilyRelationVariant:
    """A single variant within a family relation section."""

    guid: str  # Hardcoded GUID (e.g., "N35_010")
    lemma_text: str  # English term (base form)
    definition: str  # English definition

    # Which languages this variant is applicable to
    # If None, applicable to all languages
    # If specified, only applicable to listed languages (always includes 'en')
    applicable_languages: Optional[Set[str]] = None

    # Optional notes about this variant
    notes: Optional[str] = None

    # Difficulty level (1-20 for Trakaido, or None for auto-assignment)
    difficulty_level: Optional[int] = None

    # Tags for additional categorization
    tags: Optional[List[str]] = None

    def get_excluded_languages(self, all_languages: List[str]) -> Set[str]:
        """
        Get the set of languages this variant should be excluded from.

        Returns languages that are not in applicable_languages (if specified).
        Always excludes 'en' from the exclusion list.
        """
        if self.applicable_languages is None:
            return set()

        excluded = set()
        for lang in all_languages:
            if lang not in self.applicable_languages and lang != "en":
                excluded.add(lang)

        return excluded


@dataclass
class FamilyRelationSection:
    """A section representing a family relation concept with multiple variants."""

    section_name: str  # Human-readable name (e.g., "Sibling")
    description: str  # Description of this section
    variants: List[FamilyRelationVariant]  # All variants in this section


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
            applicable_languages={"en", "zh", "ko", "vi"},
            difficulty_level=2,
            tags=["nuclear_family", "male", "age_distinguished"],
            notes="Distinct term in Chinese (哥哥/gēge), Korean (형/오빠), Vietnamese (anh)",
        ),
        FamilyRelationVariant(
            guid="N35_014",
            lemma_text="younger brother",
            definition="A male sibling who is younger than oneself",
            applicable_languages={"en", "zh", "ko", "vi"},
            difficulty_level=3,
            tags=["nuclear_family", "male", "age_distinguished"],
            notes="Distinct term in Chinese (弟弟/dìdi), Korean (남동생), Vietnamese (em trai)",
        ),
        FamilyRelationVariant(
            guid="N35_015",
            lemma_text="older sister",
            definition="A female sibling who is older than oneself",
            applicable_languages={"en", "zh", "ko", "vi"},
            difficulty_level=2,
            tags=["nuclear_family", "female", "age_distinguished"],
            notes="Distinct term in Chinese (姐姐/jiějie), Korean (누나/언니), Vietnamese (chị)",
        ),
        FamilyRelationVariant(
            guid="N35_016",
            lemma_text="younger sister",
            definition="A female sibling who is younger than oneself",
            applicable_languages={"en", "zh", "ko", "vi"},
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
            notes="Many languages distinguish maternal/paternal grandmother",
        ),
        FamilyRelationVariant(
            guid="N35_022",
            lemma_text="grandfather",
            definition="A father of one's parent",
            difficulty_level=2,
            tags=["extended_family", "male"],
            notes="Many languages distinguish maternal/paternal grandfather",
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
    description="Uncle term",
    variants=[
        FamilyRelationVariant(
            guid="N35_030",
            lemma_text="uncle",
            definition="A brother of one's parent, or the husband of one's aunt",
            difficulty_level=2,
            tags=["extended_family", "male"],
            notes="Many languages distinguish maternal/paternal uncle",
        ),
    ],
)

AUNT_SECTION = FamilyRelationSection(
    section_name="Aunt",
    description="Aunt term",
    variants=[
        FamilyRelationVariant(
            guid="N35_031",
            lemma_text="aunt",
            definition="A sister of one's parent, or the wife of one's uncle",
            difficulty_level=2,
            tags=["extended_family", "female"],
            notes="Many languages distinguish maternal/paternal aunt",
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
            notes="Gender-neutral in some languages (English, German, etc.); gendered in others",
        ),
        FamilyRelationVariant(
            guid="N35_041",
            lemma_text="male cousin",
            definition="A male child of one's aunt or uncle",
            applicable_languages={"en", "es", "pt", "it", "fr"},
            difficulty_level=3,
            tags=["extended_family", "male", "gendered"],
            notes="Spanish: primo, French: cousin (m), Italian: cugino, Portuguese: primo",
        ),
        FamilyRelationVariant(
            guid="N35_042",
            lemma_text="female cousin",
            definition="A female child of one's aunt or uncle",
            applicable_languages={"en", "es", "pt", "it", "fr"},
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
                        # We need to bypass add_lemma's auto-GUID generation
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
                                else None  # Simple string representation for now
                            ),
                            notes=variant.notes,
                        )
                        session.add(lemma)
                        session.flush()  # Ensure ID is assigned
                        stats["created"] += 1
                        if verbose:
                            print(f"    ✓ Created new lemma")

                    # Get languages to exclude
                    excluded_langs = variant.get_excluded_languages(LANGUAGE_HIERARCHY)

                    if excluded_langs:
                        if verbose:
                            print(f"    Excluding from: {', '.join(sorted(excluded_langs))}")

                        # Create difficulty overrides to exclude this variant from certain languages
                        for lang_code in excluded_langs:
                            override = add_difficulty_override(
                                session=session,
                                lemma_id=lemma.id,
                                language_code=lang_code,
                                difficulty_level=-1,  # -1 means exclude
                                notes=f"Not applicable in {lang_code}",
                            )
                            stats["overrides_created"] += 1

                    if variant.applicable_languages:
                        if verbose:
                            applicable = sorted(variant.applicable_languages)
                            print(f"    Applicable to: {', '.join(applicable)}")

                except Exception as e:
                    error_msg = f"Error processing {variant.lemma_text} ({variant.guid}): {str(e)}"
                    stats["errors"].append(error_msg)
                    print(f"    ✗ {error_msg}")
                    if verbose:
                        import traceback

                        traceback.print_exc()

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
        "--db-path",
        default="src/wordfreq/data/linguistics.sqlite",
        help="Path to the database file (default: src/wordfreq/data/linguistics.sqlite)",
    )

    args = parser.parse_args()

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

    return 0 if not stats["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
