#!/usr/bin/env python3
"""
Verification CLI - Command-line interface for translation verification.

This module provides the command-line interface for verifying word and
sentence translations without regenerating content.
"""

import argparse
import json
import logging
import sys
from typing import List, Optional

from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_guid_arg,
    add_language_args,
    add_llm_args,
    add_processing_args,
    get_data_source_config,
)

from .verification import (
    IncorrectPronunciationAction,
    PronunciationVerificationService,
    PronunciationCheckItem,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_argument_parser() -> argparse.ArgumentParser:
    """
    Return the argument parser for verification commands.
    """
    parser = argparse.ArgumentParser(
        description="Bebras Verification - Verify translation correctness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Verify word translations for tier-1 languages
  %(prog)s words --limit 100

  # Verify word translations for specific languages
  %(prog)s words --languages lt zh fr --limit 50

  # Verify a specific word by GUID
  %(prog)s words --guid WRD-00123

  # Verify sentence translations
  %(prog)s sentences --limit 50 --languages lt zh

  # Verify without updating database (report only)
  %(prog)s words --limit 100 --report-only

  # Verify only unverified translations
  %(prog)s words --unverified-only --limit 100
        """,
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="verify_type", help="What to verify")

    # Words subcommand
    words_parser = subparsers.add_parser("words", help="Verify word translations")
    _add_common_verify_args(words_parser)
    add_guid_arg(words_parser, help_text="Verify only the word with this GUID")

    # Sentences subcommand
    sentences_parser = subparsers.add_parser("sentences", help="Verify sentence translations")
    _add_common_verify_args(sentences_parser)
    sentences_parser.add_argument(
        "--sentence-id",
        type=int,
        default=None,
        help="Verify only the sentence with this ID",
    )
    sentences_parser.add_argument(
        "--check-lemma-links",
        action="store_true",
        default=True,
        help="Also verify linked lemmas (default: True)",
    )
    sentences_parser.add_argument(
        "--no-check-lemma-links",
        action="store_false",
        dest="check_lemma_links",
        help="Skip linked lemma verification",
    )

    # Batch submission subcommands
    batch_words_parser = subparsers.add_parser(
        "submit-batch-words",
        help="Deprecated; use 'python -m verification words' to queue work",
    )
    _add_batch_args(batch_words_parser)

    batch_sentences_parser = subparsers.add_parser(
        "submit-batch-sentences",
        help="Deprecated; use 'python -m verification sentences' to queue work",
    )
    _add_batch_args(batch_sentences_parser)
    batch_sentences_parser.add_argument(
        "--check-lemma-links",
        action="store_true",
        default=True,
        help="Also verify linked lemmas (default: True)",
    )

    pronunciation_parser = subparsers.add_parser(
        "pronunciations",
        help="Bulk verify IPA/phonetic entries (10-50 items) and return wrong words only",
    )
    add_common_args(pronunciation_parser)
    add_llm_args(pronunciation_parser, default_model="gpt-5.4-mini")
    add_backend_args(pronunciation_parser)
    pronunciation_parser.add_argument(
        "--input-json",
        required=True,
        help="Path to JSON list with items: word, chinese_hint, ipa, phonetic",
    )
    pronunciation_parser.add_argument(
        "--incorrect-action",
        choices=["log", "remove", "regenerate"],
        default="log",
        help="How Bebras should handle incorrect words",
    )

    return parser


def _add_common_verify_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments common to all verify subcommands."""
    add_common_args(parser)
    add_llm_args(parser, default_model="gpt-5.4-mini")
    add_backend_args(parser)
    add_processing_args(parser)
    add_language_args(parser, multiple=True)

    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Only report results, don't update verified flags in database",
    )

    parser.add_argument(
        "--unverified-only",
        action="store_true",
        help="Only verify items that haven't been verified yet",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )


def _add_batch_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments for batch submission subcommands."""
    add_common_args(parser)
    add_llm_args(parser, default_model="gpt-5.4-mini")
    add_backend_args(parser)
    add_language_args(parser, multiple=True)

    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of items to queue for batch verification (default: 100)",
    )

    parser.add_argument(
        "--unverified-only",
        action="store_true",
        default=True,
        help="Only verify items that haven't been verified yet (default: True)",
    )


def submit_batch_words(args: argparse.Namespace) -> int:
    """Reject the broken provider-batch path with its queue replacement."""
    del args
    logger.error(
        "OpenAI Batch verification was never able to apply its results. "
        "Use 'python -m verification words ...' to enqueue atomic workqueue jobs."
    )
    return 2


def submit_batch_sentences(args: argparse.Namespace) -> int:
    """Reject the broken provider-batch path with its queue replacement."""
    del args
    logger.error(
        "OpenAI Batch verification was never able to apply its results. "
        "Use 'python -m verification sentences ...' to enqueue atomic workqueue jobs."
    )
    return 2


def verify_pronunciations(args: argparse.Namespace) -> int:
    """Bulk verify IPA/phonetic pronunciations from a JSON list."""
    config = get_data_source_config(args)
    verifier = PronunciationVerificationService(config)

    with open(args.input_json, "r", encoding="utf-8") as input_file:
        payload = json.load(input_file)

    if not isinstance(payload, list):
        logger.error("Input JSON must be a list of pronunciation items.")
        return 1

    items: List[PronunciationCheckItem] = []
    required_fields = ("word", "chinese_hint", "ipa", "phonetic")
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict) or any(field not in item for field in required_fields):
            logger.error("Each item must include: word, chinese_hint, ipa, phonetic.")
            return 1
        items.append(
            {
                "entry_id": str(item.get("entry_id", f"item_{index:02d}")),
                "word": str(item["word"]),
                "chinese_hint": str(item["chinese_hint"]),
                "ipa": str(item["ipa"]),
                "phonetic": str(item["phonetic"]),
            }
        )

    incorrect_action: IncorrectPronunciationAction = args.incorrect_action
    result = verifier.verify_bulk_pronunciations(
        items=items,
        incorrect_action=incorrect_action,
        dry_run=args.dry_run,
    )
    print(
        json.dumps(
            {
                "wrong_ipa_entries": result["wrong_ipa_entries"],
                "wrong_phonetic_entries": result["wrong_phonetic_entries"],
                "wrong_words": result["wrong_words"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main() -> Optional[int]:
    """Main entry point for the verification CLI."""
    parser = get_argument_parser()
    args = parser.parse_args()

    # Configure logging
    if hasattr(args, "debug") and args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Dispatch to appropriate handler
    if args.verify_type == "words":
        from verification.cli import verify_words as verify_words_standalone

        return verify_words_standalone(args)
    elif args.verify_type == "sentences":
        from verification.cli import verify_sentences as verify_sentences_standalone

        return verify_sentences_standalone(args)
    elif args.verify_type == "submit-batch-words":
        return submit_batch_words(args)
    elif args.verify_type == "submit-batch-sentences":
        return submit_batch_sentences(args)
    elif args.verify_type == "pronunciations":
        return verify_pronunciations(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
