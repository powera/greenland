#!/usr/bin/env python3
"""
Bebras CLI - Command-line interface for sentence-word link management.

This module provides the command-line interface for the Bebras agent,
allowing users to process sentences, manage word links, and add translations.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from .agent import BebrasAgent
from .translation import get_language_name, validate_language_codes

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_argument_parser():
    """
    Return the argument parser for introspection.

    This function allows external tools to introspect the available
    command-line arguments without executing the main function.
    """
    parser = argparse.ArgumentParser(
        description="Bebras - Sentence-Word Link Management Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process a single sentence
  %(prog)s --sentence "I eat a banana" --languages lt zh

  # Process sentences from a file
  %(prog)s --file sentences.txt --languages lt zh

  # Process with source language
  %(prog)s --sentence "La gato dormas" --source eo --languages en lt

  # Interactive mode (prompts for disambiguation)
  %(prog)s --sentence "The mouse is on the table" --interactive
        """
    )

    # Input options
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        '--sentence',
        help='Single sentence to process'
    )
    input_group.add_argument(
        '--file',
        help='File containing sentences (one per line)'
    )

    # Language options
    parser.add_argument(
        '--source',
        default='en',
        help='Source language code (default: en)'
    )
    parser.add_argument(
        '--languages',
        nargs='+',
        default=['lt', 'zh'],
        help='Target language codes for translations (default: lt zh)'
    )

    # Processing options
    parser.add_argument(
        '--verified',
        action='store_true',
        help='Mark sentences as verified'
    )
    parser.add_argument(
        '--context',
        help='Optional context about the sentence(s)'
    )
    parser.add_argument(
        '--interactive',
        action='store_true',
        help='Enable interactive disambiguation prompts'
    )

    # Model and database options
    parser.add_argument(
        '--model',
        default='gpt-5-mini',
        help='LLM model to use (default: gpt-5-mini)'
    )
    parser.add_argument(
        '--db-path',
        help='Database path (uses default if not specified)'
    )

    # Output options
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output results as JSON'
    )

    return parser


def process_single_sentence(
    agent: BebrasAgent,
    sentence: str,
    source_language: str,
    target_languages: List[str],
    verified: bool,
    context: Optional[str],
    output_json: bool
) -> int:
    """Process a single sentence."""
    logger.info(f"Processing sentence: {sentence}")

    result = agent.process_sentence(
        sentence_text=sentence,
        source_language=source_language,
        target_languages=target_languages,
        context=context,
        verified=verified
    )

    if output_json:
        import json
        print(json.dumps(result, indent=2))
    else:
        print_result(result)

    return 0 if result.get('success') else 1


def process_file(
    agent: BebrasAgent,
    file_path: str,
    source_language: str,
    target_languages: List[str],
    verified: bool,
    output_json: bool
) -> int:
    """Process sentences from a file."""
    logger.info(f"Processing sentences from: {file_path}")

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            sentences = [line.strip() for line in f if line.strip()]

        if not sentences:
            logger.error("No sentences found in file")
            return 1

        logger.info(f"Found {len(sentences)} sentences to process")

        result = agent.process_sentence_batch(
            sentences=sentences,
            source_language=source_language,
            target_languages=target_languages,
            verified=verified
        )

        if output_json:
            import json
            print(json.dumps(result, indent=2))
        else:
            print_batch_result(result)

        return 0 if result.get('success_count', 0) > 0 else 1

    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        return 1
    except Exception as e:
        logger.error(f"Error processing file: {e}", exc_info=True)
        return 1


def print_result(result: dict):
    """Print processing result in human-readable format."""
    if result.get('success'):
        print("\n✓ Success!")
        print(f"  Sentence ID: {result.get('sentence_id')}")
        print(f"  Text: {result.get('sentence_text')}")
        print(f"  Linked words: {result.get('linked_words', 0)}")
        print(f"  Unlinked words: {result.get('unlinked_words', 0)}")

        min_level = result.get('minimum_level')
        if min_level and min_level > 0:
            print(f"  Minimum level: {min_level}")

        disambiguation = result.get('disambiguation_needed', [])
        if disambiguation:
            print(f"\n  ⚠ Disambiguation needed for {len(disambiguation)} words:")
            for word_info in disambiguation:
                print(f"    - {word_info['word']} ({word_info['pos']}): {word_info['hint']}")
    else:
        print(f"\n✗ Failed: {result.get('error', 'Unknown error')}")


def print_batch_result(result: dict):
    """Print batch processing result in human-readable format."""
    total = result.get('total', 0)
    success = result.get('success_count', 0)
    failure = result.get('failure_count', 0)

    print(f"\n{'='*60}")
    print(f"Batch Processing Complete")
    print(f"{'='*60}")
    print(f"Total sentences: {total}")
    print(f"Successful: {success}")
    print(f"Failed: {failure}")

    # Show details for each sentence
    results = result.get('results', [])
    if results:
        print(f"\nDetails:")
        for i, res in enumerate(results, 1):
            if res.get('success'):
                print(f"  {i}. ✓ {res.get('sentence_text', 'N/A')[:50]}...")
                print(f"     Linked: {res.get('linked_words', 0)}, " +
                      f"Unlinked: {res.get('unlinked_words', 0)}")
            else:
                print(f"  {i}. ✗ Error: {res.get('error', 'Unknown')}")

    print(f"{'='*60}")


def main():
    """Main entry point for the Bebras CLI."""
    parser = get_argument_parser()
    args = parser.parse_args()

    # Configure logging
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate language codes
    target_languages = validate_language_codes(args.languages)
    if not target_languages:
        logger.error("No valid target language codes provided")
        return 1

    # Show language configuration
    source_name = get_language_name(args.source)
    target_names = [get_language_name(lang) for lang in target_languages]
    logger.info(f"Source language: {source_name} ({args.source})")
    logger.info(f"Target languages: {', '.join(target_names)}")

    # Initialize agent
    agent = BebrasAgent(
        db_path=args.db_path,
        debug=args.debug,
        model=args.model
    )

    # Process based on input mode
    if args.sentence:
        return process_single_sentence(
            agent=agent,
            sentence=args.sentence,
            source_language=args.source,
            target_languages=target_languages,
            verified=args.verified,
            context=args.context,
            output_json=args.json
        )
    elif args.file:
        return process_file(
            agent=agent,
            file_path=args.file,
            source_language=args.source,
            target_languages=target_languages,
            verified=args.verified,
            output_json=args.json
        )
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
