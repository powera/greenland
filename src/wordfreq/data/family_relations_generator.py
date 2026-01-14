#!/usr/bin/env python3

"""
Family Relations Generator

This module manages family relation lemmas across different languages, handling
the complexity that family terms vary significantly between languages:
- Some languages gender cousins, siblings, or other relations
- Some languages distinguish older/younger siblings (Korean, Chinese, etc.)
- Some languages have different levels of formality for family terms
- The M->N translation problem means we can't assume 1:1 mappings

This generator:
1. Defines family relation terms with language-specific applicability
2. Creates/updates lemmas in the database
3. Uses LemmaDifficultyOverride to exclude terms from languages where they don't apply
   (difficulty_level = -1 means exclude)
4. Handles language-specific variations as separate lemmas when needed

Usage:
    PYTHONPATH=src python src/wordfreq/data/family_relations_generator.py --help
    PYTHONPATH=src python src/wordfreq/data/family_relations_generator.py --dry-run
    PYTHONPATH=src python src/wordfreq/data/family_relations_generator.py --apply
"""

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Add parent directory to path for imports
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from wordfreq.storage.backend.config import BackendType, DataSourceConfig
from wordfreq.storage.backend.factory import create_session
from wordfreq.storage.crud.difficulty_override import add_difficulty_override
from wordfreq.storage.crud.lemma import add_lemma
from wordfreq.storage.models.schema import Lemma
from wordfreq.storage.translation_helpers import LANGUAGE_HIERARCHY


@dataclass
class FamilyRelationTerm:
    """Definition of a family relation term with language applicability."""

    lemma_text: str  # English term (base form)
    definition: str  # English definition

    # Which languages this term is applicable to
    # If None, applicable to all languages
    # If specified, only applicable to listed languages (and always includes 'en')
    applicable_languages: Optional[Set[str]] = None

    # Which languages to explicitly EXCLUDE (for easier specification)
    # These will get difficulty_level = -1 overrides
    exclude_languages: Set[str] = field(default_factory=set)

    # Optional notes about the term
    notes: Optional[str] = None

    # Difficulty level (1-20 for Trakaido, or None for auto-assignment)
    difficulty_level: Optional[int] = None

    # Tags for additional categorization
    tags: List[str] = field(default_factory=list)

    def get_excluded_languages(self, all_languages: List[str]) -> Set[str]:
        """
        Get the set of languages this term should be excluded from.

        Returns languages that are either:
        1. In exclude_languages, OR
        2. Not in applicable_languages (if applicable_languages is specified)

        Always excludes 'en' from the exclusion list.
        """
        excluded = set(self.exclude_languages)

        if self.applicable_languages is not None:
            # If applicable_languages is specified, exclude all others
            for lang in all_languages:
                if lang not in self.applicable_languages and lang != "en":
                    excluded.add(lang)

        # Never exclude English (source language)
        excluded.discard("en")

        return excluded


# Family relation terms organized by category
# These terms represent the English-centric view and specify which languages they apply to

NUCLEAR_FAMILY = [
    FamilyRelationTerm(
        lemma_text="parent",
        definition="A mother or father",
        difficulty_level=1,
        tags=["nuclear_family", "gender_neutral"],
    ),
    FamilyRelationTerm(
        lemma_text="mother",
        definition="A female parent",
        difficulty_level=1,
        tags=["nuclear_family", "female"],
    ),
    FamilyRelationTerm(
        lemma_text="father",
        definition="A male parent",
        difficulty_level=1,
        tags=["nuclear_family", "male"],
    ),
    FamilyRelationTerm(
        lemma_text="child",
        definition="A son or daughter",
        difficulty_level=1,
        tags=["nuclear_family", "gender_neutral"],
    ),
    FamilyRelationTerm(
        lemma_text="son",
        definition="A male child",
        difficulty_level=1,
        tags=["nuclear_family", "male"],
    ),
    FamilyRelationTerm(
        lemma_text="daughter",
        definition="A female child",
        difficulty_level=1,
        tags=["nuclear_family", "female"],
    ),
    FamilyRelationTerm(
        lemma_text="sibling",
        definition="A brother or sister",
        difficulty_level=2,
        tags=["nuclear_family", "gender_neutral"],
        notes="Gender-neutral term; less common in some languages",
    ),
    FamilyRelationTerm(
        lemma_text="brother",
        definition="A male sibling",
        difficulty_level=1,
        tags=["nuclear_family", "male"],
        notes="Some languages distinguish older/younger brother (see separate entries)",
    ),
    FamilyRelationTerm(
        lemma_text="sister",
        definition="A female sibling",
        difficulty_level=1,
        tags=["nuclear_family", "female"],
        notes="Some languages distinguish older/younger sister (see separate entries)",
    ),
]

# Age-distinguished siblings (common in East Asian languages)
SIBLING_AGE_VARIANTS = [
    FamilyRelationTerm(
        lemma_text="older brother",
        definition="A male sibling who is older than oneself",
        applicable_languages={"en", "zh", "ko", "vi"},
        difficulty_level=2,
        tags=["nuclear_family", "male", "age_distinguished"],
        notes="Distinct term in Chinese (哥哥), Korean (형/오빠), Vietnamese (anh)",
    ),
    FamilyRelationTerm(
        lemma_text="younger brother",
        definition="A male sibling who is younger than oneself",
        applicable_languages={"en", "zh", "ko", "vi"},
        difficulty_level=3,
        tags=["nuclear_family", "male", "age_distinguished"],
        notes="Distinct term in Chinese (弟弟), Korean (남동생), Vietnamese (em trai)",
    ),
    FamilyRelationTerm(
        lemma_text="older sister",
        definition="A female sibling who is older than oneself",
        applicable_languages={"en", "zh", "ko", "vi"},
        difficulty_level=2,
        tags=["nuclear_family", "female", "age_distinguished"],
        notes="Distinct term in Chinese (姐姐), Korean (누나/언니), Vietnamese (chị)",
    ),
    FamilyRelationTerm(
        lemma_text="younger sister",
        definition="A female sibling who is younger than oneself",
        applicable_languages={"en", "zh", "ko", "vi"},
        difficulty_level=3,
        tags=["nuclear_family", "female", "age_distinguished"],
        notes="Distinct term in Chinese (妹妹), Korean (여동생), Vietnamese (em gái)",
    ),
]

EXTENDED_FAMILY = [
    FamilyRelationTerm(
        lemma_text="grandparent",
        definition="A parent of one's parent",
        difficulty_level=2,
        tags=["extended_family", "gender_neutral"],
    ),
    FamilyRelationTerm(
        lemma_text="grandmother",
        definition="A mother of one's parent",
        difficulty_level=2,
        tags=["extended_family", "female"],
        notes="Many languages distinguish maternal/paternal grandmother",
    ),
    FamilyRelationTerm(
        lemma_text="grandfather",
        definition="A father of one's parent",
        difficulty_level=2,
        tags=["extended_family", "male"],
        notes="Many languages distinguish maternal/paternal grandfather",
    ),
    FamilyRelationTerm(
        lemma_text="grandchild",
        definition="A child of one's child",
        difficulty_level=3,
        tags=["extended_family", "gender_neutral"],
    ),
    FamilyRelationTerm(
        lemma_text="grandson",
        definition="A son of one's child",
        difficulty_level=3,
        tags=["extended_family", "male"],
    ),
    FamilyRelationTerm(
        lemma_text="granddaughter",
        definition="A daughter of one's child",
        difficulty_level=3,
        tags=["extended_family", "female"],
    ),
    FamilyRelationTerm(
        lemma_text="uncle",
        definition="A brother of one's parent, or the husband of one's aunt",
        difficulty_level=2,
        tags=["extended_family", "male"],
        notes="Many languages distinguish maternal/paternal uncle",
    ),
    FamilyRelationTerm(
        lemma_text="aunt",
        definition="A sister of one's parent, or the wife of one's uncle",
        difficulty_level=2,
        tags=["extended_family", "female"],
        notes="Many languages distinguish maternal/paternal aunt",
    ),
    FamilyRelationTerm(
        lemma_text="nephew",
        definition="A son of one's sibling",
        difficulty_level=3,
        tags=["extended_family", "male"],
    ),
    FamilyRelationTerm(
        lemma_text="niece",
        definition="A daughter of one's sibling",
        difficulty_level=3,
        tags=["extended_family", "female"],
    ),
    FamilyRelationTerm(
        lemma_text="cousin",
        definition="A child of one's aunt or uncle",
        difficulty_level=2,
        tags=["extended_family", "gender_neutral"],
        notes="Not always gender-neutral; see gendered variants",
    ),
]

# Gendered cousin variants (Romance languages, Slavic languages, etc.)
COUSIN_VARIANTS = [
    FamilyRelationTerm(
        lemma_text="male cousin",
        definition="A male child of one's aunt or uncle",
        # Applicable to languages that gender cousins
        applicable_languages={"en", "es", "pt", "it", "fr"},
        difficulty_level=3,
        tags=["extended_family", "male", "gendered"],
        notes="Distinct in Spanish (primo), French (cousin), Italian (cugino), Portuguese (primo)",
    ),
    FamilyRelationTerm(
        lemma_text="female cousin",
        definition="A female child of one's aunt or uncle",
        applicable_languages={"en", "es", "pt", "it", "fr"},
        difficulty_level=3,
        tags=["extended_family", "female", "gendered"],
        notes="Distinct in Spanish (prima), French (cousine), Italian (cugina), Portuguese (prima)",
    ),
]

MARRIAGE_FAMILY = [
    FamilyRelationTerm(
        lemma_text="spouse",
        definition="A husband or wife",
        difficulty_level=2,
        tags=["marriage", "gender_neutral"],
    ),
    FamilyRelationTerm(
        lemma_text="husband",
        definition="A married man; a woman's male spouse",
        difficulty_level=1,
        tags=["marriage", "male"],
    ),
    FamilyRelationTerm(
        lemma_text="wife",
        definition="A married woman; a man's female spouse",
        difficulty_level=1,
        tags=["marriage", "female"],
    ),
    FamilyRelationTerm(
        lemma_text="partner",
        definition="A person in a romantic relationship (married or unmarried)",
        difficulty_level=2,
        tags=["marriage", "gender_neutral", "modern"],
        notes="Modern term; may not have direct equivalents in all languages",
    ),
]

IN_LAW_FAMILY = [
    FamilyRelationTerm(
        lemma_text="parent-in-law",
        definition="A parent of one's spouse",
        difficulty_level=4,
        tags=["in_law", "gender_neutral"],
    ),
    FamilyRelationTerm(
        lemma_text="mother-in-law",
        definition="The mother of one's spouse",
        difficulty_level=3,
        tags=["in_law", "female"],
    ),
    FamilyRelationTerm(
        lemma_text="father-in-law",
        definition="The father of one's spouse",
        difficulty_level=3,
        tags=["in_law", "male"],
    ),
    FamilyRelationTerm(
        lemma_text="son-in-law",
        definition="The husband of one's daughter",
        difficulty_level=4,
        tags=["in_law", "male"],
    ),
    FamilyRelationTerm(
        lemma_text="daughter-in-law",
        definition="The wife of one's son",
        difficulty_level=4,
        tags=["in_law", "female"],
    ),
    FamilyRelationTerm(
        lemma_text="brother-in-law",
        definition="The brother of one's spouse, or the husband of one's sibling",
        difficulty_level=4,
        tags=["in_law", "male"],
    ),
    FamilyRelationTerm(
        lemma_text="sister-in-law",
        definition="The sister of one's spouse, or the wife of one's sibling",
        difficulty_level=4,
        tags=["in_law", "female"],
    ),
]

OTHER_RELATIONS = [
    FamilyRelationTerm(
        lemma_text="stepmother",
        definition="The wife of one's father who is not one's biological mother",
        difficulty_level=5,
        tags=["step_family", "female"],
    ),
    FamilyRelationTerm(
        lemma_text="stepfather",
        definition="The husband of one's mother who is not one's biological father",
        difficulty_level=5,
        tags=["step_family", "male"],
    ),
    FamilyRelationTerm(
        lemma_text="stepchild",
        definition="A child of one's spouse from a previous relationship",
        difficulty_level=5,
        tags=["step_family", "gender_neutral"],
    ),
    FamilyRelationTerm(
        lemma_text="stepson",
        definition="A male child of one's spouse from a previous relationship",
        difficulty_level=5,
        tags=["step_family", "male"],
    ),
    FamilyRelationTerm(
        lemma_text="stepdaughter",
        definition="A female child of one's spouse from a previous relationship",
        difficulty_level=5,
        tags=["step_family", "female"],
    ),
    FamilyRelationTerm(
        lemma_text="half-brother",
        definition="A brother with whom one shares only one parent",
        difficulty_level=5,
        tags=["step_family", "male"],
    ),
    FamilyRelationTerm(
        lemma_text="half-sister",
        definition="A sister with whom one shares only one parent",
        difficulty_level=5,
        tags=["step_family", "female"],
    ),
    FamilyRelationTerm(
        lemma_text="twin",
        definition="One of two children born to the same mother at the same time",
        difficulty_level=4,
        tags=["nuclear_family", "gender_neutral"],
    ),
]

# All family relation terms
ALL_FAMILY_RELATIONS = (
    NUCLEAR_FAMILY
    + SIBLING_AGE_VARIANTS
    + EXTENDED_FAMILY
    + COUSIN_VARIANTS
    + MARRIAGE_FAMILY
    + IN_LAW_FAMILY
    + OTHER_RELATIONS
)


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
        "total_terms": len(ALL_FAMILY_RELATIONS),
        "created": 0,
        "existing": 0,
        "overrides_created": 0,
        "errors": [],
    }

    session = create_session(config)
    try:
        for term in ALL_FAMILY_RELATIONS:
            try:
                if verbose:
                    print(f"\nProcessing: {term.lemma_text}")
                    print(f"  Definition: {term.definition}")

                # Check if lemma already exists before creating
                existing = (
                    session.query(Lemma)
                    .filter(
                        Lemma.lemma_text == term.lemma_text,
                        Lemma.definition_text == term.definition,
                        Lemma.pos_type == "noun",
                    )
                    .first()
                )

                is_new = existing is None

                # Create or get the lemma
                lemma = add_lemma(
                    session=session,
                    lemma_text=term.lemma_text,
                    definition_text=term.definition,
                    pos_type="noun",
                    pos_subtype="family_relation",
                    difficulty_level=term.difficulty_level,
                    tags=term.tags if term.tags else None,
                    notes=term.notes,
                    auto_generate_guid=True,
                )

                # Ensure ID is assigned for new lemmas
                if is_new and lemma.id is None:
                    session.flush()

                # Track statistics
                if is_new:
                    stats["created"] += 1
                    if verbose:
                        print(f"  ✓ Created new lemma (GUID: {lemma.guid})")
                else:
                    stats["existing"] += 1
                    if verbose:
                        print(f"  → Already exists (GUID: {lemma.guid})")

                # Get languages to exclude
                excluded_langs = term.get_excluded_languages(LANGUAGE_HIERARCHY)

                if excluded_langs:
                    if verbose:
                        print(f"  Excluding from: {', '.join(sorted(excluded_langs))}")

                    # Create difficulty overrides to exclude this term from certain languages
                    for lang_code in excluded_langs:
                        override = add_difficulty_override(
                            session=session,
                            lemma_id=lemma.id,
                            language_code=lang_code,
                            difficulty_level=-1,  # -1 means exclude
                            notes=f"Not applicable in {lang_code}",
                        )
                        stats["overrides_created"] += 1

                if term.applicable_languages:
                    if verbose:
                        applicable = sorted(term.applicable_languages)
                        print(f"  Applicable to: {', '.join(applicable)}")

            except Exception as e:
                error_msg = f"Error processing {term.lemma_text}: {str(e)}"
                stats["errors"].append(error_msg)
                print(f"  ✗ {error_msg}")
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
    print(f"Total terms processed:      {stats['total_terms']}")
    print(f"New lemmas created:         {stats['created']}")
    print(f"Existing lemmas found:      {stats['existing']}")
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
    print(f"Total terms defined: {len(ALL_FAMILY_RELATIONS)}")
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
