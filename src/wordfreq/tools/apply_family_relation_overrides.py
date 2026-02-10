#!/usr/bin/env python3
"""
CLI tool for applying family relation word difficulty level overrides.

This tool allows you to:
- Preview changes that would be made for a specific language
- Apply overrides for one or all languages
- View current family relation overrides
- Clear family relation overrides

The key difference from country overrides is that family relation overrides
primarily deal with EXCLUSION (setting terms to null/-1) rather than
prioritizing difficulty levels. This is because family relation terms that
don't exist naturally in a language should be excluded from learning.

Examples:
    # Preview changes for Chinese learners
    PYTHONPATH=src python src/wordfreq/tools/apply_family_relation_overrides.py preview zh

    # Apply changes for Chinese learners
    PYTHONPATH=src python src/wordfreq/tools/apply_family_relation_overrides.py apply zh

    # Preview changes for all languages
    PYTHONPATH=src python src/wordfreq/tools/apply_family_relation_overrides.py preview-all

    # Apply changes for all languages
    PYTHONPATH=src python src/wordfreq/tools/apply_family_relation_overrides.py apply-all

    # View current overrides for a language
    PYTHONPATH=src python src/wordfreq/tools/apply_family_relation_overrides.py view zh

    # Validate the priority configuration
    PYTHONPATH=src python src/wordfreq/tools/apply_family_relation_overrides.py validate
"""

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Optional

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

# Import priority configuration (no database dependencies)
from wordfreq.tools.family_relation_priorities import (
    ALL_FAMILY_RELATIONS,
    get_excluded_terms_for_language,
    get_included_terms_for_language,
    get_supported_languages,
    validate_configuration,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from wordfreq.tools.family_relation_override_manager import (
        FamilyRelationOverrideManager,
    )


def _get_db_session(db_path: Optional[str]) -> "Session":
    """Lazy import and create database session."""
    from wordfreq.storage.database import create_database_session

    return create_database_session(db_path) if db_path else create_database_session()


def _get_manager(session: "Session") -> "FamilyRelationOverrideManager":
    """Lazy import and create manager."""
    from wordfreq.tools.family_relation_override_manager import (
        FamilyRelationOverrideManager,
    )

    return FamilyRelationOverrideManager(session)


def cmd_preview(args: argparse.Namespace) -> None:
    """Preview changes for a single language."""
    session = _get_db_session(args.db_path)
    manager = _get_manager(session)

    print(f"Previewing family relation overrides for '{args.language}'...")
    print()

    try:
        summary = manager.preview_changes(args.language, include_unchanged=args.show_all)
        print(manager.format_summary_report(summary))
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        session.close()


def cmd_preview_all(args: argparse.Namespace) -> None:
    """Preview changes for all languages."""
    session = _get_db_session(args.db_path)
    manager = _get_manager(session)

    print("Previewing family relation overrides for all languages...")
    print()

    try:
        for lang_code in get_supported_languages():
            print(f"\n{'='*60}")
            print(f"LANGUAGE: {lang_code}")
            print("=" * 60)

            summary = manager.preview_changes(lang_code, include_unchanged=False)
            excluded = get_excluded_terms_for_language(lang_code)
            included = get_included_terms_for_language(lang_code)

            print(f"Terms included: {len(included)}")
            print(f"Terms excluded (null): {len(excluded)}")
            print(f"Changes to apply: {len(summary.changes)}")

            if summary.changes:
                exclusion_count = sum(1 for c in summary.changes if c.is_exclusion)
                inclusion_count = len(summary.changes) - exclusion_count
                print(f"  - Exclusions to add: {exclusion_count}")
                print(f"  - Exclusions to remove: {inclusion_count}")
    finally:
        session.close()


def cmd_apply(args: argparse.Namespace) -> None:
    """Apply changes for a single language."""
    session = _get_db_session(args.db_path)
    manager = _get_manager(session)

    action = "DRY RUN - " if args.dry_run else ""
    print(f"{action}Applying family relation overrides for '{args.language}'...")
    print()

    try:
        summary = manager.apply_overrides(
            args.language,
            dry_run=args.dry_run,
        )

        if args.dry_run:
            print("DRY RUN - No changes were committed")
            print()

        print(manager.format_summary_report(summary))

        if not args.dry_run:
            print()
            print(f"Successfully applied {len(summary.changes)} overrides!")
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        session.close()


def cmd_apply_all(args: argparse.Namespace) -> None:
    """Apply changes for all languages."""
    session = _get_db_session(args.db_path)
    manager = _get_manager(session)

    action = "DRY RUN - " if args.dry_run else ""
    print(f"{action}Applying family relation overrides for all languages...")
    print()

    try:
        results = manager.apply_overrides_all_languages(dry_run=args.dry_run)

        total_changes = 0
        for lang_code, summary in results.items():
            print(f"{lang_code}: {len(summary.changes)} changes")
            total_changes += len(summary.changes)

        if args.dry_run:
            print()
            print("DRY RUN - No changes were committed")
        else:
            print()
            print(f"Successfully applied {total_changes} total overrides!")
    finally:
        session.close()


def cmd_view(args: argparse.Namespace) -> None:
    """View current overrides for a language."""
    session = _get_db_session(args.db_path)
    manager = _get_manager(session)

    print(f"Current family relation overrides for '{args.language}':")
    print("=" * 60)

    try:
        overrides = manager.get_current_overrides_for_language(args.language)

        if not overrides:
            print("No family relation overrides found for this language.")
            return

        # Sort by level, then by lemma text
        overrides.sort(
            key=lambda x: (
                x[1].difficulty_level,
                x[0].lemma_text,
            )
        )

        print(f"{'GUID':<12} {'Concept':<25} {'Level':>6}")
        print("-" * 60)

        for lemma, override in overrides:
            concept = lemma.lemma_text
            level_str = str(override.difficulty_level)
            if override.difficulty_level == -1:
                level_str = "-1 (null)"
            print(f"{lemma.guid or '':<12} {concept:<25} {level_str:>10}")

        print()
        print(f"Total: {len(overrides)} overrides")
    finally:
        session.close()


def cmd_clear(args: argparse.Namespace) -> None:
    """Clear family relation overrides for a language."""
    session = _get_db_session(args.db_path)
    manager = _get_manager(session)

    action = "DRY RUN - " if args.dry_run else ""
    print(f"{action}Clearing family relation overrides for '{args.language}'...")

    try:
        count = manager.clear_family_relation_overrides_for_language(
            args.language, dry_run=args.dry_run
        )

        if args.dry_run:
            print(f"DRY RUN - Would remove {count} overrides")
        else:
            print(f"Removed {count} overrides")
    finally:
        session.close()


def cmd_validate(args: argparse.Namespace) -> None:
    """Validate the priority configuration."""
    print("Validating family relation priority configuration...")
    print()

    issues = validate_configuration()

    if issues:
        print("Issues found:")
        for issue in issues:
            print(f"  - {issue}")
        sys.exit(1)
    else:
        print("Configuration is valid!")
        print()
        print(f"Total family relation terms: {len(ALL_FAMILY_RELATIONS)}")
        print(f"Supported languages: {len(get_supported_languages())}")
        print(f"  {', '.join(get_supported_languages())}")


def cmd_info(args: argparse.Namespace) -> None:
    """Show configuration info for a language."""
    if args.language not in get_supported_languages():
        print(f"Error: Language '{args.language}' not found in configuration.")
        print(f"Supported languages: {', '.join(get_supported_languages())}")
        sys.exit(1)

    excluded = get_excluded_terms_for_language(args.language)
    included = get_included_terms_for_language(args.language)

    print(f"Family relation configuration for '{args.language}':")
    print("=" * 60)

    print(f"\nINCLUDED terms ({len(included)}):")
    print("-" * 40)
    for term in sorted(included):
        print(f"  - {term}")

    print(f"\nEXCLUDED terms (set to null) ({len(excluded)}):")
    print("-" * 40)
    for term in sorted(excluded):
        print(f"  - {term}")


def cmd_list_terms(args: argparse.Namespace) -> None:
    """List all known family relation terms."""
    print("All family relation terms:")
    print("=" * 60)

    for i, term in enumerate(ALL_FAMILY_RELATIONS, 1):
        print(f"  {i:2}. {term}")

    print()
    print(f"Total: {len(ALL_FAMILY_RELATIONS)} terms")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply family relation word difficulty level overrides",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview changes for Chinese learners
  %(prog)s preview zh

  # Apply changes for Lithuanian learners (dry run first)
  %(prog)s apply lt --dry-run
  %(prog)s apply lt

  # Preview changes for all languages
  %(prog)s preview-all

  # View current overrides for a language
  %(prog)s view zh

  # Show configuration for a language
  %(prog)s info lt

  # List all known family relation terms
  %(prog)s list-terms

  # Validate the configuration
  %(prog)s validate
        """,
    )

    parser.add_argument(
        "--db-path",
        help="Database path (uses default if not specified)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Preview command
    preview_parser = subparsers.add_parser("preview", help="Preview changes for a language")
    preview_parser.add_argument("language", help="Target language code (e.g., zh, lt)")
    preview_parser.add_argument(
        "--show-all",
        action="store_true",
        help="Show all words, including unchanged",
    )

    # Preview-all command
    subparsers.add_parser("preview-all", help="Preview changes for all languages")

    # Apply command
    apply_parser = subparsers.add_parser("apply", help="Apply changes for a language")
    apply_parser.add_argument("language", help="Target language code (e.g., zh, lt)")
    apply_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without committing",
    )

    # Apply-all command
    apply_all_parser = subparsers.add_parser("apply-all", help="Apply changes for all languages")
    apply_all_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without committing",
    )

    # View command
    view_parser = subparsers.add_parser("view", help="View current overrides for a language")
    view_parser.add_argument("language", help="Target language code")

    # Clear command
    clear_parser = subparsers.add_parser(
        "clear", help="Clear family relation overrides for a language"
    )
    clear_parser.add_argument("language", help="Target language code")
    clear_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without committing",
    )

    # Validate command
    subparsers.add_parser("validate", help="Validate the priority configuration")

    # Info command
    info_parser = subparsers.add_parser("info", help="Show configuration info for a language")
    info_parser.add_argument("language", help="Target language code")

    # List-terms command
    subparsers.add_parser("list-terms", help="List all known family relation terms")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Dispatch to command handler
    commands = {
        "preview": cmd_preview,
        "preview-all": cmd_preview_all,
        "apply": cmd_apply,
        "apply-all": cmd_apply_all,
        "view": cmd_view,
        "clear": cmd_clear,
        "validate": cmd_validate,
        "info": cmd_info,
        "list-terms": cmd_list_terms,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        print(f"Unknown command: {args.command}")
        parser.print_help()


if __name__ == "__main__":
    main()
