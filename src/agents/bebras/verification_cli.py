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
from typing import Any, Dict, List, Optional

from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_guid_arg,
    add_language_args,
    add_llm_args,
    add_processing_args,
    confirm_operation,
    get_data_source_config,
)
from storage.models.schema import Lemma, Sentence

from .verification import (
    DEFAULT_VERIFY_LANGUAGES,
    MODEL_LANGUAGE_SUPPORT,
    IncorrectPronunciationAction,
    PronunciationCheckItem,
    VerificationAgent,
    filter_languages_for_model,
    get_dialect_display_name,
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
        "submit-batch-words", help="Submit batch word verification job to OpenAI Batch API"
    )
    _add_batch_args(batch_words_parser)

    batch_sentences_parser = subparsers.add_parser(
        "submit-batch-sentences", help="Submit batch sentence verification job to OpenAI Batch API"
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


def verify_words(args: argparse.Namespace) -> int:
    """Verify word translations."""
    config = get_data_source_config(args)
    agent = VerificationAgent(config)
    session = agent.get_session()

    try:
        # Determine languages to verify
        languages = getattr(args, "languages", None) or DEFAULT_VERIFY_LANGUAGES
        languages = filter_languages_for_model(languages, config.model or "gpt-5.4-mini")

        if not languages:
            logger.error(f"No supported languages for model {config.model}")
            return 1

        logger.info(f"Verifying languages: {', '.join(languages)}")

        # Build query for lemmas
        query = session.query(Lemma).filter(Lemma.guid.isnot(None))

        if args.guid:
            # Single GUID mode
            query = query.filter(Lemma.guid == args.guid)
        elif getattr(args, "unverified_only", False):
            # Only lemmas with unverified translations
            from storage.models.schema import LemmaTranslation

            query = (
                query.join(LemmaTranslation)
                .filter(
                    LemmaTranslation.verified == False,
                    LemmaTranslation.language_code.in_(languages),
                )
                .distinct()
            )

        # Apply limit
        if args.limit:
            query = query.limit(args.limit)

        lemmas = query.all()

        if not lemmas:
            logger.info("No lemmas found to verify")
            return 0

        # Confirm operation
        if not args.guid:
            estimated_calls = len(lemmas)
            if not confirm_operation(
                f"Will verify translations for {len(lemmas)} words.",
                estimated_calls=estimated_calls,
                skip_confirmation=args.yes,
                dry_run=args.dry_run,
            ):
                return 0

        # Run verification
        result = agent.batch_verify_words(
            lemmas=lemmas,
            languages=languages,
            session=session,
            dry_run=args.dry_run or getattr(args, "report_only", False),
            update_verified_flag=not getattr(args, "report_only", False),
        )

        # Output results
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            _print_word_verification_results(result)

        return 0

    except Exception as e:
        logger.error(f"Error during verification: {e}", exc_info=True)
        return 1
    finally:
        session.close()


def verify_sentences(args: argparse.Namespace) -> int:
    """Verify sentence translations."""
    config = get_data_source_config(args)
    agent = VerificationAgent(config)
    session = agent.get_session()

    try:
        # Determine languages to verify
        languages = getattr(args, "languages", None) or DEFAULT_VERIFY_LANGUAGES
        languages = filter_languages_for_model(languages, config.model or "gpt-5.4-mini")

        if not languages:
            logger.error(f"No supported languages for model {config.model}")
            return 1

        logger.info(f"Verifying languages: {', '.join(languages)}")

        # Build query for sentences
        query = session.query(Sentence)

        if args.sentence_id:
            # Single sentence mode
            query = query.filter(Sentence.id == args.sentence_id)
        elif getattr(args, "unverified_only", False):
            # Only sentences with unverified translations
            from storage.models.schema import SentenceTranslation

            query = (
                query.join(SentenceTranslation)
                .filter(
                    SentenceTranslation.verified == False,
                    SentenceTranslation.language_code.in_(languages),
                )
                .distinct()
            )

        # Apply limit
        if args.limit:
            query = query.limit(args.limit)

        sentences = query.all()

        if not sentences:
            logger.info("No sentences found to verify")
            return 0

        # Confirm operation
        if not args.sentence_id:
            estimated_calls = len(sentences)
            if not confirm_operation(
                f"Will verify translations for {len(sentences)} sentences.",
                estimated_calls=estimated_calls,
                skip_confirmation=args.yes,
                dry_run=args.dry_run,
            ):
                return 0

        # Run verification
        result = agent.batch_verify_sentences(
            sentences=sentences,
            languages=languages,
            session=session,
            check_lemma_links=getattr(args, "check_lemma_links", True),
            dry_run=args.dry_run or getattr(args, "report_only", False),
            update_verified_flag=not getattr(args, "report_only", False),
        )

        # Output results
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            _print_sentence_verification_results(result)

        return 0

    except Exception as e:
        logger.error(f"Error during verification: {e}", exc_info=True)
        return 1
    finally:
        session.close()


def _print_word_verification_results(result: Dict[str, Any]) -> None:
    """Print word verification results in human-readable format."""
    print("\n" + "=" * 60)
    print("Word Translation Verification Results")
    print("=" * 60)
    print(f"Total lemmas verified: {result['total_lemmas']}")
    print(f"Total translations checked: {result['total_translations_checked']}")
    print(f"Correct: {result['correct_count']}")
    print(f"Incorrect: {result['incorrect_count']}")
    print(f"Errors: {result['error_count']}")

    # Show details for incorrect translations
    incorrect_items = []
    for item in result.get("results", []):
        if item.get("success"):
            for lang_code, verdict in item.get("results", {}).items():
                if verdict == "incorrect":
                    incorrect_items.append(
                        {
                            "guid": item.get("lemma_guid"),
                            "word": item.get("lemma_text"),
                            "lang": lang_code,
                            "translation": item.get("translations_checked", {}).get(lang_code),
                        }
                    )

    if incorrect_items:
        print(f"\nIncorrect Translations ({len(incorrect_items)}):")
        for item in incorrect_items[:20]:  # Show first 20
            dialect = get_dialect_display_name(item["lang"])
            print(f"  - {item['guid']} '{item['word']}' [{dialect}]: {item['translation']}")
        if len(incorrect_items) > 20:
            print(f"  ... and {len(incorrect_items) - 20} more")

    print("=" * 60)


def _print_sentence_verification_results(result: Dict[str, Any]) -> None:
    """Print sentence verification results in human-readable format."""
    print("\n" + "=" * 60)
    print("Sentence Translation Verification Results")
    print("=" * 60)
    print(f"Total sentences verified: {result['total_sentences']}")
    print(f"Fully correct: {result['fully_correct_count']}")
    print(f"Has issues: {result['has_issues_count']}")
    print(f"Errors: {result['error_count']}")

    # Show details for sentences with issues
    issue_items = []
    for item in result.get("results", []):
        if item.get("success"):
            for lang_code, lang_result in item.get("results", {}).items():
                issues = []
                if lang_result.get("meaning_correct") != "correct":
                    issues.append("meaning")
                if lang_result.get("grammar_correct") != "correct":
                    issues.append("grammar")

                for guid, lemma_check in lang_result.get("lemma_checks", {}).items():
                    if lemma_check.get("sense_correct") != "correct":
                        issues.append(f"lemma sense ({guid})")
                    if lemma_check.get("form_matches") != "correct":
                        issues.append(f"lemma form ({guid})")

                if issues:
                    issue_items.append(
                        {
                            "sentence_id": item.get("sentence_id"),
                            "english": item.get("english_text", "")[:50],
                            "lang": lang_code,
                            "translation": lang_result.get("translation", "")[:50],
                            "issues": issues,
                        }
                    )

    if issue_items:
        print(f"\nSentences with Issues ({len(issue_items)}):")
        for item in issue_items[:10]:  # Show first 10
            dialect = get_dialect_display_name(item["lang"])
            print(f"\n  Sentence ID: {item['sentence_id']}")
            print(f"  English: {item['english']}...")
            print(f"  {dialect}: {item['translation']}...")
            print(f"  Issues: {', '.join(item['issues'])}")
        if len(issue_items) > 10:
            print(f"\n  ... and {len(issue_items) - 10} more")

    print("=" * 60)


def submit_batch_words(args: argparse.Namespace) -> int:
    """Submit batch word verification job."""
    config = get_data_source_config(args)
    agent = VerificationAgent(config)

    languages = getattr(args, "languages", None) or DEFAULT_VERIFY_LANGUAGES
    limit = getattr(args, "limit", 100)
    unverified_only = getattr(args, "unverified_only", True)

    logger.info(f"Submitting batch word verification for languages: {', '.join(languages)}")
    logger.info(f"Limit: {limit}, Unverified only: {unverified_only}")

    batch_id, count = agent.submit_batch_word_verification(
        languages=languages,
        limit=limit,
        unverified_only=unverified_only,
    )

    if batch_id:
        print("=" * 80)
        print("BEBRAS VERIFICATION - BATCH SUBMISSION REPORT")
        print("=" * 80)
        print(f"Batch ID: {batch_id}")
        print(f"Requests submitted: {count}")
        print(f"Languages: {', '.join(languages)}")
        print("=" * 80)
        print(f"Check status with: python -m agents.common.batch status --batch-id {batch_id}")
        print(
            f"Complete batch with: python -m agents.common.batch complete --batch-id {batch_id} --agent bebras_verify"
        )
        return 0

    logger.warning("No batch submitted (no items to verify)")
    return 0


def submit_batch_sentences(args: argparse.Namespace) -> int:
    """Submit batch sentence verification job."""
    config = get_data_source_config(args)
    agent = VerificationAgent(config)

    languages = getattr(args, "languages", None) or DEFAULT_VERIFY_LANGUAGES
    limit = getattr(args, "limit", 100)
    unverified_only = getattr(args, "unverified_only", True)
    check_lemma_links = getattr(args, "check_lemma_links", True)

    logger.info(f"Submitting batch sentence verification for languages: {', '.join(languages)}")
    logger.info(f"Limit: {limit}, Unverified only: {unverified_only}")

    batch_id, count = agent.submit_batch_sentence_verification(
        languages=languages,
        limit=limit,
        unverified_only=unverified_only,
        check_lemma_links=check_lemma_links,
    )

    if batch_id:
        print("=" * 80)
        print("BEBRAS VERIFICATION - BATCH SUBMISSION REPORT")
        print("=" * 80)
        print(f"Batch ID: {batch_id}")
        print(f"Requests submitted: {count}")
        print(f"Languages: {', '.join(languages)}")
        print("=" * 80)
        print(f"Check status with: python -m agents.common.batch status --batch-id {batch_id}")
        print(
            f"Complete batch with: python -m agents.common.batch complete --batch-id {batch_id} --agent bebras_verify"
        )
        return 0

    logger.warning("No batch submitted (no items to verify)")
    return 0


def verify_pronunciations(args: argparse.Namespace) -> int:
    """Bulk verify IPA/phonetic pronunciations from a JSON list."""
    config = get_data_source_config(args)
    agent = VerificationAgent(config)

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
    result = agent.verify_bulk_pronunciations(
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
        return verify_words(args)
    elif args.verify_type == "sentences":
        return verify_sentences(args)
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
