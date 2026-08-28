#!/usr/bin/python3

"""Generate a Wikipedia corpus JSON file from a dump snapshot.

    PYTHONPATH=src python src/wordfreq/corpora/build_wikipedia.py --corpus wiki_vital
    PYTHONPATH=src python src/wordfreq/corpora/build_wikipedia.py --corpus wiki_math

Reads the articles named in ``wordfreq.corpora.wikipedia.vital_articles`` out
of a downloaded Wikimedia snapshot, parses each one's wikitext down to running
prose, separates proper nouns from ordinary vocabulary, and writes
``data/wordfreq/<corpus>.json`` in the format ``wordfreq.frequency.importer``
expects.

Two corpora are buildable, listed in :data:`WIKIPEDIA_CORPORA`:

* ``wiki_vital`` -- Wikipedia's 1000 vital articles, a general sample of
  modern encyclopedic English.
* ``wiki_math`` -- 299 mathematics articles, which reach the vocabulary a
  general sample only touches ("theorem", "integer", "coefficient").  A strict
  superset of the vital list's 53-title Mathematics section.

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
from wordfreq.corpora.wikipedia.vital_articles import MATH_ARTICLES, VITAL_ARTICLES, flatten
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


WIKIPEDIA_CORPORA: Dict[str, WikipediaCorpus] = {
    "wiki_vital": WikipediaCorpus(
        name="wiki_vital",
        articles=VITAL_ARTICLES,
        # There are 1000 documents here, against 54 books in the 19th-century
        # list, so a word must reach more of them before it counts as corpus
        # vocabulary rather than one article's subject matter.  An article is
        # also narrower than a novel: "Photosynthesis" uses "chloroplast"
        # throughout and no other article uses it at all.
        min_articles=15,
        # Matches the wiki_vital entry in CORPUS_CONFIGS, which is 6000 rather
        # than the books' 10000: encyclopedic prose repeats a narrow register,
        # so its tail is thinner than a novel corpus's at the same rank.
        max_words=6000,
        description="Wikipedia's 1000 vital articles, across eleven topic groups",
    ),
    "wiki_math": WikipediaCorpus(
        name="wiki_math",
        articles=MATH_ARTICLES,
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
}

DEFAULT_CORPUS = "wiki_vital"


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
