#!/usr/bin/python3

"""Generate a corpus word-frequency JSON file from downloaded Gutenberg books.

    PYTHONPATH=src python src/wordfreq/corpora/download_gutenberg.py --corpus 19th_books
    PYTHONPATH=src python src/wordfreq/corpora/build_wordfreq.py --corpus 19th_books

Reads the cached plain-text files written by ``download_gutenberg.py``, strips
the Gutenberg header/footer and transcription apparatus, separates proper nouns
from ordinary vocabulary, and writes ``data/wordfreq/<corpus>.json`` in the
format ``wordfreq.frequency.importer`` expects.

No network and no database access: this step is reproducible from the cache.
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List, Optional, Sequence

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import constants
from wordfreq.corpora.book_lists import BOOK_LISTS, GutenbergBook, get_book_list
from wordfreq.corpora.download_gutenberg import default_cache_dir, text_path
from wordfreq.corpora.frequency_build import (
    DEFAULT_FULL_WEIGHT_TOKENS,
    DEFAULT_MIN_BOOKS,
    DEFAULT_MIN_NAME_COUNT,
    BookAnalysis,
    analyze_book,
    book_report_rows,
    build_corpus_payload,
    write_corpus_json,
)

logger = logging.getLogger(__name__)


def analyze_corpus_books(
    books: List[GutenbergBook],
    cache_dir: Path,
    *,
    skip_missing: bool = False,
    always_vocabulary: Sequence[str] = (),
) -> List[BookAnalysis]:
    """Analyze every cached book in ``books``.

    Args:
        books: Books making up the corpus.
        cache_dir: Directory holding ``<id>.txt`` files.
        skip_missing: Warn and continue when a book is not cached, instead of
            raising.
        always_vocabulary: Words this corpus keeps as vocabulary rather than
            letting them be classified as proper nouns.

    Returns:
        One :class:`BookAnalysis` per book that could be read.

    Raises:
        FileNotFoundError: If a book is missing and ``skip_missing`` is False.
    """
    analyses: List[BookAnalysis] = []
    for index, book in enumerate(books, start=1):
        path = text_path(cache_dir, book.gutenberg_id)
        if not path.exists():
            message = f"Not downloaded: #{book.gutenberg_id} {book.title} ({path})"
            if not skip_missing:
                raise FileNotFoundError(
                    f"{message}. Run download_gutenberg.py first, or pass --skip-missing."
                )
            logger.warning(message)
            continue

        raw_text = path.read_text(encoding="utf-8", errors="replace")
        analysis = analyze_book(book.slug, raw_text, extra_never_names=always_vocabulary)
        logger.info(
            "[%d/%d] %s: %d tokens, %d names",
            index,
            len(books),
            book.slug,
            analysis.stats.token_total,
            len(analysis.names),
        )
        analyses.append(analysis)
    return analyses


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus", required=True, choices=sorted(BOOK_LISTS), help="Corpus to build"
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help=f"Directory of downloaded books (default: {default_cache_dir()})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path (default: data/wordfreq/<corpus>.json)",
    )
    parser.add_argument(
        "--max-words", type=int, default=None, help="Words to keep (default: per book list)"
    )
    parser.add_argument(
        "--weighting",
        choices=["per-book-mean", "pooled"],
        default="per-book-mean",
        help="per-book-mean averages each word's rate across books (default); "
        "pooled sums raw counts, letting long books dominate",
    )
    parser.add_argument(
        "--min-books",
        type=int,
        default=DEFAULT_MIN_BOOKS,
        help=f"Books a word must appear in (default: {DEFAULT_MIN_BOOKS})",
    )
    parser.add_argument(
        "--min-name-count",
        type=int,
        default=DEFAULT_MIN_NAME_COUNT,
        help=f"Minimum count for a name to be reported (default: {DEFAULT_MIN_NAME_COUNT})",
    )
    parser.add_argument(
        "--full-weight-tokens",
        type=int,
        default=DEFAULT_FULL_WEIGHT_TOKENS,
        help=f"Length at which a book gets full weight (default: {DEFAULT_FULL_WEIGHT_TOKENS})",
    )
    parser.add_argument(
        "--skip-missing", action="store_true", help="Ignore books that are not downloaded"
    )
    parser.add_argument("--report", type=Path, help="Write per-book statistics as JSON")
    parser.add_argument("--top", type=int, default=25, help="Top words to print (default: 25)")
    parser.add_argument("--dry-run", action="store_true", help="Do not write the corpus file")
    parser.add_argument("--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    book_list = get_book_list(args.corpus)
    cache_dir = args.source_dir or default_cache_dir()
    max_words: Optional[int] = args.max_words or book_list.max_words

    analyses = analyze_corpus_books(
        list(book_list.books),
        cache_dir,
        skip_missing=args.skip_missing,
        always_vocabulary=book_list.always_vocabulary,
    )
    if not analyses:
        logger.error("No books could be read from %s", cache_dir)
        return 1

    payload = build_corpus_payload(
        analyses,
        corpus_name=book_list.corpus_name,
        weighting=args.weighting,
        min_books=args.min_books,
        max_words=max_words,
        min_name_count=args.min_name_count,
        full_weight_tokens=args.full_weight_tokens,
    )

    output_path = args.output or Path(constants.WORDFREQ_DATA_DIR) / f"{args.corpus}.json"

    frequencies = payload["global_word_frequency"]
    print(f"\nCorpus: {book_list.corpus_name}")
    print(f"  books processed:   {len(analyses)} of {len(book_list.books)}")
    print(f"  tokens counted:    {payload['generation']['total_tokens']:,}")
    print(f"  unique words:      {payload['total_unique_words']:,}")
    print(f"  names identified:  {payload['total_names_identified']:,}")
    print(f"  words written:     {len(frequencies):,}")
    print(f"\n  Top {args.top} words:")
    for rank, (word, value) in enumerate(list(frequencies.items())[: args.top], start=1):
        print(f"    {rank:>3}. {word:<16} {value:,}")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as handle:
            json.dump(book_report_rows(analyses), handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        print(f"\n  Per-book report: {args.report}")

    if args.dry_run:
        print(f"\nDry run: would write {output_path}")
        return 0

    write_corpus_json(payload, str(output_path))
    print(f"\nWrote {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
