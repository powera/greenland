#!/usr/bin/python3

"""Generate the OpenStax textbook corpora from the pinned book checkouts.

    PYTHONPATH=src python src/wordfreq/corpora/download_openstax.py --corpus all
    PYTHONPATH=src python src/wordfreq/corpora/build_openstax.py --corpus openstax_science --phrases-from-db
    PYTHONPATH=src python src/wordfreq/corpora/build_openstax.py --corpus openstax_society --phrases-from-db

Two corpora, from the books listed in ``openstax_books``:

* ``openstax_science`` -- biology, microbiology, anatomy, neuroscience,
  chemistry, physics, astronomy, and three computing books with their code
  stripped.
* ``openstax_society`` -- psychology, lifespan development, sociology,
  anthropology, political science, American government, economics, U.S. and
  world history, philosophy.

What they add is the register of the modern introductory textbook: plain
expository English that defines each term as it introduces it.  The unit of
analysis is the chapter (see :mod:`wordfreq.corpora.openstax_text`), and
everything after extraction is the shared ``frequency_build`` path.

Names remain in the shared frequency pipeline; chapter coverage and weighting
limit terms confined to individual documents. Casing uses ordinary-prose evidence.

No network.  No database access either, unless ``--phrases-from-db`` is passed.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import constants
from agents.common.common_args import add_backend_args, get_data_source_config
from wordfreq.corpora.download_openstax import collection_path, default_cache_dir, repo_dir
from wordfreq.corpora.frequency_build import (
    DEFAULT_MIN_UPPERCASE_COUNT,
    DEFAULT_MIN_UPPERCASE_SHARE,
    analyze_book,
    build_corpus_payload,
    write_corpus_json,
)
from wordfreq.corpora.openstax_books import OPENSTAX_CORPORA, OpenStaxBook, get_books
from wordfreq.corpora.openstax_text import read_chapters

logger = logging.getLogger(__name__)

# ~240 chapters in each corpus.  A word in three chapters has left the one
# section that introduced it.
DEFAULT_MIN_CHAPTERS = 3

# A chapter runs to 5000-20000 words once exercises are stripped; the short
# ones are the computing books' and a few introductory chapters.
DEFAULT_FULL_WEIGHT_CHAPTER_TOKENS = 5000

# A topic corpus, like wiki_society and eu_parliament_debates: a corpus's word
# count is also its weight in combined_rank.
DEFAULT_MAX_WORDS = 5500


def read_book_chapters(cache_dir: Path, books: Sequence[OpenStaxBook]) -> List[Tuple[str, str]]:
    """``(slug, text)`` for every chapter of every book, in book order.

    A book whose checkout is missing is logged and skipped.
    """
    documents: List[Tuple[str, str]] = []
    for book in books:
        collection = collection_path(cache_dir, book)
        if not collection.exists():
            logger.warning("%s: not checked out (%s)", book.slug, collection)
            continue
        chapters = list(
            read_chapters(collection, repo_dir(cache_dir, book.repo) / "modules", book.slug)
        )
        logger.info(
            "%s: %d chapters, %d words",
            book.slug,
            len(chapters),
            sum(len(text.split()) for _, text in chapters),
        )
        documents.extend(chapters)
    return documents


def _load_phrases(args: argparse.Namespace) -> Dict[str, int]:
    """Build the multi-word phrase index from the selected data source."""
    from storage.backend import create_session
    from wordfreq.corpora.lemma_phrases import load_phrase_index

    session = create_session(get_data_source_config(args))
    try:
        return load_phrase_index(session, include_periphrastic=args.join_periphrastic)
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus", required=True, choices=sorted(OPENSTAX_CORPORA), help="Corpus to build"
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help=f"OpenStax cache directory (default: {default_cache_dir()})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path (default: data/wordfreq/<corpus>.json)",
    )
    parser.add_argument(
        "--max-words",
        type=int,
        default=DEFAULT_MAX_WORDS,
        help=f"Words to keep (default: {DEFAULT_MAX_WORDS})",
    )
    parser.add_argument(
        "--min-chapters",
        type=int,
        default=DEFAULT_MIN_CHAPTERS,
        help=f"Chapters a word must appear in (default: {DEFAULT_MIN_CHAPTERS})",
    )

    parser.add_argument(
        "--full-weight-tokens",
        type=int,
        default=DEFAULT_FULL_WEIGHT_CHAPTER_TOKENS,
        help=f"Length at which a chapter gets full weight "
        f"(default: {DEFAULT_FULL_WEIGHT_CHAPTER_TOKENS})",
    )
    parser.add_argument(
        "--min-uppercase-count",
        type=int,
        default=DEFAULT_MIN_UPPERCASE_COUNT,
        help=(
            "Minimum count to publish a capitalized spelling as its own entry "
            f"(default: {DEFAULT_MIN_UPPERCASE_COUNT})"
        ),
    )
    parser.add_argument(
        "--min-uppercase-share",
        type=float,
        default=DEFAULT_MIN_UPPERCASE_SHARE,
        help=(
            "Minimum share of a word's uses that must be capitalized to publish "
            f"it separately (default: {DEFAULT_MIN_UPPERCASE_SHARE})"
        ),
    )
    parser.add_argument(
        "--phrases-from-db",
        action="store_true",
        help="Count known multi-word lemma forms as single tokens",
    )
    parser.add_argument(
        "--no-join-periphrastic",
        dest="join_periphrastic",
        action="store_false",
        help='Do not join "will <verb>" and "more <adj>" into single tokens',
    )

    parser.add_argument("--top", type=int, default=25, help="Top words to print")
    parser.add_argument("--dry-run", action="store_true", help="Report without writing")
    add_backend_args(parser)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    cache_dir: Path = args.source_dir or default_cache_dir()
    if not cache_dir.is_dir():
        logger.error("Cache directory not found: %s; run download_openstax.py first", cache_dir)
        return 1

    phrases: Optional[Dict[str, int]] = None
    if args.phrases_from_db:
        phrases = _load_phrases(args)
        logger.info("Phrase index: %d multi-word forms", len(phrases))

    documents = read_book_chapters(cache_dir, get_books(args.corpus))
    if not documents:
        logger.error("No chapters could be read from %s", cache_dir)
        return 1

    analyses = [analyze_book(slug, text, phrases=phrases) for slug, text in documents]

    payload = build_corpus_payload(
        analyses,
        corpus_name=args.corpus,
        min_books=args.min_chapters,
        max_words=args.max_words,
        full_weight_tokens=args.full_weight_tokens,
        min_uppercase_count=args.min_uppercase_count,
        min_uppercase_share=args.min_uppercase_share,
        generator="wordfreq.corpora.build_openstax",
    )
    generation = payload["generation"]
    generation["books_pinned"] = {book.slug: book.commit for book in get_books(args.corpus)}

    frequencies = payload["global_word_frequency"]
    print(f"\nCorpus: {args.corpus}")
    print(f"  chapters analyzed: {len(analyses):,}")
    print(f"  tokens counted:    {generation['total_tokens']:,}")
    print(f"  unique words:      {payload['total_unique_words']:,}")
    print(f"  words written:     {len(frequencies):,}")
    print(f"\n  Top {args.top} words:")
    for rank, (word, value) in enumerate(list(frequencies.items())[: args.top], start=1):
        print(f"    {rank:>3}. {word:<16} {value:,}")

    if args.dry_run:
        print("\n(dry run; nothing written)")
        return 0

    output_path = args.output or Path(constants.WORDFREQ_DATA_DIR) / f"{args.corpus}.json"
    write_corpus_json(payload, str(output_path))
    print(f"\nWrote {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
