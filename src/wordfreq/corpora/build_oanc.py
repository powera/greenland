#!/usr/bin/python3

"""Generate an OANC subcorpus word-frequency JSON from downloaded texts.

    PYTHONPATH=src python src/wordfreq/corpora/download_oanc.py
    PYTHONPATH=src python src/wordfreq/corpora/build_oanc.py --phrases-from-db

Reads the primary texts ``download_oanc.py`` cached for one subcorpus, cleans
them (:mod:`wordfreq.corpora.oanc_text`), and writes
``data/wordfreq/oanc_<subcorpus>.json`` in the format
``wordfreq.frequency.importer`` expects.  Everything after text extraction is
the shared ``frequency_build`` code, as for every other corpus.

Only ``slate`` is supported so far: 4,531 Slate magazine articles from
1996-2000 (~4.2M words), for modern general-audience American prose -- the
register where "charisma", "meticulous" and "pristine" occur and the book
corpora cannot supply them.  About a sixth of the articles are the daily
"Today's Papers" press roundup, which is formulaic ("leads with", "fronts")
and full of paper abbreviations (NYT, LAT, USAT); they are counted like any
other article.  Spoken subcorpora such as Switchboard are transcripts and will
need their own cleaning before they are added here.

No network.  No database access either, unless ``--phrases-from-db`` is passed:
that reads the multi-word lemma forms so "credit card" is counted as one token.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import constants
from agents.common.common_args import add_backend_args, get_data_source_config
from wordfreq.corpora.download_oanc import default_cache_dir
from wordfreq.corpora.frequency_build import (
    DEFAULT_MIN_NAME_COUNT,
    DEFAULT_MIN_UPPERCASE_COUNT,
    DEFAULT_MIN_UPPERCASE_SHARE,
    BookAnalysis,
    analyze_book,
    build_corpus_payload,
    write_corpus_json,
)
from wordfreq.corpora.oanc_text import iter_documents

logger = logging.getLogger(__name__)

SUPPORTED_SUBCORPORA = ("slate",)

# 4,531 articles, more than SCOTUS's ~1,500 opinions, so at least as many
# documents are required before a word counts as corpus vocabulary rather
# than one article's subject.
DEFAULT_MIN_DOCUMENTS = 8

# Below this a document is a stub (a correction, a one-paragraph note).
DEFAULT_MIN_CHARS = 500

# A Slate article averages under 1,000 words; a long feature runs to ~3,000.
# Matches the WPA interviews, which are a similar length.
DEFAULT_FULL_WEIGHT_TOKENS = 1500

# Longer than the 15000 of the book corpora (see build_scotus.DEFAULT_MAX_WORDS):
# the vocabulary this corpus is for -- meticulous, pristine, conundrum -- ranks
# 15000-20000 here, so a 15000 list would cut exactly those words.  About 25,600
# words pass the 8-document minimum, so the list fills.
DEFAULT_MAX_WORDS = 20000


def corpus_name(subcorpus: str) -> str:
    """The corpus key, also the output file stem: ``oanc_slate``."""
    return f"oanc_{subcorpus}"


def _load_phrases(args: argparse.Namespace) -> Dict[str, int]:
    """Build the multi-word phrase index from the selected data source."""
    from storage.backend import create_session
    from wordfreq.corpora.lemma_phrases import load_phrase_index

    session = create_session(get_data_source_config(args))
    try:
        return load_phrase_index(session, include_periphrastic=args.join_periphrastic)
    finally:
        session.close()


def analyze_subcorpus(
    subcorpus_dir: Path,
    *,
    min_chars: int = DEFAULT_MIN_CHARS,
    phrases: Optional[Dict[str, int]] = None,
) -> List[BookAnalysis]:
    """Analyze every cached document of one subcorpus.

    Args:
        subcorpus_dir: ``<cache>/<subcorpus>`` as written by ``download_oanc``.
        min_chars: Skip documents shorter than this once cleaned.
        phrases: Multi-word forms to count as single tokens.

    Returns:
        One :class:`BookAnalysis` per document.
    """
    analyses: List[BookAnalysis] = []
    for document in iter_documents(subcorpus_dir, min_chars=min_chars):
        analyses.append(analyze_book(document.slug, document.text, phrases=phrases))
        if len(analyses) % 1000 == 0:
            logger.info("%d documents analyzed", len(analyses))
    return analyses


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--subcorpus",
        choices=SUPPORTED_SUBCORPORA,
        default="slate",
        help="OANC subcorpus to build (default: slate)",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help=f"OANC cache directory (default: {default_cache_dir()})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path (default: data/wordfreq/oanc_<subcorpus>.json)",
    )
    parser.add_argument(
        "--max-words",
        type=int,
        default=DEFAULT_MAX_WORDS,
        help=f"Words to keep (default: {DEFAULT_MAX_WORDS})",
    )
    parser.add_argument(
        "--min-documents",
        type=int,
        default=DEFAULT_MIN_DOCUMENTS,
        help=f"Documents a word must appear in (default: {DEFAULT_MIN_DOCUMENTS})",
    )
    parser.add_argument(
        "--min-chars",
        type=int,
        default=DEFAULT_MIN_CHARS,
        help=f"Skip documents shorter than this (default: {DEFAULT_MIN_CHARS})",
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
        help=f"Length at which a document gets full weight (default: {DEFAULT_FULL_WEIGHT_TOKENS})",
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

    name = corpus_name(args.subcorpus)
    subcorpus_dir = (args.source_dir or default_cache_dir()) / args.subcorpus
    if not subcorpus_dir.is_dir():
        logger.error(
            "Subcorpus not found: %s (run download_oanc.py --subcorpora %s)",
            subcorpus_dir,
            args.subcorpus,
        )
        return 1

    phrases: Optional[Dict[str, int]] = None
    if args.phrases_from_db:
        phrases = _load_phrases(args)
        logger.info("Phrase index: %d multi-word forms", len(phrases))

    analyses = analyze_subcorpus(subcorpus_dir, min_chars=args.min_chars, phrases=phrases)
    if not analyses:
        logger.error("No documents could be read from %s", subcorpus_dir)
        return 1

    payload = build_corpus_payload(
        analyses,
        corpus_name=name,
        min_books=args.min_documents,
        max_words=args.max_words,
        min_name_count=args.min_name_count,
        full_weight_tokens=args.full_weight_tokens,
        min_uppercase_count=args.min_uppercase_count,
        min_uppercase_share=args.min_uppercase_share,
        generator="wordfreq.corpora.build_oanc",
    )

    frequencies = payload["global_word_frequency"]
    print(f"\nCorpus: {name}")
    print(f"  documents analyzed: {len(analyses):,}")
    print(f"  tokens counted:     {payload['generation']['total_tokens']:,}")
    print(f"  unique words:       {payload['total_unique_words']:,}")
    print(f"  words written:      {len(frequencies):,}")
    print(f"\n  Top {args.top} words:")
    for rank, (word, value) in enumerate(list(frequencies.items())[: args.top], start=1):
        print(f"    {rank:>3}. {word:<16} {value:,}")

    if args.dry_run:
        print("\n(dry run; nothing written)")
        return 0

    output_path = args.output or Path(constants.WORDFREQ_DATA_DIR) / f"{name}.json"
    write_corpus_json(payload, str(output_path))
    print(f"\nWrote {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
