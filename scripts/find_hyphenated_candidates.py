#!/usr/bin/env python3
"""Report the hyphenated compounds the corpora contain, for curation.

The corpus tokenizer splits "non-linear" into "non" and "linear" on purpose (see
``wordfreq.corpora.gutenberg_text``), and the cost of that shows up in the
frequency list: ``non`` ranks 301 and ``self`` 381, with ``re``, ``pre``,
``anti``, ``semi``, ``multi`` and ``ex`` all inside the top 4000.  None is a
lemma, none is excluded; each is a fragment of a compound nobody counted.

Teaching the tokenizer to keep those compounds cannot come first.  The phrase
index joins only what the database already holds, so the lemmas have to exist
before the tokenizer can preserve them.  This script is the discovery step: it
re-reads the cached corpus source text, where the hyphens survive, and reports
what is actually attested.

It reads only, and writes nothing anywhere.  The output is a wordlist to curate
by hand and paste into an import script.

Usage::

    PYTHONPATH=src python scripts/find_hyphenated_candidates.py
    PYTHONPATH=src python scripts/find_hyphenated_candidates.py --corpus gutenberg
    PYTHONPATH=src python scripts/find_hyphenated_candidates.py --min-documents 5 --limit 500
    PYTHONPATH=src python scripts/find_hyphenated_candidates.py --format wordlist

The three sources are the ones with cached text locally:

* ``gutenberg`` -- the downloaded books, all five book-list corpora by default.
* ``scotus`` -- the cached CAP case JSON, which is where legal compounds
  ("so-called", "well-settled", "cross-examination") live.
* ``wikipedia`` -- needs the dump snapshot at ``constants.WIKI_CORPUS_BASE_PATH``
  and is skipped with a warning when that is not mounted, since it is an
  external drive.

Words the database already accounts for are excluded, so the report is a list of
things to add rather than a census.  That check is a local database read; pass
``--no-exclude-known`` to skip it.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import constants
from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig
from wordfreq.corpora.book_lists import get_book_list, get_corpus_names
from wordfreq.corpora.download_gutenberg import text_path
from wordfreq.corpora.download_scotus import default_cache_dir as scotus_cache_dir
from wordfreq.corpora.gutenberg_text import strip_gutenberg_boilerplate
from wordfreq.corpora.hyphenated import (
    Document,
    HyphenatedCandidate,
    HyphenatedStats,
    rank_candidates,
    scan_source,
)
from wordfreq.corpora.scotus_text import iter_opinions

logger = logging.getLogger("find_hyphenated_candidates")

# The SCOTUS builder's own floors, so this scan sees the same text the corpus
# does rather than a wider or narrower slice of it.
SCOTUS_MIN_CHARS = 2000
SCOTUS_MIN_YEAR = 1950

SOURCE_NAMES = ("gutenberg", "scotus", "wikipedia")


def gutenberg_documents(cache_dir: Path) -> Iterator[Document]:
    """Every cached book across all Gutenberg book lists, deduplicated.

    A book may appear in more than one list; it is yielded once, or its
    compounds would be counted twice for no reason.
    """
    seen: set[int] = set()
    for corpus_name in get_corpus_names():
        book_list = get_book_list(corpus_name)
        for book in book_list.books:
            if book.gutenberg_id in seen:
                continue
            seen.add(book.gutenberg_id)
            path = text_path(cache_dir, book.gutenberg_id)
            if not path.exists():
                logger.debug("not cached, skipping: %s", path)
                continue
            raw_text = path.read_text(encoding="utf-8", errors="replace")
            # The same strip analyze_book performs. Without it the licence
            # header dominates the report: "re-use", "machine-readable",
            # "non-profit" and "e-mail" appear in every single book because
            # Project Gutenberg's boilerplate says so, not because the
            # 19th-century novels do.
            yield book.slug, strip_gutenberg_boilerplate(raw_text)


def scotus_documents(cache_dir: Path) -> Iterator[Document]:
    """Every opinion in every cached CAP case."""
    for path in sorted(cache_dir.glob("case_*.json")):
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            logger.warning("%s: unreadable, skipping", path)
            continue
        for opinion in iter_opinions(case, min_chars=SCOTUS_MIN_CHARS, min_year=SCOTUS_MIN_YEAR):
            yield opinion.slug, opinion.text


def wikipedia_documents() -> Iterator[Document]:
    """Every article of every Wikipedia corpus, deduplicated by title.

    Imported lazily: ``build_wikipedia`` reaches the dump snapshot at import
    time, and that lives on an external drive.
    """
    from wordfreq.corpora.build_wikipedia import (
        WIKIPEDIA_CORPORA,
        slugify_title,
        wikitext_to_plain_text,
    )
    from wordfreq.corpora.wikipedia.article_lists import flatten
    from wordfreq.corpora.wikipedia.wiki_dump import WikiLoader

    loader = WikiLoader()
    seen: set[str] = set()
    for corpus in WIKIPEDIA_CORPORA.values():
        for title in flatten(corpus.articles):
            if title in seen:
                continue
            seen.add(title)
            try:
                wikitext = loader.get_text_from_page(title)
            except (ValueError, RuntimeError) as error:
                logger.debug("%s: %s", title, error)
                continue
            text = wikitext_to_plain_text(wikitext, title)
            if text:
                yield slugify_title(title), text


def known_words(config: DataSourceConfig) -> List[str]:
    """Every English surface form the database already accounts for.

    Reuses the same four columns the import preflight consults
    (``storage.queries.lemma.filter_existing_english_words``), so a compound
    this reports is one that path would also treat as new.
    """
    from storage.models.imports import WordExclusion
    from storage.models.schema import DerivativeForm, Lemma
    from storage.models.variant_form import VariantForm

    session = create_session(config)
    try:
        words: List[str] = []
        words.extend(text for (text,) in session.query(Lemma.lemma_text).all() if text)
        words.extend(
            text
            for (text,) in session.query(DerivativeForm.derivative_form_text)
            .filter(DerivativeForm.language_code == "en")
            .all()
            if text
        )
        words.extend(
            text
            for (text,) in session.query(VariantForm.variant_form_text)
            .filter(VariantForm.language_code == "en")
            .all()
            if text
        )
        words.extend(
            text
            for (text,) in session.query(WordExclusion.excluded_word)
            .filter(WordExclusion.language_code == "en")
            .all()
            if text
        )
        return words
    finally:
        session.close()


def collect(
    sources: Sequence[str],
    *,
    gutenberg_dir: Path,
    scotus_dir: Path,
) -> Dict[str, HyphenatedStats]:
    """Scan each requested source, skipping any whose data is not present."""
    stats_by_corpus: Dict[str, HyphenatedStats] = {}

    if "gutenberg" in sources:
        if gutenberg_dir.exists():
            stats_by_corpus["gutenberg"] = scan_source(
                lambda: gutenberg_documents(gutenberg_dir), name="gutenberg"
            )
        else:
            logger.warning("Gutenberg cache not found at %s, skipping", gutenberg_dir)

    if "scotus" in sources:
        if scotus_dir.exists():
            stats_by_corpus["scotus"] = scan_source(
                lambda: scotus_documents(scotus_dir), name="scotus"
            )
        else:
            logger.warning("SCOTUS cache not found at %s, skipping", scotus_dir)

    if "wikipedia" in sources:
        if Path(constants.WIKI_CORPUS_BASE_PATH).exists():
            stats_by_corpus["wikipedia"] = scan_source(wikipedia_documents, name="wikipedia")
        else:
            logger.warning(
                "Wikipedia snapshot not mounted at %s, skipping",
                constants.WIKI_CORPUS_BASE_PATH,
            )

    return stats_by_corpus


def print_table(candidates: Sequence[HyphenatedCandidate], limit: Optional[int]) -> None:
    shown = candidates[:limit] if limit else candidates
    print(f"{'compound':<32} {'docs':>6} {'count':>7}  corpora")
    print("-" * 72)
    for candidate in shown:
        print(
            f"{candidate.text:<32} {candidate.documents:>6} {candidate.count:>7}  "
            f"{','.join(candidate.corpora)}"
        )
    print("-" * 72)
    print(f"{len(shown)} shown of {len(candidates)} candidates")


def print_wordlist(candidates: Sequence[HyphenatedCandidate], limit: Optional[int]) -> None:
    """Print a paste-ready Python list for an import script."""
    shown = candidates[:limit] if limit else candidates
    print("WORDS: Sequence[str] = (")
    for candidate in shown:
        print(f'    "{candidate.text}",  # {candidate.documents} docs, {candidate.count} uses')
    print(")")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--corpus",
        action="append",
        choices=SOURCE_NAMES,
        help="Corpus to scan; repeatable. Default: all three.",
    )
    parser.add_argument(
        "--min-count", type=int, default=5, help="Minimum pooled occurrences (default: 5)"
    )
    parser.add_argument(
        "--min-documents",
        type=int,
        default=3,
        help="Minimum distinct documents (default: 3). The spread filter that "
        "separates vocabulary from one author's habit.",
    )
    parser.add_argument(
        "--min-corpora", type=int, default=1, help="Minimum corpora attesting it (default: 1)"
    )
    parser.add_argument("--limit", type=int, help="Show at most this many candidates")
    parser.add_argument(
        "--format",
        choices=("table", "wordlist"),
        default="table",
        help="table for review, wordlist to paste into an import script",
    )
    parser.add_argument(
        "--no-exclude-known",
        action="store_true",
        help="Include compounds the database already accounts for",
    )
    parser.add_argument(
        "--gutenberg-dir",
        type=Path,
        default=Path(constants.GUTENBERG_CACHE_DIR),
        help="Directory of cached Gutenberg .txt files",
    )
    parser.add_argument(
        "--scotus-dir", type=Path, default=None, help="Directory of cached case_*.json files"
    )
    parser.add_argument("--sqlite-path", default="data/wordfreq/linguistics.sqlite")
    parser.add_argument("--output", type=Path, help="Write the report here instead of stdout")
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    sources = args.corpus or list(SOURCE_NAMES)
    stats_by_corpus = collect(
        sources,
        gutenberg_dir=args.gutenberg_dir,
        scotus_dir=args.scotus_dir or scotus_cache_dir(),
    )
    if not stats_by_corpus:
        logger.error("No corpus data available. Nothing scanned.")
        return 1

    exclude: List[str] = []
    if not args.no_exclude_known:
        config = DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=args.sqlite_path)
        exclude = known_words(config)
        logger.info("Excluding %d words the database already accounts for", len(exclude))

    candidates = rank_candidates(
        stats_by_corpus,
        min_count=args.min_count,
        min_documents=args.min_documents,
        min_corpora=args.min_corpora,
        exclude=exclude,
    )

    for corpus_name, stats in sorted(stats_by_corpus.items()):
        logger.info(
            "%s: %d documents, %d distinct compounds",
            corpus_name,
            stats.documents_scanned,
            len(stats.counts),
        )

    handle = args.output.open("w", encoding="utf-8") if args.output else None
    try:
        if handle:
            original_stdout = sys.stdout
            sys.stdout = handle
        if args.format == "wordlist":
            print_wordlist(candidates, args.limit)
        else:
            print_table(candidates, args.limit)
    finally:
        if handle:
            sys.stdout = original_stdout
            handle.close()
            logger.info("Wrote %s", args.output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
