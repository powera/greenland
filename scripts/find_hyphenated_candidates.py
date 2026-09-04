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
    PYTHONPATH=src python scripts/find_hyphenated_candidates.py \
        --format wordlist --category fraction

**The report is sectioned, not one ranked list.**  The first run's output showed
why: a hyphen joins several quite different things, and ranking them together
buried the vocabulary among them.  ``wordfreq.corpora.hyphenated.classify``
separates the sections and its docstring says what each one is; briefly, the
fractions lead (they are wanted at a much earlier level than the rest), the
general vocabulary follows, and after it come the compounds that are really
spellings of a solid word ("north-east" for "northeast"), prefixed bases,
attributive participles ("long-tailed"), hyphenated phrases
("black-and-white"), numbers-plus-units ("five-year"), numerals, and names.
``--limit`` applies within each section, so capping the general list does not
truncate the short ones off the end of the report.

**Case is evidence now.**  Compounds are still counted lowercased, but each
occurrence is recorded as capitalized, lowercase or sentence-initial, exactly as
``gutenberg_text.analyze_text`` records a single word.  That is what the
``proper`` section runs on, and it is why "jean-luc" no longer reaches the
import list.  A capital on a part after the first is treated separately and
needs no minimum, because sentence position cannot force it: that alone
separates "non-Jewish" from "non-fiction".

**The unhyphenated spellings are counted alongside.**  For each two-part
compound a document attests, the same pass counts the solid spelling
("northeast") and the spaced one ("north east").  Where the solid form wins, the
hyphenated one is a ``variant_forms`` row against that lemma rather than a word
to import -- and once it exists as a variant, all three spellings can be counted
together, which was the point of the exercise.

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
    CATEGORY_GENERAL,
    CATEGORY_ORDER,
    DEFAULT_MIN_CASE_EVIDENCE,
    DEFAULT_PROPER_SHARE,
    DEFAULT_SOLID_RATIO,
    Document,
    HyphenatedCandidate,
    HyphenatedStats,
    group_by_category,
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


# What each report section is for, printed above it so the curator does not
# have to reconstruct the reasoning from the module docstring.
CATEGORY_NOTES: Dict[str, str] = {
    "fraction": (
        "Spelled-out fractions. Vocabulary, and wanted well before the level "
        "the general list lands at, so decide these on their own."
    ),
    "general": "Ordinary hyphenated vocabulary: the import list.",
    "solid-variant": (
        "The corpora mostly write these solid. Each is a spelling of that word "
        "-- a variant_forms row against the solid lemma, not a lemma."
    ),
    "prefixed": (
        "A productive prefix on a base. Keep the ones whose whole means "
        "something its parts do not (non-fiction, non-profit); the rest are "
        "just the base, negated."
    ),
    "attributive": (
        "Participles that describe a head noun and mean little alone "
        "(long-tailed). Some are worth holding; most are not."
    ),
    "phrase": (
        "Three or more parts: a phrase written with hyphens (black-and-white, "
        "day-to-day) rather than a compound word."
    ),
    "measure": (
        "A number modifying a unit for one attributive use (a five-year plan). "
        "The words are the number and the unit; nothing here is new."
    ),
    "number": "Spelled-out compound numerals. Arithmetic, not vocabulary.",
    "proper": (
        "Capitalized in the corpora: names, nationalities and proper "
        "adjectives (Jean-Luc, Anglo-Saxon, non-Jewish). Not for this list. "
        "Read it before discarding it, though: a word derived from a name is "
        "capitalized for the same reason a name is, and the case evidence "
        "cannot tell them apart -- non-Euclidean is ordinary mathematical "
        "vocabulary and lands here."
    ),
}


def _format_row(candidate: HyphenatedCandidate) -> str:
    """One candidate as a report line, with its case and spelling evidence."""
    share = candidate.capitalized_share
    case = "n/a" if share is None else f"{share:.2f}"
    spelling = candidate.preferred_spelling
    return (
        f"{candidate.text:<32} {candidate.documents:>6} {candidate.count:>7}  "
        f"{case:>5} {candidate.inner_upper:>5}  "
        f"{candidate.solid:>6} {candidate.spaced:>6}  {spelling:<10} "
        f"{','.join(candidate.corpora)}"
    )


_HEADER = (
    f"{'compound':<32} {'docs':>6} {'count':>7}  "
    f"{'cap':>5} {'inner':>5}  {'solid':>6} {'spaced':>6}  {'prefers':<10} corpora"
)


def print_table(candidates: Sequence[HyphenatedCandidate], limit: Optional[int]) -> None:
    """Print the candidates grouped into sections, fractions first.

    ``limit`` applies per section rather than to the report as a whole: a cap
    meant to keep the general list reviewable should not push the fractions --
    which are few and lead the report -- off the end of it.

    The ``cap`` column is the share of *decided* occurrences written with a
    leading capital, and ``n/a`` means every occurrence opened a sentence, so
    there is no evidence.  ``inner`` counts occurrences capitalized on a later
    part ("non-Jewish"), which position can never force.
    """
    grouped = group_by_category(candidates)
    for category, group in grouped.items():
        shown = group[:limit] if limit else group
        print(f"== {category} ({len(shown)} shown of {len(group)})")
        note = CATEGORY_NOTES.get(category)
        if note:
            print(f"   {note}")
        print()
        print(_HEADER)
        print("-" * len(_HEADER))
        for candidate in shown:
            print(_format_row(candidate))
        print()
    print("-" * len(_HEADER))
    print(f"{len(candidates)} candidates in {len(grouped)} categories")


def print_wordlist(
    candidates: Sequence[HyphenatedCandidate],
    limit: Optional[int],
    *,
    category: str = CATEGORY_GENERAL,
) -> None:
    """Print a paste-ready Python list for an import script.

    One category only -- by default the general vocabulary.  The other sections
    are curation input rather than import lists, and pasting a mixed list into
    an import script is how the names got in last time.
    """
    grouped = group_by_category(candidates)
    group = grouped.get(category, [])
    shown = group[:limit] if limit else group
    print(f"# {category}: {len(shown)} of {len(group)} candidates")
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
        "--category",
        choices=CATEGORY_ORDER,
        default=CATEGORY_GENERAL,
        help=(
            "Which section --format wordlist emits (default: general). The "
            "table format always prints every section."
        ),
    )
    parser.add_argument(
        "--proper-share",
        type=float,
        default=DEFAULT_PROPER_SHARE,
        help=(
            f"Capitalized share above which a compound is a name "
            f"(default: {DEFAULT_PROPER_SHARE})"
        ),
    )
    parser.add_argument(
        "--min-case-evidence",
        type=int,
        default=DEFAULT_MIN_CASE_EVIDENCE,
        help=(
            f"Mid-sentence occurrences needed before the capitalized share is "
            f"trusted (default: {DEFAULT_MIN_CASE_EVIDENCE})"
        ),
    )
    parser.add_argument(
        "--solid-ratio",
        type=float,
        default=DEFAULT_SOLID_RATIO,
        help=(
            f"Solid-spelling share above which a compound is a variant of the "
            f"solid word rather than a lemma (default: {DEFAULT_SOLID_RATIO})"
        ),
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
        proper_share=args.proper_share,
        min_case_evidence=args.min_case_evidence,
        solid_ratio=args.solid_ratio,
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
            print_wordlist(candidates, args.limit, category=args.category)
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
