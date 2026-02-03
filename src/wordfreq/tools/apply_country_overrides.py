#!/usr/bin/env python3
"""
CLI tool for applying country-related word difficulty level overrides.

This tool allows you to:
- Preview changes that would be made for a specific language
- Apply overrides for one or all languages
- View current country-related overrides
- Clear country-related overrides

Examples:
    # Preview changes for Chinese learners
    PYTHONPATH=src python src/wordfreq/tools/apply_country_overrides.py preview zh

    # Apply changes for Chinese learners
    PYTHONPATH=src python src/wordfreq/tools/apply_country_overrides.py apply zh

    # Preview changes for all languages
    PYTHONPATH=src python src/wordfreq/tools/apply_country_overrides.py preview-all

    # Apply changes for all languages
    PYTHONPATH=src python src/wordfreq/tools/apply_country_overrides.py apply-all

    # View current overrides for a language
    PYTHONPATH=src python src/wordfreq/tools/apply_country_overrides.py view zh

    # Validate the priority configuration
    PYTHONPATH=src python src/wordfreq/tools/apply_country_overrides.py validate
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
from wordfreq.tools.country_word_priorities import (
    TIER_1_LEVEL,
    TIER_2_LEVEL,
    TIER_3_LEVEL,
    TIER_4_LEVEL,
    get_all_tier_levels,
    get_supported_languages,
    validate_configuration,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from wordfreq.tools.country_override_manager import CountryOverrideManager


def _get_db_session(db_path: Optional[str]) -> "Session":
    """Lazy import and create database session."""
    from wordfreq.storage.database import create_database_session

    return create_database_session(db_path) if db_path else create_database_session()


def _get_manager(session: "Session") -> "CountryOverrideManager":
    """Lazy import and create manager."""
    from wordfreq.tools.country_override_manager import CountryOverrideManager

    return CountryOverrideManager(session)


def cmd_preview(args: argparse.Namespace) -> None:
    """Preview changes for a single language."""
    session = _get_db_session(args.db_path)
    manager = _get_manager(session)

    print(f"Previewing country word overrides for '{args.language}'...")
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

    print("Previewing country word overrides for all languages...")
    print()

    try:
        for lang_code in get_supported_languages():
            print(f"\n{'='*60}")
            print(f"LANGUAGE: {lang_code}")
            print("=" * 60)

            summary = manager.preview_changes(lang_code, include_unchanged=False)
            print(f"Words with changes: {summary.words_with_changes}")

            tier_names = {
                TIER_1_LEVEL: "Tier 1 (Home/Neighbors)",
                TIER_2_LEVEL: "Tier 2 (Major Powers)",
                TIER_3_LEVEL: "Tier 3 (Secondary)",
                TIER_4_LEVEL: "Tier 4 (Lowest Priority)",
            }

            for level in get_all_tier_levels():
                count = summary.changes_by_tier.get(level, 0)
                if count > 0:
                    print(f"  Level {level} ({tier_names.get(level, '')}): {count}")
    finally:
        session.close()


def cmd_apply(args: argparse.Namespace) -> None:
    """Apply changes for a single language."""
    session = _get_db_session(args.db_path)
    manager = _get_manager(session)

    action = "DRY RUN - " if args.dry_run else ""
    print(f"{action}Applying country word overrides for '{args.language}'...")
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
            print(f"Successfully applied {summary.words_with_changes} overrides!")
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
    print(f"{action}Applying country word overrides for all languages...")
    print()

    try:
        results = manager.apply_overrides_all_languages(dry_run=args.dry_run)

        total_changes = 0
        for lang_code, summary in results.items():
            print(f"{lang_code}: {summary.words_with_changes} changes")
            total_changes += summary.words_with_changes

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

    print(f"Current country-related overrides for '{args.language}':")
    print("=" * 60)

    try:
        overrides = manager.get_current_overrides_for_language(args.language)

        if not overrides:
            print("No country-related overrides found for this language.")
            return

        # Sort by level
        overrides.sort(key=lambda x: (x[1].difficulty_level, x[0].lemma_text))

        print(f"{'GUID':<12} {'Word':<20} {'Type':<12} {'Level':>6}")
        print("-" * 60)

        for lemma, override in overrides:
            print(
                f"{lemma.guid or '':<12} {lemma.lemma_text:<20} "
                f"{lemma.pos_subtype or '':<12} {override.difficulty_level:>6}"
            )

        print()
        print(f"Total: {len(overrides)} overrides")
    finally:
        session.close()


def cmd_clear(args: argparse.Namespace) -> None:
    """Clear country-related overrides for a language."""
    session = _get_db_session(args.db_path)
    manager = _get_manager(session)

    action = "DRY RUN - " if args.dry_run else ""
    print(f"{action}Clearing country-related overrides for '{args.language}'...")

    try:
        count = manager.clear_country_overrides_for_language(args.language, dry_run=args.dry_run)

        if args.dry_run:
            print(f"DRY RUN - Would remove {count} overrides")
        else:
            print(f"Removed {count} overrides")
    finally:
        session.close()


def cmd_validate(args: argparse.Namespace) -> None:
    """Validate the priority configuration."""
    print("Validating country word priority configuration...")
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
        print(f"Supported languages: {len(get_supported_languages())}")
        print(f"  {', '.join(get_supported_languages())}")
        print()
        print("Tier levels:")
        print(f"  Tier 1 (Home/Neighbors): Level {TIER_1_LEVEL}")
        print(f"  Tier 2 (Major Powers): Level {TIER_2_LEVEL}")
        print(f"  Tier 3 (Secondary): Level {TIER_3_LEVEL}")
        print(f"  Tier 4 (Lowest Priority): Level {TIER_4_LEVEL}")


def cmd_info(args: argparse.Namespace) -> None:
    """Show configuration info for a language."""
    from wordfreq.tools.country_word_priorities import COUNTRY_PRIORITIES

    if args.language not in COUNTRY_PRIORITIES:
        print(f"Error: Language '{args.language}' not found in configuration.")
        print(f"Supported languages: {', '.join(get_supported_languages())}")
        sys.exit(1)

    priorities = COUNTRY_PRIORITIES[args.language]

    print(f"Country priority configuration for '{args.language}':")
    print("=" * 60)

    tier_names = {
        TIER_1_LEVEL: "Tier 1 - Home country and immediate neighbors",
        TIER_2_LEVEL: "Tier 2 - Major world powers and culturally relevant",
        TIER_3_LEVEL: "Tier 3 - Secondary importance",
        TIER_4_LEVEL: "Tier 4 - Lowest priority",
    }

    for level in get_all_tier_levels():
        countries = priorities.get(level, [])
        print(f"\nLevel {level} ({tier_names.get(level, '')}):")
        if countries:
            for country in countries:
                print(f"  - {country}")
        else:
            print("  (no countries assigned)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply country-related word difficulty level overrides",
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
    preview_all_parser = subparsers.add_parser(
        "preview-all", help="Preview changes for all languages"
    )

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
        "clear", help="Clear country-related overrides for a language"
    )
    clear_parser.add_argument("language", help="Target language code")
    clear_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without committing",
    )

    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate the priority configuration")

    # Info command
    info_parser = subparsers.add_parser("info", help="Show configuration info for a language")
    info_parser.add_argument("language", help="Target language code")

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
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        print(f"Unknown command: {args.command}")
        parser.print_help()


if __name__ == "__main__":
    main()
