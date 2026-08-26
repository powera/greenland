#!/usr/bin/python3

"""Generate a corpus word-frequency JSON file from downloaded Gutenberg books.

    PYTHONPATH=src python src/wordfreq/corpora/download_gutenberg.py --corpus 19th_books
    PYTHONPATH=src python src/wordfreq/corpora/build_wordfreq.py --corpus 19th_books

Reads the cached plain-text files written by ``download_gutenberg.py``, strips
the Gutenberg header/footer and transcription apparatus, separates proper nouns
from ordinary vocabulary, and writes ``data/wordfreq/<corpus>.json`` in the
format ``wordfreq.frequency.importer`` expects.

No network. No database access either, unless ``--phrases-from-db`` is passed:
that reads the multi-word lemma forms so "ice cream" is counted as one token
rather than inflating "ice" and "cream". Without the flag the step stays
reproducible from the cache alone.
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import constants
from agents.common.common_args import add_backend_args, get_data_source_config
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


def _load_phrases(args: argparse.Namespace, always_vocabulary: Sequence[str]) -> Dict[str, int]:
    """Build the multi-word phrase index from the selected data source.

    The backend comes from the standard ``--persona`` / ``--backend`` flags, so
    this reads the local SQLite database by default and a release tree under
    ``--persona custom --backend jsonl --data-dir data/release``.

    The multi-word entries of ``always_vocabulary`` are folded in, because a
    whitelisted name like "New York" is only protected if the tokenizer emits
    it as one token.
    """
    from storage.backend import create_session
    from wordfreq.corpora.lemma_phrases import load_phrase_index

    # Passed explicitly rather than through configure_backend(): only the
    # explicit-config path of create_session() honors the JSONL backend, so a
    # --data-dir release tree would otherwise fall through to SQLite.
    session = create_session(get_data_source_config(args))
    try:
        return load_phrase_index(
            session,
            include_periphrastic=args.join_periphrastic,
            extra_phrases=[word for word in always_vocabulary if " " in word],
        )
    finally:
        session.close()


def analyze_corpus_books(
    books: List[GutenbergBook],
    cache_dir: Path,
    *,
    skip_missing: bool = False,
    always_vocabulary: Sequence[str] = (),
    phrases: Optional[Dict[str, int]] = None,
) -> List[BookAnalysis]:
    """Analyze every cached book in ``books``.

    Args:
        books: Books making up the corpus.
        cache_dir: Directory holding ``<id>.txt`` files.
        skip_missing: Warn and continue when a book is not cached, instead of
            raising.
        always_vocabulary: Words this corpus keeps as vocabulary rather than
            letting them be classified as proper nouns.
        phrases: Multi-word forms to count as single tokens, from
            ``wordfreq.corpora.lemma_phrases.load_phrase_index``.

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
        analysis = analyze_book(
            book.slug,
            raw_text,
            extra_never_names=always_vocabulary,
            phrases=phrases,
        )
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
    parser.add_argument(
        "--phrases-from-db",
        action="store_true",
        help="Read multi-word lemma forms from the database (or --data-dir "
        "release tree) and count each as a single token: ice cream, New York.",
    )
    parser.add_argument(
        "--no-join-periphrastic",
        dest="join_periphrastic",
        action="store_false",
        help="Do not join periphrastic inflections (will walk, more quickly). "
        "They are joined by default, since 'will want' is a form of 'want'; "
        "this leaves the auxiliary merged into a single 'will' token instead.",
    )
    parser.add_argument("--report", type=Path, help="Write per-book statistics as JSON")
    parser.add_argument("--top", type=int, default=25, help="Top words to print (default: 25)")
    parser.add_argument("--dry-run", action="store_true", help="Do not write the corpus file")
    parser.add_argument("--verbose", action="store_true", help="Debug logging")
    # Standard backend selection, so --phrases-from-db can read the local
    # SQLite database or a release tree (--persona custom --backend jsonl
    # --data-dir data/release) the same way the agents do. Only --db-path is
    # taken from add_common_args' set: its --debug and --dry-run would collide
    # with this script's own flags.
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Path to database file (default: inferred from environment)",
    )
    add_backend_args(parser)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    book_list = get_book_list(args.corpus)
    cache_dir = args.source_dir or default_cache_dir()
    max_words: Optional[int] = args.max_words or book_list.max_words

    always_vocabulary = book_list.resolved_always_vocabulary()

    phrases: Optional[Dict[str, int]] = None
    if args.phrases_from_db:
        phrases = _load_phrases(args, always_vocabulary)
        logger.info(
            "Phrase index: %d multi-word forms (periphrastic %s)",
            len(phrases),
            "included" if args.join_periphrastic else "excluded",
        )

    analyses = analyze_corpus_books(
        list(book_list.books),
        cache_dir,
        skip_missing=args.skip_missing,
        always_vocabulary=always_vocabulary,
        phrases=phrases,
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
