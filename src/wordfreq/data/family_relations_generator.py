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
2. Hardcoded GUIDs: each variant has an explicit GUID with unique number (10-slot ranges)
3. Explicit language configs: each language declares which variants it uses
4. Language groupings: reduce duplication for language families (Romance, Germanic, etc.)

Usage:
    PYTHONPATH=src python src/wordfreq/data/family_relations_generator.py --help
    PYTHONPATH=src python src/wordfreq/data/family_relations_generator.py --dry-run
    PYTHONPATH=src python src/wordfreq/data/family_relations_generator.py --apply
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

# Add parent directory to path for imports
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from wordfreq.data.family_relations_sections import (
    ALL_SECTIONS,
    SECTION_MAP,
    FamilyRelationSection,
)
from wordfreq.storage.backend.config import BackendType, DataSourceConfig
from wordfreq.storage.backend.factory import create_session
from wordfreq.storage.crud.difficulty_override import add_difficulty_override
from wordfreq.storage.crud.lemma import get_lemma_by_guid
from wordfreq.storage.models.schema import Lemma
from wordfreq.storage.translation_helpers import LANGUAGE_HIERARCHY


# =============================================================================
# LANGUAGE GROUPINGS
# =============================================================================
# Language groups share similar family relation structures.
# This reduces duplication in language configurations.
# =============================================================================

# Romance languages typically gender cousins but use general terms for siblings
ROMANCE_BASE_CONFIG: Dict[str, List[str]] = {
    "Parent": ["N35_001", "N35_002", "N35_003"],
    "Child": ["N35_011", "N35_012", "N35_013"],
    "Sibling": ["N35_021", "N35_022", "N35_023"],
    "Half-sibling": ["N35_031", "N35_032"],
    "Grandparent": ["N35_041", "N35_042", "N35_043"],
    "Grandchild": ["N35_051", "N35_052", "N35_053"],
    "Aunt/Uncle": ["N35_061", "N35_062"],
    "Niece/Nephew": ["N35_071", "N35_072"],
    "Cousin": ["N35_082", "N35_083"],  # Gendered cousins (primo/prima)
    "Spouse": ["N35_091", "N35_092", "N35_093", "N35_094"],
    "In-law": ["N35_101", "N35_102", "N35_103", "N35_104", "N35_105", "N35_106", "N35_107"],
    "Step-parent": ["N35_111", "N35_112"],
    "Step-child": ["N35_121", "N35_122", "N35_123"],
    "Other relations": ["N35_131"],
}

# Germanic languages (German, Dutch, Swedish) - similar to Romance
GERMANIC_BASE_CONFIG: Dict[str, List[str]] = {
    "Parent": ["N35_001", "N35_002", "N35_003"],
    "Child": ["N35_011", "N35_012", "N35_013"],
    "Sibling": ["N35_021", "N35_022", "N35_023"],
    "Half-sibling": ["N35_031", "N35_032"],
    "Grandparent": ["N35_041", "N35_042", "N35_043"],
    "Grandchild": ["N35_051", "N35_052", "N35_053"],
    "Aunt/Uncle": ["N35_061", "N35_062"],
    "Niece/Nephew": ["N35_071", "N35_072"],
    "Cousin": ["N35_082", "N35_083"],  # Gendered cousins
    "Spouse": ["N35_091", "N35_092", "N35_093", "N35_094"],
    "In-law": ["N35_101", "N35_102", "N35_103", "N35_104", "N35_105", "N35_106", "N35_107"],
    "Step-parent": ["N35_111", "N35_112"],
    "Step-child": ["N35_121", "N35_122", "N35_123"],
    "Other relations": ["N35_131"],
}


# =============================================================================
# LANGUAGE CONFIGURATIONS
# =============================================================================
# For each language, explicitly specify which GUIDs from each section to use.
# Languages can inherit from a base config (ROMANCE_BASE_CONFIG, etc.) or
# define their own configuration.
# =============================================================================

LANGUAGE_CONFIGS: Dict[str, Dict[str, List[str]]] = {
    "en": {
        # English uses all standard terms including maternal/paternal variants
        "Parent": ["N35_001", "N35_002", "N35_003"],
        "Child": ["N35_011", "N35_012", "N35_013"],
        "Sibling": ["N35_021", "N35_022", "N35_023"],  # sibling, brother, sister
        "Half-sibling": ["N35_031", "N35_032"],
        "Grandparent": [
            "N35_041",
            "N35_042",
            "N35_043",
            "N35_044",
            "N35_045",
            "N35_046",
            "N35_047",
        ],  # all variants
        "Grandchild": ["N35_051", "N35_052", "N35_053"],
        "Aunt/Uncle": [
            "N35_061",
            "N35_062",
            "N35_063",
            "N35_064",
            "N35_065",
            "N35_066",
        ],  # all variants
        "Niece/Nephew": ["N35_071", "N35_072"],
        "Cousin": ["N35_081"],  # gender-neutral only
        "Spouse": ["N35_091", "N35_092", "N35_093", "N35_094"],
        "In-law": ["N35_101", "N35_102", "N35_103", "N35_104", "N35_105", "N35_106", "N35_107"],
        "Step-parent": ["N35_111", "N35_112"],
        "Step-child": ["N35_121", "N35_122", "N35_123"],
        "Other relations": ["N35_131"],
    },
    "zh": {
        # Chinese distinguishes heavily by age and maternal/paternal
        "Parent": ["N35_002", "N35_003"],  # mother, father (no gender-neutral "parent")
        "Child": ["N35_012", "N35_013"],  # son, daughter (no "child")
        "Sibling": [
            "N35_024",
            "N35_025",
            "N35_026",
            "N35_027",
        ],  # age-distinguished only
        "Half-sibling": ["N35_031", "N35_032"],
        "Grandparent": [
            "N35_044",
            "N35_045",
            "N35_046",
            "N35_047",
        ],  # maternal/paternal only
        "Grandchild": ["N35_052", "N35_053"],  # grandson, granddaughter (no "grandchild")
        "Aunt/Uncle": ["N35_063", "N35_064", "N35_065", "N35_066"],  # maternal/paternal only
        "Niece/Nephew": ["N35_071", "N35_072"],
        "Cousin": ["N35_081"],  # gender-neutral
        "Spouse": ["N35_092", "N35_093"],  # husband, wife (no "spouse" or "partner")
        "In-law": [
            "N35_102",
            "N35_103",
            "N35_104",
            "N35_105",
            "N35_106",
            "N35_107",
        ],  # no "parent-in-law"
        "Step-parent": ["N35_111", "N35_112"],
        "Step-child": ["N35_122", "N35_123"],  # stepson, stepdaughter (no "stepchild")
        "Other relations": ["N35_131"],
    },
    "ko": {
        # Korean uses age-distinguished siblings
        "Parent": ["N35_001", "N35_002", "N35_003"],
        "Child": ["N35_011", "N35_012", "N35_013"],
        "Sibling": [
            "N35_024",
            "N35_025",
            "N35_026",
            "N35_027",
        ],  # age-distinguished
        "Half-sibling": ["N35_031", "N35_032"],
        "Grandparent": ["N35_041", "N35_042", "N35_043"],
        "Grandchild": ["N35_051", "N35_052", "N35_053"],
        "Aunt/Uncle": ["N35_061", "N35_062"],
        "Niece/Nephew": ["N35_071", "N35_072"],
        "Cousin": ["N35_081"],
        "Spouse": ["N35_091", "N35_092", "N35_093", "N35_094"],
        "In-law": ["N35_101", "N35_102", "N35_103", "N35_104", "N35_105", "N35_106", "N35_107"],
        "Step-parent": ["N35_111", "N35_112"],
        "Step-child": ["N35_121", "N35_122", "N35_123"],
        "Other relations": ["N35_131"],
    },
    "vi": {
        # Vietnamese uses age-distinguished siblings
        "Parent": ["N35_001", "N35_002", "N35_003"],
        "Child": ["N35_011", "N35_012", "N35_013"],
        "Sibling": [
            "N35_024",
            "N35_025",
            "N35_026",
            "N35_027",
        ],  # age-distinguished
        "Half-sibling": ["N35_031", "N35_032"],
        "Grandparent": ["N35_041", "N35_042", "N35_043"],
        "Grandchild": ["N35_051", "N35_052", "N35_053"],
        "Aunt/Uncle": ["N35_061", "N35_062"],
        "Niece/Nephew": ["N35_071", "N35_072"],
        "Cousin": ["N35_081"],
        "Spouse": ["N35_091", "N35_092", "N35_093", "N35_094"],
        "In-law": ["N35_101", "N35_102", "N35_103", "N35_104", "N35_105", "N35_106", "N35_107"],
        "Step-parent": ["N35_111", "N35_112"],
        "Step-child": ["N35_121", "N35_122", "N35_123"],
        "Other relations": ["N35_131"],
    },
    # Romance languages - use base config
    "es": ROMANCE_BASE_CONFIG,  # Spanish
    "fr": ROMANCE_BASE_CONFIG,  # French
    "pt": ROMANCE_BASE_CONFIG,  # Portuguese
    "it": ROMANCE_BASE_CONFIG,  # Italian
    # Germanic languages - use base config
    "de": GERMANIC_BASE_CONFIG,  # German
    "nl": GERMANIC_BASE_CONFIG,  # Dutch
    "sv": GERMANIC_BASE_CONFIG,  # Swedish
}

# Default config for languages not explicitly configured
# Uses all general terms, no special variants
DEFAULT_LANGUAGE_CONFIG = {
    "Parent": ["N35_001", "N35_002", "N35_003"],
    "Child": ["N35_011", "N35_012", "N35_013"],
    "Sibling": ["N35_021", "N35_022", "N35_023"],
    "Half-sibling": ["N35_031", "N35_032"],
    "Grandparent": ["N35_041", "N35_042", "N35_043"],
    "Grandchild": ["N35_051", "N35_052", "N35_053"],
    "Aunt/Uncle": ["N35_061", "N35_062"],
    "Niece/Nephew": ["N35_071", "N35_072"],
    "Cousin": ["N35_081"],
    "Spouse": ["N35_091", "N35_092", "N35_093", "N35_094"],
    "In-law": ["N35_101", "N35_102", "N35_103", "N35_104", "N35_105", "N35_106", "N35_107"],
    "Step-parent": ["N35_111", "N35_112"],
    "Step-child": ["N35_121", "N35_122", "N35_123"],
    "Other relations": ["N35_131"],
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
                                json.dumps(variant.tags)
                                if variant.tags
                                else None  # Valid JSON array
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
