"""Command line for the reading lexicon export.

Usage::

    PYTHONPATH=src python -m exports.reading_lexicon --language en \
        --output data/exports/reading-lexicon.en.json

    # every reading language at once, into one directory
    PYTHONPATH=src python -m exports.reading_lexicon --language en es fr zh lt \
        --output-dir data/exports
"""

import argparse
import logging
import os
from typing import List, Optional

from agents.common.common_args import add_backend_args, get_data_source_config
from exports.reading_lexicon.export_reading_lexicon import (
    DEFAULT_GLOSS_LANGUAGES,
    ReadingLexiconExporter,
)


def output_filename(language: str) -> str:
    """The conventional file name, as consumers fetch it."""
    return f"reading-lexicon.{language}.json"


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Export the reading lexicon (word-by-word annotation data) per text language"
    )
    parser.add_argument(
        "--language",
        nargs="+",
        required=True,
        help="Text language(s) to export: the language being read (en, es, fr, zh, lt, ...)",
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--output", help="Output file (only with a single --language)")
    target.add_argument(
        "--output-dir", help="Directory to write reading-lexicon.<lang>.json files into"
    )
    parser.add_argument(
        "--gloss-languages",
        default=",".join(DEFAULT_GLOSS_LANGUAGES),
        help="Comma-separated languages to gloss lemmas in (default: %(default)s)",
    )
    parser.add_argument(
        "--include-staging",
        action="store_true",
        help="Also export unreviewed staging-band lemmas",
    )
    parser.add_argument(
        "--stored-forms-only",
        action="store_true",
        help="Export only stored derivative forms; do not fill paradigms by rule",
    )
    parser.add_argument("--pretty", action="store_true", help="Indent the JSON")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--db-path", default=None, help="SQLite database to read (default: inferred)"
    )
    add_backend_args(parser)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.output and len(args.language) != 1:
        parser.error("--output takes exactly one --language; use --output-dir for several")

    config = get_data_source_config(args)
    gloss_languages = tuple(
        code.strip() for code in args.gloss_languages.split(",") if code.strip()
    )
    for language in args.language:
        path = args.output or os.path.join(args.output_dir, output_filename(language))
        exporter = ReadingLexiconExporter(
            language=language,
            config=config,
            gloss_languages=gloss_languages,
            include_staging=args.include_staging,
            derive_forms=not args.stored_forms_only,
        )
        document = exporter.export(path, pretty=args.pretty)
        meta = document["_meta"]
        print(
            f"{language}: {meta['lemma_count']} lemmas, {meta['form_count']} surface forms, "
            f"{meta['function_word_count']} function words -> {path}"
        )


if __name__ == "__main__":
    main()
