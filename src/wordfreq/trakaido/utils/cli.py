
#!/usr/bin/env python3
"""
Command-line interface for trakaido word management tools.

Provides argument parsing and command dispatch for all trakaido operations.
"""

import argparse
import os
import sys
from pathlib import Path

# Add the src directory to the path for imports
GREENLAND_SRC_PATH = '/Users/powera/repo/greenland/src'
sys.path.append(GREENLAND_SRC_PATH)

import constants
from .word_manager import WordManager
from .verb_manager import VerbManager
from .export_manager import TrakaidoExporter
from .bulk_import_verbs import bulk_import_verbs
# from .noun_forms import generate_noun_forms_for_lemmas  # Function not implemented
from wordfreq.trakaido.verb_converter import export_wireword_verbs


def create_parser():
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(description="Trakaido Word Management Tool")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Store subparsers for later access
    parser.subparsers_map = {}

    # Add word command
    add_parser = subparsers.add_parser('add', help='Add a new word')
    add_parser.add_argument('english_word', help='English word to add')
    add_parser.add_argument('--lithuanian', help='Lithuanian translation to clarify meaning')
    add_parser.add_argument('--level', type=int, help='Difficulty level (1-20)')
    add_parser.add_argument('--auto-approve', action='store_true',
                           help='Skip user review')
    add_parser.add_argument('--model', default='gpt-5-mini',
                           help='LLM model to use')

    # Set level command
    level_parser = subparsers.add_parser('set-level', help='Set word difficulty level')
    level_parser.add_argument('identifier', help='GUID or English word')
    level_parser.add_argument('level', type=int, help='New difficulty level (1-20)')
    level_parser.add_argument('--reason', help='Reason for the change')

    # Update word command
    update_parser = subparsers.add_parser('update', help='Update entire Lemma entry using specified model')
    update_parser.add_argument('identifier', help='GUID or English word to update')
    update_parser.add_argument('--auto-approve', action='store_true',
                              help='Skip user review')
    update_parser.add_argument('--model', default='gpt-5-mini',
                              help='LLM model to use')

    # Move words by subtype and level command
    move_parser = subparsers.add_parser('move-words', help='Move all words with specific level and subtype to new level')
    move_parser.add_argument('from_level', type=int, help='Current difficulty level (1-20)')
    move_parser.add_argument('subtype', help='POS subtype (e.g., "clothing")')
    move_parser.add_argument('to_level', type=int, help='New difficulty level (1-20)')
    move_parser.add_argument('--reason', help='Reason for the bulk change')
    move_parser.add_argument('--dry-run', action='store_true', help='Show what would be changed without making changes')

    # List words command
    list_parser = subparsers.add_parser('list', help='List words')
    list_parser.add_argument('--level', type=int, help='Filter by difficulty level')
    list_parser.add_argument('--subtype', help='Filter by POS subtype')
    list_parser.add_argument('--limit', type=int, default=50, help='Maximum results')

    # List subtypes command
    subtypes_parser = subparsers.add_parser('subtypes', help='List all subtypes with counts')

    # Generate noun forms command
    generate_forms_parser = subparsers.add_parser('generate-noun-forms', help='Generate derivative forms for Lithuanian nouns')
    generate_forms_parser.add_argument('--limit', type=int, default=50, help='Maximum number of nouns to process')
    generate_forms_parser.add_argument('--level', type=int, help='Filter by specific difficulty level')
    generate_forms_parser.add_argument('--dry-run', action='store_true', help='Show what would be generated without saving')
    generate_forms_parser.add_argument('--force', action='store_true', help='Regenerate forms even if they already exist')

    # Verb commands
    add_verb_parser = subparsers.add_parser('add-verb', help='Add a new verb')
    add_verb_parser.add_argument('english_verb', help='English verb to add (infinitive form)')
    add_verb_parser.add_argument('--translation', help='Translation in target language to clarify meaning')
    add_verb_parser.add_argument('--language', choices=['lt', 'zh', 'ko', 'fr'], default='lt',
                                 help='Target language (default: lt)')
    add_verb_parser.add_argument('--level', type=int, help='Difficulty level (1-20)')
    add_verb_parser.add_argument('--auto-approve', action='store_true',
                                 help='Skip user review')
    add_verb_parser.add_argument('--no-forms', action='store_true',
                                 help='Skip generating conjugation forms')
    add_verb_parser.add_argument('--model', default='gpt-5-mini',
                                 help='LLM model to use')

    list_verbs_parser = subparsers.add_parser('list-verbs', help='List verbs in database')
    list_verbs_parser.add_argument('--language', choices=['lt', 'zh', 'ko', 'fr'], default='lt',
                                   help='Filter by language (default: lt)')
    list_verbs_parser.add_argument('--level', type=int, help='Filter by difficulty level')
    list_verbs_parser.add_argument('--subtype', help='Filter by verb subtype')
    list_verbs_parser.add_argument('--limit', type=int, default=50, help='Maximum results')

    import_verbs_parser = subparsers.add_parser('import-verbs', help='Bulk import verbs from verbs.py file')
    import_verbs_parser.add_argument('--language', choices=['lt'], default='lt',
                                     help='Language code (default: lt)')
    import_verbs_parser.add_argument('--limit', type=int,
                                     help='Limit number of verbs to import')
    import_verbs_parser.add_argument('--dry-run', action='store_true',
                                     help='Show what would be imported without saving')

    # Export commands
    export_parser = subparsers.add_parser('export', help='Export words to files')
    export_subparsers = export_parser.add_subparsers(dest='export_type', help='Export formats')

    # Store export parser for later access to show help
    parser.subparsers_map['export'] = export_parser

    # Export to JSON
    json_parser = export_subparsers.add_parser('json', help='Export to JSON format')
    json_parser.add_argument('--output', help='Output JSON file path')

    # Export to lang_lt
    lang_lt_parser = export_subparsers.add_parser('lang-lt', help='Export to lang_lt directory structure')
    lang_lt_parser.add_argument('--output-dir', help='Output directory path')

    # Export to text
    text_parser = export_subparsers.add_parser('text', help='Export to simple text format for specific subtype')
    text_parser.add_argument('subtype', help='POS subtype to export (required)')
    text_parser.add_argument('--output', help='Output text file path')
    text_parser.add_argument('--level', type=int, help='Filter by specific difficulty level')
    text_parser.add_argument('--include-without-guid', action='store_true',
                            help='Include lemmas without GUIDs')
    text_parser.add_argument('--include-unverified', action='store_true', default=True,
                            help='Include unverified entries (default: True)')

    # Export to wireword format
    wireword_parser = export_subparsers.add_parser('wireword', help='Export nouns/adjectives/etc to single WireWord JSON file')
    wireword_parser.add_argument('--output', help='Output JSON file path')
    wireword_parser.add_argument('--level', type=int, help='Filter by specific difficulty level')
    wireword_parser.add_argument('--subtype', help='Filter by specific POS subtype')
    wireword_parser.add_argument('--include-without-guid', action='store_true',
                                help='Include lemmas without GUIDs')
    wireword_parser.add_argument('--include-unverified', action='store_true', default=True,
                                help='Include unverified entries (default: True)')

    # Export wireword directory (DEPRECATED)
    wireword_dir_parser = export_subparsers.add_parser('wireword-dir',
                                                       help='[DEPRECATED] Export WireWord nouns/adjectives to separate files by level/subtype')
    wireword_dir_parser.add_argument('--output-dir', help='Base output directory (will create wireword subdirectory)')

    # Export wireword verbs
    wireword_verbs_parser = export_subparsers.add_parser('wireword-verbs', help='Export verbs from verbs.py to WireWord JSON file')
    wireword_verbs_parser.add_argument('--output', help='Output JSON file path')

    # Export all
    all_parser = export_subparsers.add_parser('all', help='Export to all formats including wireword directory')
    all_parser.add_argument('--json-output', help='JSON output file path')
    all_parser.add_argument('--lang-lt-dir', help='lang_lt output directory path')
    all_parser.add_argument('--no-wireword-dir', action='store_true', help='Skip wireword directory export')

    return parser


def handle_word_commands(args, manager):
    """Handle word management commands."""
    if args.command == 'add':
        success = manager.add_word(
            english_word=args.english_word,
            lithuanian_word=args.lithuanian,
            difficulty_level=args.level,
            auto_approve=args.auto_approve
        )
        return success

    elif args.command == 'set-level':
        success = manager.set_level(args.identifier, args.level,
                                   reason=getattr(args, 'reason', ''))
        return success

    elif args.command == 'update':
        success = manager.update_word(
            identifier=args.identifier,
            auto_approve=args.auto_approve,
            model=args.model
        )
        return success

    elif args.command == 'move-words':
        success = manager.move_words_by_subtype_and_level(
            from_level=args.from_level,
            subtype=args.subtype,
            to_level=args.to_level,
            reason=getattr(args, 'reason', ''),
            dry_run=getattr(args, 'dry_run', False)
        )
        return success

    return False


def handle_list_commands(args, manager):
    """Handle list and information commands."""
    if args.command == 'list':
        words = manager.list_words(level=args.level, subtype=args.subtype,
                                  limit=args.limit)

        if words:
            print(f"\nFound {len(words)} words:")
            print("-" * 80)
            for word in words:
                status = "✓" if word['verified'] else "?"
                print(f"{status} {word['guid']:<10} L{word['level']:<2} "
                      f"{word['english']:<20} → {word['lithuanian']:<20} "
                      f"({word['subtype']})")
        else:
            print("No words found matching criteria.")
        return True

    elif args.command == 'subtypes':
        subtypes = manager.list_subtypes()

        if subtypes:
            print(f"\nFound {len(subtypes)} subtypes:")
            print("-" * 60)
            for subtype_info in subtypes:
                print(f"{subtype_info['pos_subtype']:<25} ({subtype_info['pos_type']:<10}) {subtype_info['count']:>6} words")
        else:
            print("No subtypes found.")
        return True

    return False


def handle_verb_commands(args, model='gpt-5-mini'):
    """Handle verb management commands."""
    verb_manager = VerbManager(model=args.model if hasattr(args, 'model') else model, debug=False)

    if args.command == 'add-verb':
        success = verb_manager.add_verb(
            english_verb=args.english_verb,
            target_translation=args.translation,
            difficulty_level=args.level,
            auto_approve=args.auto_approve,
            language=args.language,
            generate_forms=not args.no_forms
        )
        return success

    elif args.command == 'list-verbs':
        verbs = verb_manager.list_verbs(
            language=args.language,
            level=args.level,
            subtype=args.subtype,
            limit=args.limit
        )

        if verbs:
            print(f"\nFound {len(verbs)} verbs:")
            print("-" * 80)
            for verb in verbs:
                status = "✓" if verb['verified'] else "?"
                print(f"{status} {verb['guid']:<10} L{verb['level']:<2} "
                      f"{verb['english']:<20} → {verb['translation']:<20} "
                      f"({verb['subtype']})")
        else:
            print("No verbs found matching criteria.")
        return True

    elif args.command == 'import-verbs':
        results = bulk_import_verbs(
            language=args.language,
            limit=args.limit,
            dry_run=args.dry_run
        )
        return results.get('success', False)

    return False


def handle_export_commands(args, manager, export_parser=None):
    """Handle export commands."""
    if not args.export_type:
        if export_parser:
            export_parser.print_help()
        else:
            print("Error: No export type specified. Use 'utils.py export -h' for help.")
        return False

    # Create TrakaidoExporter instance for export operations
    exporter = TrakaidoExporter(db_path=manager.db_path, debug=manager.debug)

    if args.export_type == 'json':
        # Use default path if not provided
        output_path = args.output
        if not output_path:
            output_path = str(Path(GREENLAND_SRC_PATH) / "wordfreq" / "trakaido" / "exported_nouns.json")

        success, stats = exporter.export_to_json(
            output_path=output_path,
            include_without_guid=False,  # Only include words with GUIDs
            include_unverified=True,     # Include unverified entries
            pretty_print=True
        )

        if success and stats:
            print(f"Exported {stats.total_entries} words to {output_path}")
            print(f"Entries with GUIDs: {stats.entries_with_guids}")

        return success

    elif args.export_type == 'lang-lt':
        # Use default directory if not provided
        output_dir = args.output_dir
        if not output_dir:
            output_dir = f'{GREENLAND_SRC_PATH}/../data/trakaido_wordlists/lang_lt/generated'

        success, results = exporter.export_to_lang_lt(output_dir)

        if success:
            levels_generated = results.get('levels_generated', [])
            dictionaries_generated = results.get('dictionaries_generated', [])

            print(f"\n✅ Export to lang_lt completed:")
            print(f"   Structure files: {len(levels_generated)} levels")
            print(f"   Dictionary files: {len(dictionaries_generated)} subtypes")
            print(f"   Output directory: {output_dir}")

        return success

    elif args.export_type == 'text':
        # Generate default output filename if not provided
        output_path = args.output
        if not output_path:
            output_path = f"{args.subtype}.txt"

        # Convert to absolute path to avoid issues with directory creation
        output_path = str(Path(output_path).resolve())

        success, stats = exporter.export_to_text(
            output_path=output_path,
            pos_subtype=args.subtype,
            difficulty_level=args.level,
            include_without_guid=args.include_without_guid,
            include_unverified=args.include_unverified
        )

        if success and stats:
            print(f"\n✅ Text export completed:")
            print(f"   Exported {stats.total_entries} words for subtype '{args.subtype}'")
            print(f"   Entries with GUIDs: {stats.entries_with_guids}")
            if args.level is not None:
                print(f"   Difficulty level: {args.level}")
            print(f"   Output file: {output_path}")

        return success

    elif args.export_type == 'wireword':
        # Generate default output filename if not provided
        output_path = args.output
        if not output_path:
            output_path = f'{GREENLAND_SRC_PATH}/../data/trakaido_wordlists/lang_lt/generated/wireword/wireword_nouns.json'

        # Ensure directory exists
        output_path = str(Path(output_path).resolve())
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        success, stats = exporter.export_to_wireword_format(
            output_path=output_path,
            difficulty_level=args.level,
            pos_subtype=args.subtype,
            include_without_guid=args.include_without_guid,
            include_unverified=args.include_unverified
        )

        if success and stats:
            print(f"\n✅ WireWord export completed:")
            print(f"   Exported {stats.total_entries} words")
            print(f"   Entries with GUIDs: {stats.entries_with_guids}")
            if args.level is not None:
                print(f"   Difficulty level: {args.level}")
            if args.subtype:
                print(f"   POS subtype: {args.subtype}")
            print(f"   Output file: {output_path}")

        return success

    elif args.export_type == 'wireword-dir':
        # Use default directory if not provided
        output_dir = args.output_dir
        if not output_dir:
            output_dir = f'{GREENLAND_SRC_PATH}/../data/trakaido_wordlists/lang_lt/generated'

        success, results = exporter.export_wireword_directory(output_dir)

        if success:
            print(f"\n✅ WireWord directory export completed:")
            print(f"   Files created: {len(results.get('files_created', []))}")
            print(f"   Levels exported: {len(results.get('levels_exported', []))}")
            print(f"   Subtypes exported: {len(results.get('subtypes_exported', []))}")
            print(f"   Total words: {results.get('total_words', 0)}")
            print(f"   Output directory: {os.path.abspath(os.path.join(output_dir, 'wireword'))}")

        return success

    elif args.export_type == 'wireword-verbs':
        # Use default output path if not provided
        output_path = args.output
        if not output_path:
            output_path = f'{GREENLAND_SRC_PATH}/../data/trakaido_wordlists/lang_lt/generated/wireword/wireword_verbs.json'

        # Ensure directory exists
        output_path = str(Path(output_path).resolve())
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        success, results = export_wireword_verbs(output_path)

        if success:
            print(f"\n✅ WireWord verbs export completed:")
            print(f"   Total verbs: {results['total_verbs']}")
            print(f"   Total grammatical forms: {results['total_forms']}")
            print(f"   Levels: {results['levels']}")
            print(f"   Level distribution: {results['level_distribution']}")
            print(f"   Group distribution: {results['group_distribution']}")
            print(f"   Output file: {results['output_path']}")

            if results['skipped_verbs']:
                print(f"   Skipped verbs ({len(results['skipped_verbs'])}): {', '.join(results['skipped_verbs'])}")
        else:
            print(f"\n❌ WireWord verbs export failed: {results.get('error', 'Unknown error')}")

        return success

    elif args.export_type == 'all':
        # Use default paths if not provided
        json_path = args.json_output
        if not json_path:
            json_path = str(Path(GREENLAND_SRC_PATH) / "wordfreq" / "trakaido" / "exported_nouns.json")

        lang_lt_dir = args.lang_lt_dir
        if not lang_lt_dir:
            lang_lt_dir = f'{GREENLAND_SRC_PATH}/../data/trakaido_wordlists/lang_lt/generated'

        # Include wireword directory unless explicitly disabled
        include_wireword_dir = not args.no_wireword_dir

        success, results = exporter.export_all(
            json_path,
            lang_lt_dir,
            include_wireword_directory=include_wireword_dir
        )
        return success

    return False


def main():
    """Main entry point for command-line interface."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    manager = WordManager(model=args.model if hasattr(args, 'model') else 'gpt-5-mini')

    success = False

    # Handle different command types
    if args.command in ['add', 'set-level', 'update', 'move-words']:
        success = handle_word_commands(args, manager)

    elif args.command in ['list', 'subtypes']:
        success = handle_list_commands(args, manager)

    elif args.command in ['add-verb', 'list-verbs', 'import-verbs']:
        success = handle_verb_commands(args, model=args.model if hasattr(args, 'model') else 'gpt-5-mini')

    elif args.command == 'generate-noun-forms':
        # Function not implemented yet
        print("Error: generate-noun-forms command is not yet implemented")
        success = False

    elif args.command == 'export':
        export_parser = parser.subparsers_map.get('export')
        success = handle_export_commands(args, manager, export_parser)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
