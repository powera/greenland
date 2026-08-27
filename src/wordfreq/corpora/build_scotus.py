#!/usr/bin/python3

"""Generate the SCOTUS corpus word-frequency JSON from downloaded opinions.

    PYTHONPATH=src python src/wordfreq/corpora/download_scotus.py --years 1997-2006
    PYTHONPATH=src python src/wordfreq/corpora/build_scotus.py --phrases-from-db

Reads the cached CAP case JSON written by ``download_scotus.py``, extracts and
strips each opinion, separates proper nouns from ordinary vocabulary, and
writes ``data/wordfreq/legal_scotus.json`` in the format
``wordfreq.frequency.importer`` expects.

The counterpart of ``build_gutenberg.py``, which is tied to Gutenberg book lists
and ``<id>.txt`` files.  Everything after text extraction is shared: both
builders call ``frequency_build.analyze_book`` and ``build_corpus_payload``, so
proper-noun detection, per-document weighting and the output format are the
same code.

The unit of analysis is the *opinion*, not the case.  A case carries a majority
and often several dissents and concurrences, each written by a different
Justice; treating them separately is what lets the per-document mean stop one
long opinion from deciding a word's rank, exactly as it stops one long novel
in the Gutenberg corpora.

No network.  No database access either, unless ``--phrases-from-db`` is passed:
that reads the multi-word lemma forms so "credit card" is counted as one token
rather than inflating "credit" and "card".
"""

import argparse
import glob
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import constants
from agents.common.common_args import add_backend_args, get_data_source_config
from wordfreq.corpora.download_scotus import default_cache_dir
from wordfreq.corpora.frequency_build import (
    DEFAULT_FULL_WEIGHT_TOKENS,
    DEFAULT_MIN_NAME_COUNT,
    BookAnalysis,
    analyze_book,
    build_corpus_payload,
    write_corpus_json,
)
from wordfreq.corpora.scotus_text import iter_opinions

logger = logging.getLogger(__name__)

CORPUS_NAME = "legal_scotus"

# Opinions are shorter than novels and there are far more of them: ~1500 from a
# decade of cases against 54 books in the 19th-century list.  A word must
# therefore appear in more documents before it counts as corpus vocabulary
# rather than one case's subject matter.
DEFAULT_MIN_OPINIONS = 8

# Below this an "opinion" is an order or a denial of certiorari: near-pure
# boilerplate with almost no running prose.
DEFAULT_MIN_CHARS = 1000

# The earliest decision year to count.  A modern volume can carry a
# supplemental decree in a decades-old original-jurisdiction case -- Nebraska
# v. Wyoming (1945) and Arizona v. California (1963) both appear in volumes of
# the 2000s -- and that prose is not of the period the corpus measures.
DEFAULT_MIN_YEAR = 1997

# Opinions are a fraction of a novel's length, so the Gutenberg default of
# 20000 tokens would down-weight every one of them.  A long majority opinion
# runs to about 10000 tokens.
DEFAULT_FULL_WEIGHT_OPINION_TOKENS = 4000

# Matches the 19th- and 20th-century book corpora, which this one sits
# alongside in CORPUS_CONFIGS.  It is a larger corpus (~5M tokens) and could
# support a longer list, but a corpus's word count is also its weight in
# combined_rank, and there is no reason for this one to reach further down its
# tail than the novels reach down theirs.
DEFAULT_MAX_WORDS = 10000


def _load_phrases(args: argparse.Namespace) -> Dict[str, int]:
    """Build the multi-word phrase index from the selected data source."""
    from storage.backend import create_session
    from wordfreq.corpora.lemma_phrases import load_phrase_index

    session = create_session(get_data_source_config(args))
    try:
        return load_phrase_index(session, include_periphrastic=args.join_periphrastic)
    finally:
        session.close()


def analyze_cached_opinions(
    cache_dir: Path,
    *,
    min_chars: int = DEFAULT_MIN_CHARS,
    min_year: Optional[int] = DEFAULT_MIN_YEAR,
    include_types: Optional[List[str]] = None,
    phrases: Optional[Dict[str, int]] = None,
) -> List[BookAnalysis]:
    """Analyze every opinion in every cached case.

    Args:
        cache_dir: Directory of ``case_*.json`` files from ``download_scotus``.
        min_chars: Skip opinions shorter than this once stripped.
        min_year: Skip cases decided before this year.
        include_types: Opinion types to keep (``None`` keeps every type).
        phrases: Multi-word forms to count as single tokens.

    Returns:
        One :class:`BookAnalysis` per opinion.
    """
    analyses: List[BookAnalysis] = []
    paths = sorted(cache_dir.glob("case_*.json"))
    for index, path in enumerate(paths, start=1):
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            logger.warning("%s: unreadable, skipping", path)
            continue
        for opinion in iter_opinions(
            case, include_types=include_types, min_chars=min_chars, min_year=min_year
        ):
            analyses.append(analyze_book(opinion.slug, opinion.text, phrases=phrases))
        if index % 100 == 0:
            logger.info("[%d/%d] cases read, %d opinions", index, len(paths), len(analyses))
    return analyses


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help=f"Directory of downloaded cases (default: {default_cache_dir()})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=f"Output JSON path (default: data/wordfreq/{CORPUS_NAME}.json)",
    )
    parser.add_argument(
        "--max-words",
        type=int,
        default=DEFAULT_MAX_WORDS,
        help=f"Words to keep (default: {DEFAULT_MAX_WORDS})",
    )
    parser.add_argument(
        "--min-opinions",
        type=int,
        default=DEFAULT_MIN_OPINIONS,
        help=f"Opinions a word must appear in (default: {DEFAULT_MIN_OPINIONS})",
    )
    parser.add_argument(
        "--min-chars",
        type=int,
        default=DEFAULT_MIN_CHARS,
        help=f"Skip opinions shorter than this (default: {DEFAULT_MIN_CHARS})",
    )
    parser.add_argument(
        "--min-year",
        type=int,
        default=DEFAULT_MIN_YEAR,
        help=f"Skip cases decided before this year (default: {DEFAULT_MIN_YEAR})",
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
        default=DEFAULT_FULL_WEIGHT_OPINION_TOKENS,
        help=f"Length at which an opinion gets full weight "
        f"(default: {DEFAULT_FULL_WEIGHT_OPINION_TOKENS})",
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

    cache_dir = args.source_dir or default_cache_dir()
    if not cache_dir.is_dir():
        logger.error("Cache directory not found: %s", cache_dir)
        return 1

    phrases: Optional[Dict[str, int]] = None
    if args.phrases_from_db:
        phrases = _load_phrases(args)
        logger.info("Phrase index: %d multi-word forms", len(phrases))

    analyses = analyze_cached_opinions(
        cache_dir,
        min_chars=args.min_chars,
        min_year=args.min_year,
        phrases=phrases,
    )
    if not analyses:
        logger.error("No opinions could be read from %s", cache_dir)
        return 1

    payload = build_corpus_payload(
        analyses,
        corpus_name=CORPUS_NAME,
        min_books=args.min_opinions,
        max_words=args.max_words,
        min_name_count=args.min_name_count,
        full_weight_tokens=args.full_weight_tokens,
        generator="wordfreq.corpora.build_scotus",
    )

    frequencies = payload["global_word_frequency"]
    print(f"\nCorpus: {CORPUS_NAME}")
    print(f"  opinions analyzed: {len(analyses):,}")
    print(f"  tokens counted:    {payload['generation']['total_tokens']:,}")
    print(f"  unique words:      {payload['total_unique_words']:,}")
    print(f"  words written:     {len(frequencies):,}")
    print(f"\n  Top {args.top} words:")
    for rank, (word, value) in enumerate(list(frequencies.items())[: args.top], start=1):
        print(f"    {rank:>3}. {word:<16} {value:,}")

    if args.dry_run:
        print("\n(dry run; nothing written)")
        return 0

    output_path = args.output or Path(constants.WORDFREQ_DATA_DIR) / f"{CORPUS_NAME}.json"
    write_corpus_json(payload, str(output_path))
    print(f"\nWrote {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
