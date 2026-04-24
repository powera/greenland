#!/usr/bin/env python3
"""Genys CLI entry point."""

import argparse
import sys
from pathlib import Path

# Add src directory to path
if str(Path(__file__).parent.parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_llm_args,
    add_processing_args,
    confirm_operation,
    get_data_source_config,
)


def get_argument_parser() -> argparse.ArgumentParser:
    """Build and return argument parser for genys."""
    parser = argparse.ArgumentParser(
        description="Genys - Document parser and PendingImport staging agent"
    )

    add_common_args(parser)
    add_llm_args(parser, default_model="gpt-5.4-mini")
    add_processing_args(parser)
    add_backend_args(parser)

    parser.add_argument("--input", required=True, help="Path to text document")
    parser.add_argument(
        "--language", required=True, help="Document language code (e.g., en, zh, fr)"
    )
    parser.add_argument(
        "--store-sentences",
        action="store_true",
        help="Store source sentences and sentence words in sentence tables",
    )
    parser.add_argument(
        "--pivot-languages",
        default="bn,uk,kn",
        help=(
            "Comma-separated pivot languages used to disambiguate ambiguous English "
            "words via sentence-level translations (default: bn,uk,kn). Pass an empty "
            "string to disable pivot disambiguation."
        ),
    )

    return parser


def main() -> None:
    """Run the genys agent from command line."""
    from agents.genys.agent import GenysAgent

    parser = get_argument_parser()
    args = parser.parse_args()

    config = get_data_source_config(args)
    agent = GenysAgent(config=config)

    input_path = Path(args.input)
    if not input_path.exists() or not input_path.is_file():
        print(f"Error: input file not found: {args.input}")
        sys.exit(1)

    raw_text = input_path.read_text(encoding="utf-8")
    split_sentences = agent.split_sentences(raw_text, args.language)
    total_sentences = len(split_sentences)
    estimated_calls = min(total_sentences, args.limit) if args.limit else total_sentences

    if not confirm_operation(
        message=(
            f"Document: {input_path.name}\n"
            f"Language: {args.language}\n"
            f"Sentences parsed: {total_sentences}\n"
            f"Target model: {args.model}\n"
            f"Store sentences: {'yes' if args.store_sentences else 'no'}"
        ),
        estimated_calls=estimated_calls,
        skip_confirmation=args.yes,
        dry_run=args.dry_run,
    ):
        return

    pivot_languages = [lang.strip() for lang in args.pivot_languages.split(",") if lang.strip()]

    results = agent.process_document(
        input_path=args.input,
        document_language=args.language,
        store_sentences=args.store_sentences,
        dry_run=args.dry_run,
        throttle_seconds=args.throttle,
        limit=args.limit,
        pivot_languages=pivot_languages,
    )

    print(f"Document: {results['document']} ({results['document_language']})")
    print(f"Sentences parsed: {results['sentences_parsed']}")
    print(f"Total words extracted: {results['total_words_extracted']}")
    print(f"  - Function/grammatical words skipped: {results['function_words_skipped']}")
    print(f"  - Already in database: {results['already_in_database']}")
    print(f"  - Already staged in pending_imports: {results['existing_pending']}")
    print(f"  - Staged for review: {results['staged_for_review']}")
    if results["errors"]:
        print(f"  - Decomposition errors: {results['errors']}")


if __name__ == "__main__":
    main()
