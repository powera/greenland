#!/usr/bin/python3

"""Generate a Wikipedia corpus JSON file from a dump snapshot.

    PYTHONPATH=src python src/wordfreq/corpora/build_wikipedia.py --corpus wiki_arts
    PYTHONPATH=src python src/wordfreq/corpora/build_wikipedia.py --corpus wiki_society
    PYTHONPATH=src python src/wordfreq/corpora/build_wikipedia.py --corpus wiki_history

Reads the articles named in ``wordfreq.corpora.wikipedia.article_lists`` out
of a downloaded Wikimedia snapshot, parses each one's wikitext down to running
prose, separates proper nouns from ordinary vocabulary, and writes
``data/wordfreq/<corpus>.json`` in the format ``wordfreq.frequency.importer``
expects.

Eight corpora are buildable, listed in :data:`WIKIPEDIA_CORPORA`:

* ``wiki_math`` -- 299 mathematics articles, which reach the vocabulary a
  general sample only touches ("theorem", "integer", "coefficient").
* ``wiki_geography`` -- 1204 Level 4 geography articles, which go from the
  continents down to their rivers, ranges and cities.
* ``wiki_biology`` -- 1004 Level 4 organism and anatomy articles, which is
  where the ordinary names of plants and animals come from.
* ``wiki_modern_life`` -- 1200 Level 4 everyday-life and technology articles,
  the vocabulary of modern material life the older corpora cannot have.
* ``wiki_arts`` -- 703 Level 4 arts articles, whose critical metalanguage
  ("narrative", "genre", "counterpoint") the book corpora do not supply: they
  *are* literature, and narrative English is not the vocabulary used to write
  *about* literature.
* ``wiki_society`` -- 1369 Level 4 society, philosophy and religion articles,
  the abstract institutional vocabulary of law, politics and belief.
* ``wiki_physical_science`` -- 1317 Level 4 physical science and molecular
  biology articles, covering the process vocabulary ("oxidize", "orbit",
  "decay") that wiki_biology's organism articles never reach.
* ``wiki_history`` -- 2606 Level 4 history and biography articles, the
  connective prose of historical narrative.

These replace the former ``wiki_vital``, which was the 1000-article Level 3
list.  Five of its eleven sections were already covered in depth by the Level 4
corpora; the four new corpora cover the rest, at roughly six times the article
count.  Its Health and medicine section is deliberately not replaced: the Level
4 expansion of it is named drugs, syndromes and procedures, a technical
register that helps no learner.

The third builder alongside ``build_gutenberg.py`` and ``build_scotus.py``.
Everything after text extraction is shared: all three call
``frequency_build.analyze_book`` and ``build_corpus_payload``, so proper-noun
detection, per-document weighting and the output format are the same code.

The unit of analysis is the *article*.  Articles differ enormously in length --
"Science" runs to tens of thousands of words while "0" is a few hundred -- so
the per-document mean is what stops the long ones deciding the corpus's
vocabulary, exactly as it stops one long novel in the book corpora.

No network: unlike the other two builders there is no download step to pair
with this one, because Wikipedia is taken from a single snapshot fetched by
hand.  Point ``constants.WIKI_CORPUS_BASE_PATH`` at it, or pass ``--corpus-base``.
The snapshot must have been indexed once (``--build-index``) before articles
can be looked up by title.

No database access either, unless ``--phrases-from-db`` is passed: that reads
the multi-word lemma forms so "credit card" is counted as one token rather
than inflating "credit" and "card".
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import constants
from agents.common.common_args import add_backend_args, get_data_source_config
from wordfreq.corpora.frequency_build import (
    DEFAULT_MIN_NAME_COUNT,
    DEFAULT_MIN_UPPERCASE_COUNT,
    DEFAULT_MIN_UPPERCASE_SHARE,
    BookAnalysis,
    analyze_book,
    book_report_rows,
    build_corpus_payload,
    write_corpus_json,
)
from wordfreq.corpora.wikipedia.article_lists import flatten, load_list, load_lists
from wordfreq.corpora.wikipedia.wiki_dump import WikiLoader
from wordfreq.corpora.wikipedia.wiki_text import wikitext_to_plain_text

logger = logging.getLogger(__name__)

# Below this a "page" is a stub or a disambiguation list -- a few sentences and
# a set of links, with no running prose to measure.
DEFAULT_MIN_CHARS = 1000

# Articles are far shorter than novels, so the Gutenberg default of 20000
# tokens would down-weight nearly every one.  A substantial vital article runs
# to about 5000 tokens of prose once apparatus is stripped.
DEFAULT_FULL_WEIGHT_ARTICLE_TOKENS = 2500


class WikipediaCorpus(NamedTuple):
    """One corpus buildable from a list of article titles.

    Attributes:
        name: Corpus name, and the stem of its JSON file.
        articles: Grouped article titles making up the corpus.
        min_articles: Articles a word must appear in to be counted.
        max_words: Words to keep.
        description: What the corpus covers.
    """

    name: str
    articles: Dict[str, List[str]]
    min_articles: int
    max_words: int
    description: str


# Three corpora span two upstream lists each.  In every case the two are after
# the same register and neither is large enough alone, and the group names stay
# prefixed so a gap in either list is still visible.
#
# Everyday life + technology: the vocabulary of modern material life --
# appliances, clothing, sport, computing, transport -- which the book corpora
# predate and which encyclopedic prose about history and science never reaches.
MODERN_LIFE_ARTICLES: Dict[str, List[str]] = load_lists(
    "everyday_life", "technology", prefix_groups=True
)

# Society + philosophy and religion: abstract institutional vocabulary -- law,
# politics, economics, ethics, belief -- that no other corpus here reaches.
SOCIETY_ARTICLES: Dict[str, List[str]] = load_lists(
    "society", "philosophy_religion", prefix_groups=True
)

# Physical sciences + molecular biology: wiki_biology covers organisms and
# anatomy only, so the process vocabulary of the physical and molecular
# sciences -- oxidize, dissolve, orbit, pressure, decay -- had no corpus.
PHYSICAL_SCIENCE_ARTICLES: Dict[str, List[str]] = load_lists(
    "physical_sciences", "molecular_biology", prefix_groups=True
)

# History + people: a period's prose and its actors' biographies are the same
# register, and the biography list is mostly proper nouns, which analyze_book
# separates per document.  What is left is the connective vocabulary of
# historical narrative -- reign, treaty, siege, dynasty, revolt.
HISTORY_ARTICLES: Dict[str, List[str]] = load_lists("history", "people", prefix_groups=True)


WIKIPEDIA_CORPORA: Dict[str, WikipediaCorpus] = {
    "wiki_math": WikipediaCorpus(
        name="wiki_math",
        articles=load_list("math"),
        # 299 documents rather than 1000, so the vital list's threshold would
        # ask a word to reach a far larger share of the corpus.  Scaled to keep
        # roughly the same proportion.
        min_articles=5,
        # A single register with a small vocabulary: past a few thousand words
        # the list is proper nouns and one-article jargon rather than
        # mathematical English.
        max_words=4000,
        description="Mathematics in depth, from arithmetic to category theory",
    ),
    "wiki_geography": WikipediaCorpus(
        name="wiki_geography",
        articles=load_list("geography"),
        # 1204 documents, the same order as the vital list, so the same
        # threshold applies.
        min_articles=15,
        # The narrowest subject matter of the three: a river article and a city
        # article share their descriptive vocabulary and little else, so past a
        # few thousand words the list is place names rather than English.
        max_words=4500,
        description="Wikipedia's 1204 Level 4 geography articles, from continents to cities",
    ),
    "wiki_biology": WikipediaCorpus(
        name="wiki_biology",
        articles=load_list("biology"),
        # 1004 documents, so the vital list's threshold carries over.
        min_articles=15,
        # Mostly the names of organisms, which are proper-noun-like and shared
        # between few articles: a beetle article and a fern article have little
        # vocabulary in common past the anatomical terms.
        max_words=4500,
        description="Wikipedia's Level 4 organisms and anatomy articles",
    ),
    "wiki_modern_life": WikipediaCorpus(
        name="wiki_modern_life",
        articles=MODERN_LIFE_ARTICLES,
        # 1200 documents across two lists, the largest of the Wikipedia
        # corpora, so the vital list's threshold applies unchanged.
        min_articles=15,
        # Two everyday registers rather than one technical one, so the tail
        # stays ordinary English further down than wiki_math's does.
        max_words=5000,
        description="Wikipedia's Level 4 everyday-life and technology articles",
    ),
    "wiki_arts": WikipediaCorpus(
        name="wiki_arts",
        articles=load_list("arts"),
        # 703 documents, so the threshold is scaled down from the 15 the
        # thousand-document lists use, in the same proportion wiki_math's is.
        min_articles=11,
        # The critical metalanguage this corpus exists for -- narrative, genre,
        # motif, counterpoint, chiaroscuro -- is ordinary educated English and
        # its tail stays ordinary further down than a technical corpus's.
        max_words=5000,
        description="Wikipedia's Level 4 arts articles, from architecture to film",
    ),
    "wiki_society": WikipediaCorpus(
        name="wiki_society",
        articles=SOCIETY_ARTICLES,
        # 1369 documents across two lists, the same order as the other large
        # corpora, so their threshold applies unchanged.
        min_articles=15,
        # Abstract institutional prose, which repeats a broad vocabulary rather
        # than a narrow technical one, so its tail is thicker than wiki_math's.
        max_words=5500,
        description="Wikipedia's Level 4 society, philosophy and religion articles",
    ),
    "wiki_physical_science": WikipediaCorpus(
        name="wiki_physical_science",
        articles=PHYSICAL_SCIENCE_ARTICLES,
        # 1317 documents across two lists.
        min_articles=15,
        # Largely named compounds, particles and reactions, which are
        # proper-noun-like and shared between few articles, so the useful yield
        # sits in the first few thousand words as wiki_math's does.
        max_words=4000,
        description="Wikipedia's Level 4 physical science and molecular biology articles",
    ),
    "wiki_history": WikipediaCorpus(
        name="wiki_history",
        articles=HISTORY_ARTICLES,
        # 2606 documents across two lists, the largest corpus here, so a word
        # must reach more of them than in the thousand-document lists.
        min_articles=30,
        # Overwhelmingly proper nouns once past the connective prose, and
        # analyze_book separates those per document, so the ordinary-English
        # tail thins out early.
        max_words=4500,
        description="Wikipedia's Level 4 history and biography articles",
    ),
}

DEFAULT_CORPUS = "wiki_arts"


def _load_phrases(args: argparse.Namespace) -> Dict[str, int]:
    """Build the multi-word phrase index from the selected data source."""
    from storage.backend import create_session
    from wordfreq.corpora.lemma_phrases import load_phrase_index

    session = create_session(get_data_source_config(args))
    try:
        return load_phrase_index(session, include_periphrastic=args.join_periphrastic)
    finally:
        session.close()


def slugify_title(title: str) -> str:
    """Key for one article in the corpus JSON."""
    return title.replace(" ", "_")


def analyze_articles(
    loader: WikiLoader,
    titles: List[str],
    *,
    min_chars: int = DEFAULT_MIN_CHARS,
    phrases: Optional[Dict[str, int]] = None,
) -> Tuple[List[BookAnalysis], List[str]]:
    """Read, parse and analyze each named article.

    Args:
        loader: An indexed snapshot to read pages from.
        titles: Article titles to look up.
        min_chars: Skip articles shorter than this once parsed.
        phrases: Multi-word forms to count as single tokens.

    Returns:
        ``(analyses, missing)`` -- one :class:`BookAnalysis` per article that
        was found and long enough, and the titles that were not.  A miss is
        reported rather than raised: an article renamed since the snapshot was
        taken should cost the corpus one document, not the whole run.
    """
    analyses: List[BookAnalysis] = []
    missing: List[str] = []
    for index, title in enumerate(titles, start=1):
        try:
            wikitext = loader.get_text_from_page(title)
        except (ValueError, RuntimeError) as error:
            logger.warning("%s: %s", title, error)
            missing.append(title)
            continue

        text = wikitext_to_plain_text(wikitext, title)
        if len(text) < min_chars:
            logger.warning("%s: %d chars of prose, skipping", title, len(text))
            missing.append(title)
            continue

        analyses.append(analyze_book(slugify_title(title), text, phrases=phrases))
        if index % 100 == 0:
            logger.info("[%d/%d] articles read", index, len(titles))
    return analyses, missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        choices=sorted(WIKIPEDIA_CORPORA),
        default=DEFAULT_CORPUS,
        help=f"Corpus to build (default: {DEFAULT_CORPUS})",
    )
    parser.add_argument(
        "--corpus-base",
        type=Path,
        default=None,
        help=f"Snapshot directory (default: {constants.WIKI_CORPUS_BASE_PATH})",
    )
    parser.add_argument(
        "--corpus-prefix",
        default=None,
        help=f"Dump file prefix (default: {constants.WIKI_CORPUS_PREFIX})",
    )
    parser.add_argument(
        "--offset-dir",
        type=Path,
        default=None,
        help="Where the sharded SQLite index lives (default: <corpus-base>/offset). "
        "Build to local disk when the snapshot is on an exFAT drive, which cannot "
        "host SQLite writes, then copy the finished index back; reads work there.",
    )
    parser.add_argument(
        "--build-index",
        action="store_true",
        help="Build the title offset index from the snapshot, then exit. "
        "Required once per snapshot before any article can be read.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path (default: data/wordfreq/<corpus>.json)",
    )
    parser.add_argument(
        "--section",
        action="append",
        help="Limit to one section of the corpus's article list " "(repeatable; default: all)",
    )
    parser.add_argument(
        "--max-words",
        type=int,
        default=None,
        help="Words to keep (default: the corpus's own setting)",
    )
    parser.add_argument(
        "--min-articles",
        type=int,
        default=None,
        help="Articles a word must appear in (default: the corpus's own setting)",
    )
    parser.add_argument(
        "--min-chars",
        type=int,
        default=DEFAULT_MIN_CHARS,
        help=f"Skip articles with less prose than this (default: {DEFAULT_MIN_CHARS})",
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
        default=DEFAULT_FULL_WEIGHT_ARTICLE_TOKENS,
        help=f"Length at which an article gets full weight "
        f"(default: {DEFAULT_FULL_WEIGHT_ARTICLE_TOKENS})",
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
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write per-article token and name counts to this JSON file",
    )
    parser.add_argument("--top", type=int, default=25, help="Top words to print")
    parser.add_argument("--dry-run", action="store_true", help="Report without writing")
    add_backend_args(parser)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    corpus = WIKIPEDIA_CORPORA[args.corpus]
    min_articles = args.min_articles if args.min_articles is not None else corpus.min_articles
    max_words = args.max_words if args.max_words is not None else corpus.max_words

    offset_dir = str(args.offset_dir) if args.offset_dir is not None else None
    loader = WikiLoader(offset_dir=offset_dir)
    if args.corpus_base is not None:
        loader.set_corpus_base(str(args.corpus_base), args.corpus_prefix, offset_dir)
    elif args.corpus_prefix is not None:
        loader.set_corpus_base(loader.corpus_base, args.corpus_prefix, offset_dir)

    if args.build_index:
        logger.info("Building the title index for %s", loader.dump_file)
        loader.build_offset_index()
        return 0

    if not loader.is_indexed():
        logger.error(
            "No title index found under %s. Point --corpus-base at a snapshot "
            "and run --build-index once.",
            loader.offset_dir,
        )
        return 1

    if args.section:
        unknown = [section for section in args.section if section not in corpus.articles]
        if unknown:
            logger.error(
                "Unknown section(s) for %s: %s. Available: %s",
                corpus.name,
                ", ".join(unknown),
                ", ".join(sorted(corpus.articles)),
            )
            return 1
        titles = flatten({section: corpus.articles[section] for section in args.section})
    else:
        titles = flatten(corpus.articles)

    phrases: Optional[Dict[str, int]] = None
    if args.phrases_from_db:
        phrases = _load_phrases(args)
        logger.info("Phrase index: %d multi-word forms", len(phrases))

    analyses, missing = analyze_articles(loader, titles, min_chars=args.min_chars, phrases=phrases)
    if not analyses:
        logger.error("No articles could be read from %s", loader.corpus_base)
        return 1

    payload = build_corpus_payload(
        analyses,
        corpus_name=corpus.name,
        min_books=min_articles,
        max_words=max_words,
        min_name_count=args.min_name_count,
        full_weight_tokens=args.full_weight_tokens,
        min_uppercase_count=args.min_uppercase_count,
        min_uppercase_share=args.min_uppercase_share,
        generator="wordfreq.corpora.build_wikipedia",
    )

    frequencies = payload["global_word_frequency"]
    print(f"\nCorpus: {corpus.name}")
    print(f"  articles requested: {len(titles):,}")
    print(f"  articles analyzed:  {len(analyses):,}")
    print(f"  articles missing:   {len(missing):,}")
    print(f"  tokens counted:     {payload['generation']['total_tokens']:,}")
    print(f"  unique words:       {payload['total_unique_words']:,}")
    print(f"  words written:      {len(frequencies):,}")
    print(f"\n  Top {args.top} words:")
    for rank, (word, value) in enumerate(list(frequencies.items())[: args.top], start=1):
        print(f"    {rank:>3}. {word:<16} {value:,}")

    if missing:
        print(f"\n  Missing ({len(missing)}):")
        for title in missing[:20]:
            print(f"    {title}")
        if len(missing) > 20:
            print(f"    ... and {len(missing) - 20} more")

    if args.report:
        import json

        args.report.write_text(
            json.dumps(book_report_rows(analyses), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"\nWrote report to {args.report}")

    if args.dry_run:
        print("\n(dry run; nothing written)")
        return 0

    output_path = args.output or Path(constants.WORDFREQ_DATA_DIR) / f"{corpus.name}.json"
    write_corpus_json(payload, str(output_path))
    print(f"\nWrote {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
