#!/usr/bin/env python3
"""
Erelis CLI - Command-line interface for false lemma match detection.

This module provides the command-line interface for the Erelis agent,
allowing users to detect sentences where lemma translations don't appear
in the corresponding sentence translations.
"""

import argparse
import json
import logging
import sys
from typing import Optional

from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_guid_arg,
    add_processing_args,
    get_data_source_config,
)

from .agent import ErelisAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_argument_parser() -> argparse.ArgumentParser:
    """
    Return the argument parser for introspection.

    This function allows external tools to introspect the available
    command-line arguments without executing the main function.
    """
    parser = argparse.ArgumentParser(
        description="Erelis (Eagle) - False Lemma Match Detection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check all sentences for Chinese false matches
  %(prog)s --language zh

  # Check with a limit
  %(prog)s --language zh --limit 100

  # Check a specific sentence
  %(prog)s --language zh --sentence-id 42

  # Check sentences containing a specific lemma
  %(prog)s --language zh --guid V03_007

  # Output as JSON
  %(prog)s --language zh --json

  # Show statistics only
  %(prog)s --language zh --stats
        """,
    )

    # Required arguments
    parser.add_argument(
        "--language",
        "-l",
        required=True,
        help="Target language code to check (e.g., 'zh', 'lt', 'fr')",
    )

    # Filter options
    parser.add_argument(
        "--sentence-id",
        type=int,
        default=None,
        help="Check only this specific sentence ID",
    )

    # Add common GUID argument for filtering by lemma
    add_guid_arg(parser, help_text="Check only sentences containing this lemma GUID")

    # Output options
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show statistics only, don't run checks",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output for each match",
    )

    # Common arguments
    add_common_args(parser)
    add_backend_args(parser)
    add_processing_args(parser)

    return parser


def print_match(match: dict, verbose: bool = False) -> None:
    """Print a single false match in human-readable format."""
    print(f"\n  Sentence {match['sentence_id']}:")
    print(f"    English: {match['sentence_english']}")
    print(f"    {match['language_code'].upper()}: {match['sentence_translation']}")
    print(
        f"    Lemma: {match['lemma_english']} ({match['lemma_guid']}) "
        f"-> {match['lemma_translation']}"
    )
    print(f"    Part of speech: {match['part_of_speech']}, Position: {match['position']}")


def print_results(result: dict, verbose: bool = False) -> None:
    """Print check results in human-readable format."""
    if not result.get("success"):
        print(f"\nError: {result.get('error', 'Unknown error')}")
        return

    print(f"\n{'='*70}")
    print(f"False Lemma Match Detection - {result['target_language'].upper()}")
    print(f"{'='*70}")
    print(f"Sentences checked: {result['sentences_checked']}")
    print(f"False matches found: {result['false_matches_found']}")

    if result["false_matches_found"] > 0:
        # Show summary by lemma
        print(f"\nMatches by lemma:")
        for lemma, count in sorted(result["lemma_summary"].items(), key=lambda x: -x[1]):
            print(f"  {lemma}: {count} occurrences")

        if verbose:
            print(f"\nDetailed matches:")
            for match in result["matches"]:
                print_match(match, verbose)

    print(f"{'='*70}")


def print_stats(stats: dict) -> None:
    """Print statistics in human-readable format."""
    print(f"\n{'='*70}")
    print(f"Database Statistics - {stats['target_language'].upper()}")
    print(f"{'='*70}")
    print(f"Total sentences: {stats['total_sentences']}")
    print(f"Sentences with lemma links: {stats['sentences_with_lemmas']}")
    print(
        f"Sentences with {stats['target_language'].upper()} translation: "
        f"{stats['sentences_with_target_translation']}"
    )
    print(f"Total lemma links: {stats['total_lemma_links']}")
    print(f"{'='*70}")


def main() -> Optional[int]:
    """Main entry point for the Erelis CLI."""
    parser = get_argument_parser()
    args = parser.parse_args()

    # Configure logging
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Create configuration from args
    config = get_data_source_config(args)

    # Initialize agent
    agent = ErelisAgent(config=config)

    # Stats only mode
    if args.stats:
        stats = agent.get_statistics(args.language)
        if args.json:
            print(json.dumps(stats, indent=2))
        else:
            print_stats(stats)
        return 0

    # Run checks
    result = agent.check_all_sentences(
        target_language=args.language,
        limit=args.limit if hasattr(args, "limit") else None,
        sentence_id=args.sentence_id,
        lemma_guid=args.guid if hasattr(args, "guid") else None,
    )

    # Output results
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_results(result, verbose=args.verbose)

    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
