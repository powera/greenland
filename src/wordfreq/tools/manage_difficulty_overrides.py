#!/usr/bin/env python3
"""
Utility script to manage per-language difficulty level overrides.

This script allows you to:
- Set difficulty level overrides for specific words in specific languages
- View current overrides
- Bulk import overrides from CSV
- Examples:
  - Mark "chopsticks" as level 2 in Chinese but level 10 in German
  - Exclude words from specific languages (level -1)
"""

import argparse
import csv
import sys
from pathlib import Path
from typing import List, Dict, Optional

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import constants
from wordfreq.storage.database import create_database_session
from wordfreq.storage.models.schema import Lemma, LemmaDifficultyOverride
from wordfreq.storage.crud.difficulty_override import (
    add_difficulty_override,
    get_difficulty_override,
    get_all_overrides_for_lemma,
    get_all_overrides_for_language,
    delete_difficulty_override,
    get_effective_difficulty_level,
)


def set_override(
    session, guid: str, language_code: str, difficulty_level: int, notes: Optional[str] = None
):
    """Set a difficulty override for a lemma by GUID."""
    # Find lemma by GUID
    lemma = session.query(Lemma).filter(Lemma.guid == guid).first()
    if not lemma:
        print(f"❌ Error: No lemma found with GUID '{guid}'")
        return False

    # Add or update override
    override = add_difficulty_override(
        session=session,
        lemma_id=lemma.id,
        language_code=language_code,
        difficulty_level=difficulty_level,
        notes=notes,
    )

    session.commit()

    effective = get_effective_difficulty_level(session, lemma, language_code)
    print(f"✅ Set override for '{lemma.lemma_text}' ({guid})")
    print(f"   Language: {language_code}")
    print(f"   Level: {difficulty_level} (default: {lemma.difficulty_level})")
    print(f"   Effective level: {effective}")
    if notes:
        print(f"   Notes: {notes}")

    return True


def view_override(session, guid: str):
    """View all overrides for a specific lemma."""
    lemma = session.query(Lemma).filter(Lemma.guid == guid).first()
    if not lemma:
        print(f"❌ Error: No lemma found with GUID '{guid}'")
        return

    print(f"\n📊 Overrides for '{lemma.lemma_text}' ({guid})")
    print(f"   Default level: {lemma.difficulty_level}")
    print(f"   POS: {lemma.pos_type}/{lemma.pos_subtype}")
    print()

    overrides = get_all_overrides_for_lemma(session, lemma.id)
    if not overrides:
        print("   No language-specific overrides set.")
        return

    print("   Language-specific overrides:")
    for override in overrides:
        status = (
            "EXCLUDED" if override.difficulty_level == -1 else f"Level {override.difficulty_level}"
        )
        print(f"   - {override.language_code}: {status}")
        if override.notes:
            print(f"     Notes: {override.notes}")


def view_language_overrides(session, language_code: str, limit: int = 50):
    """View all overrides for a specific language."""
    overrides = get_all_overrides_for_language(session, language_code)

    print(f"\n📊 Difficulty overrides for language: {language_code}")
    print(f"   Total overrides: {len(overrides)}")

    if not overrides:
        print("   No overrides set for this language.")
        return

    print(f"\n   Showing first {min(limit, len(overrides))} overrides:")
    print(f"   {'GUID':<15} {'Word':<25} {'Default':<8} {'Override':<10} {'Notes':<30}")
    print(f"   {'-'*15} {'-'*25} {'-'*8} {'-'*10} {'-'*30}")

    for i, override in enumerate(overrides[:limit]):
        lemma = session.query(Lemma).filter(Lemma.id == override.lemma_id).first()
        if lemma:
            status = (
                "EXCLUDED" if override.difficulty_level == -1 else str(override.difficulty_level)
            )
            word_text = (
                lemma.lemma_text[:24]
                if len(lemma.lemma_text) <= 24
                else lemma.lemma_text[:21] + "..."
            )
            notes_text = (override.notes or "")[:29] if override.notes else ""
            print(
                f"   {lemma.guid:<15} {word_text:<25} {lemma.difficulty_level or 'N/A':<8} {status:<10} {notes_text:<30}"
            )


def remove_override(session, guid: str, language_code: str):
    """Remove a difficulty override."""
    lemma = session.query(Lemma).filter(Lemma.guid == guid).first()
    if not lemma:
        print(f"❌ Error: No lemma found with GUID '{guid}'")
        return False

    deleted = delete_difficulty_override(session, lemma.id, language_code)
    session.commit()

    if deleted:
        print(f"✅ Removed override for '{lemma.lemma_text}' ({guid}) in language {language_code}")
        print(f"   Will now use default level: {lemma.difficulty_level}")
    else:
        print(f"ℹ️  No override found for '{lemma.lemma_text}' ({guid}) in language {language_code}")

    return deleted


def bulk_import_csv(session, csv_path: str):
    """
    Bulk import overrides from CSV file.

    CSV format:
    guid,language_code,difficulty_level,notes
    N01_001,zh,2,"Chopsticks are common in Chinese"
    N01_001,de,10,
    """
    import_count = 0
    error_count = 0

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            guid = row.get("guid", "").strip()
            language_code = row.get("language_code", "").strip()
            difficulty_level_str = row.get("difficulty_level", "").strip()
            notes = row.get("notes", "").strip() or None

            if not guid or not language_code or not difficulty_level_str:
                print(f"⚠️  Skipping row with missing data: {row}")
                error_count += 1
                continue

            try:
                difficulty_level = int(difficulty_level_str)
            except ValueError:
                print(f"⚠️  Invalid difficulty level '{difficulty_level_str}' for {guid}")
                error_count += 1
                continue

            # Find lemma
            lemma = session.query(Lemma).filter(Lemma.guid == guid).first()
            if not lemma:
                print(f"⚠️  No lemma found with GUID '{guid}'")
                error_count += 1
                continue

            # Add override
            try:
                add_difficulty_override(
                    session=session,
                    lemma_id=lemma.id,
                    language_code=language_code,
                    difficulty_level=difficulty_level,
                    notes=notes,
                )
                import_count += 1
            except Exception as e:
                print(f"⚠️  Error adding override for {guid}: {e}")
                error_count += 1

    session.commit()
    print(f"\n✅ Import complete!")
    print(f"   Imported: {import_count}")
    print(f"   Errors: {error_count}")


def export_to_csv(session, language_code: Optional[str], output_path: str):
    """Export overrides to CSV file."""
    if language_code:
        overrides = get_all_overrides_for_language(session, language_code)
    else:
        overrides = session.query(LemmaDifficultyOverride).all()

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["guid", "word", "language_code", "default_level", "override_level", "notes"]
        )

        for override in overrides:
            lemma = session.query(Lemma).filter(Lemma.id == override.lemma_id).first()
            if lemma:
                writer.writerow(
                    [
                        lemma.guid,
                        lemma.lemma_text,
                        override.language_code,
                        lemma.difficulty_level or "",
                        override.difficulty_level,
                        override.notes or "",
                    ]
                )

    print(f"✅ Exported {len(overrides)} overrides to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Manage per-language difficulty level overrides",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Set chopsticks to level 2 in Chinese
  %(prog)s set N01_123 zh 2 --notes "Common eating utensil"

  # Exclude a word from German wordlists
  %(prog)s set N01_456 de -1 --notes "Not relevant for German learners"

  # View overrides for a specific word
  %(prog)s view N01_123

  # View all overrides for Chinese
  %(prog)s list zh

  # Import overrides from CSV
  %(prog)s import overrides.csv

  # Export overrides to CSV
  %(prog)s export --language zh --output zh_overrides.csv
        """,
    )

    parser.add_argument("--db-path", help="Database path (uses default if not specified)")

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Set command
    set_parser = subparsers.add_parser("set", help="Set a difficulty override")
    set_parser.add_argument("guid", help="Lemma GUID")
    set_parser.add_argument("language", help="Language code (e.g., zh, fr, de)")
    set_parser.add_argument("level", type=int, help="Difficulty level (1-20) or -1 to exclude")
    set_parser.add_argument("--notes", help="Notes explaining the override")

    # View command
    view_parser = subparsers.add_parser("view", help="View overrides for a specific lemma")
    view_parser.add_argument("guid", help="Lemma GUID")

    # List command
    list_parser = subparsers.add_parser("list", help="List all overrides for a language")
    list_parser.add_argument("language", help="Language code")
    list_parser.add_argument("--limit", type=int, default=50, help="Limit results (default: 50)")

    # Remove command
    remove_parser = subparsers.add_parser("remove", help="Remove a difficulty override")
    remove_parser.add_argument("guid", help="Lemma GUID")
    remove_parser.add_argument("language", help="Language code")

    # Import command
    import_parser = subparsers.add_parser("import", help="Bulk import from CSV")
    import_parser.add_argument("csv_file", help="Path to CSV file")

    # Export command
    export_parser = subparsers.add_parser("export", help="Export overrides to CSV")
    export_parser.add_argument("--language", help="Language code (exports all if not specified)")
    export_parser.add_argument("--output", required=True, help="Output CSV file path")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Create database session
    try:
        session = (
            create_database_session(args.db_path) if args.db_path else create_database_session()
        )
        print("✅ Connected to wordfreq database")
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        return

    try:
        if args.command == "set":
            set_override(session, args.guid, args.language, args.level, args.notes)
        elif args.command == "view":
            view_override(session, args.guid)
        elif args.command == "list":
            view_language_overrides(session, args.language, args.limit)
        elif args.command == "remove":
            remove_override(session, args.guid, args.language)
        elif args.command == "import":
            bulk_import_csv(session, args.csv_file)
        elif args.command == "export":
            export_to_csv(session, args.language, args.output)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    main()
