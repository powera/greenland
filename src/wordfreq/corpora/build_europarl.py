#!/usr/bin/python3

"""Generate the parliament-debates corpus JSON from selected Europarl chapters.

    PYTHONPATH=src python src/wordfreq/corpora/download_europarl.py
    PYTHONPATH=src python src/wordfreq/corpora/europarl_select.py
    PYTHONPATH=src python src/wordfreq/corpora/build_europarl.py --phrases-from-db

Reads the chapter list written by ``europarl_select.py``, parses those
chapters out of the cached session files, and writes
``data/wordfreq/parliament_debates.json`` through the same
``frequency_build`` path every other builder uses.

The point of the corpus is the vocabulary of *debating* politics -- vote,
coalition, amendment, opposition, minister -- in the register politicians
speak rather than the one legislation is drafted in.  The unit of analysis is
the chapter (one agenda item), for the reason the SCOTUS builder uses the
opinion: it is what lets the per-document mean stop one long debate deciding a
word's rank.

Every speech is counted, whatever language it was given in: the English text
of a speech given in French is a professional translation, and still English
a learner will meet.  The English files cannot say which speeches were given
in English (see :mod:`wordfreq.corpora.europarl_text`), so there is no
native-only variant.

The English is British, and the database's is American, so British spellings
are folded before counting ("programme" counts as "program"); see
:mod:`wordfreq.corpora.british_spelling`.  The American reference is the
``legal_scotus`` vocabulary, joined by the database's English forms under
``--phrases-from-db``.  ``--show-folds N`` prints the folds for review.

Per-document name detection is off (see ``NO_NAME_DETECTION``): capitalized
words count like any other, and ``--min-chapters`` is what keeps one debate's
proper nouns out.

No network.  No database access either, unless ``--phrases-from-db`` is passed.
"""

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Collection, Dict, List, Optional, Set, Tuple

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import constants
from agents.common.common_args import add_backend_args, get_data_source_config
from wordfreq.corpora.british_spelling import build_spelling_map, fold_text, vocabulary
from wordfreq.corpora.download_europarl import default_cache_dir
from wordfreq.corpora.europarl_select import SELECTION_PATH, load_selection
from wordfreq.corpora.europarl_text import read_session, session_path, split_slug
from wordfreq.corpora.frequency_build import (
    DEFAULT_MIN_UPPERCASE_COUNT,
    DEFAULT_MIN_UPPERCASE_SHARE,
    BookAnalysis,
    analyze_book,
    build_corpus_payload,
    write_corpus_json,
)

logger = logging.getLogger(__name__)

CORPUS_NAME = "parliament_debates"

# ~1300 chapters, as legal_scotus has ~1500 opinions: the same floor.
DEFAULT_MIN_CHAPTERS = 8

# Below this a chapter has already been dropped by the selector; kept as a
# second floor for when a language filter empties most of one.
DEFAULT_MIN_WORDS = 300

# A substantial debate runs to 3000-8000 words once the chair's procedure is
# removed.  Shorter chapters count proportionally less.
DEFAULT_FULL_WEIGHT_CHAPTER_TOKENS = 3000

# A topic corpus like wiki_society (5500), not a general one like the novels:
# a corpus's word count is also its weight in combined_rank.
DEFAULT_MAX_WORDS = 5500


# Per-document name detection is off.  It exists for the character who fills
# one novel and appears in no other ("Ahab"), and the min-chapters floor
# already keeps a word confined to a few debates out of the list.  What the
# rule catches here instead is words capitalized in *every* debate --
# "Commission", "European", "Greece" -- which are the corpus's vocabulary.
# No capitalization share exceeds 1.0, so this threshold never fires.
NO_NAME_DETECTION = 1.1

# With name detection off, the people debated about come through: "Barroso"
# (2586), "Prodi", "Poettering", and name particles like "Van" and "De".  They
# sit low in the list, while the capitalized vocabulary worth keeping --
# "European", "Commission", "Greece" (988), "Kosovo" -- ranks higher.  A
# capitalized entry is kept only at or above this rank.  A stopgap for this
# corpus, not a general rule.
DEFAULT_MAX_CAPITALIZED_RANK = 2000


def drop_low_ranked_capitalized(
    frequencies: Dict[str, int], max_rank: int, max_words: Optional[int]
) -> Tuple[Dict[str, int], int]:
    """Drop capitalized entries ranked below ``max_rank``, then cap the list.

    Rank is the entry's position in the full, uncapped list.  "I" is exempt:
    it is capitalized by rule, not because it is a name.

    Returns:
        The filtered frequencies (at most ``max_words``) and how many
        capitalized entries were dropped within them.
    """
    kept: Dict[str, int] = {}
    dropped = 0
    for rank, (word, count) in enumerate(frequencies.items(), start=1):
        if max_words is not None and len(kept) >= max_words:
            break
        if rank > max_rank and word[:1].isupper() and word != "I":
            dropped += 1
            continue
        kept[word] = count
    return kept, dropped


# The American-English reference for spelling folds: a US corpus's vocabulary,
# which needs no database, joined by the database's forms when it is read.
AMERICAN_REFERENCE_CORPUS = "legal_scotus"


def _load_database_inputs(args: argparse.Namespace) -> Tuple[Dict[str, int], Set[str]]:
    """The multi-word phrase index and every English lemma/form spelling."""
    from storage.backend import create_session
    from storage.models.schema import DerivativeForm, Lemma
    from wordfreq.corpora.lemma_phrases import load_phrase_index

    session = create_session(get_data_source_config(args))
    try:
        phrases = load_phrase_index(session, include_periphrastic=args.join_periphrastic)
        spellings = {text.lower() for (text,) in session.query(Lemma.lemma_text) if text}
        spellings.update(
            text.lower()
            for (text,) in session.query(DerivativeForm.derivative_form_text).filter(
                DerivativeForm.language_code == "en"
            )
            if text
        )
        return phrases, spellings
    finally:
        session.close()


def load_reference_vocabulary(corpus: str = AMERICAN_REFERENCE_CORPUS) -> Set[str]:
    """Lowercase vocabulary of a built corpus JSON, empty if it is missing."""
    path = Path(constants.WORDFREQ_DATA_DIR) / f"{corpus}.json"
    if not path.exists():
        logger.warning("spelling reference %s not found", path)
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {word.lower() for word in payload.get("global_word_frequency", {})}


def read_selected_chapters(
    cache_dir: Path, slugs: Collection[str], *, min_words: int = DEFAULT_MIN_WORDS
) -> List[Tuple[str, str]]:
    """``(slug, cleaned text)`` for the named chapters, reading each file once.

    Slugs whose session file is not cached, or which the file no longer
    contains, are logged rather than failing the build.
    """
    wanted: Dict[str, set[str]] = defaultdict(set)
    for slug in slugs:
        session, chapter_id = split_slug(slug)
        wanted[session].add(chapter_id)

    documents: List[Tuple[str, str]] = []
    missing = 0
    for index, session in enumerate(sorted(wanted), start=1):
        path = session_path(cache_dir, session)
        if not path.exists():
            missing += len(wanted[session])
            logger.debug("not cached: %s", path)
            continue
        found = set()
        for chapter in read_session(path):
            if chapter.chapter_id not in wanted[session]:
                continue
            found.add(chapter.chapter_id)
            text = chapter.text()
            if len(text.split()) >= min_words:
                documents.append((chapter.slug, text))
        missing += len(wanted[session] - found)
        if index % 200 == 0:
            logger.info("[%d/%d] sessions read, %d chapters", index, len(wanted), len(documents))
    if missing:
        logger.warning("%d selected chapters were not found in the cache", missing)
    return documents


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help=f"Europarl cache directory (default: {default_cache_dir()})",
    )
    parser.add_argument(
        "--selection",
        type=Path,
        default=SELECTION_PATH,
        help=f"Chapter list from europarl_select.py (default: {SELECTION_PATH.name})",
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
        "--min-chapters",
        type=int,
        default=DEFAULT_MIN_CHAPTERS,
        help=f"Chapters a word must appear in (default: {DEFAULT_MIN_CHAPTERS})",
    )
    parser.add_argument(
        "--min-words",
        type=int,
        default=DEFAULT_MIN_WORDS,
        help=f"Skip chapters shorter than this after filtering (default: {DEFAULT_MIN_WORDS})",
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
    parser.add_argument(
        "--max-capitalized-rank",
        type=int,
        default=DEFAULT_MAX_CAPITALIZED_RANK,
        help=(
            "Drop capitalized entries ranked below this "
            f"(default: {DEFAULT_MAX_CAPITALIZED_RANK})"
        ),
    )
    parser.add_argument(
        "--no-fold-spellings",
        dest="fold_spellings",
        action="store_false",
        help="Count British spellings as words of their own",
    )
    parser.add_argument(
        "--show-folds",
        type=int,
        default=0,
        help="Print this many of the spelling folds applied, for review",
    )
    parser.add_argument("--top", type=int, default=25, help="Top words to print")
    parser.add_argument("--dry-run", action="store_true", help="Report without writing")
    add_backend_args(parser)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    cache_dir: Path = args.source_dir or default_cache_dir()
    if not cache_dir.is_dir():
        logger.error("Cache directory not found: %s", cache_dir)
        return 1
    if not args.selection.exists():
        logger.error("Selection not found: %s; run europarl_select.py first", args.selection)
        return 1

    slugs = load_selection(args.selection)
    logger.info("Selection: %d chapters", len(slugs))

    phrases: Optional[Dict[str, int]] = None
    known_spellings = load_reference_vocabulary()
    if args.phrases_from_db:
        phrases, database_spellings = _load_database_inputs(args)
        known_spellings |= database_spellings
        logger.info("Phrase index: %d multi-word forms", len(phrases))

    documents = read_selected_chapters(cache_dir, slugs, min_words=args.min_words)
    if not documents:
        logger.error("No selected chapters could be read from %s", cache_dir)
        return 1

    spelling_map: Dict[str, str] = {}
    if args.fold_spellings:
        spelling_map = build_spelling_map(
            vocabulary(text for _, text in documents), known_spellings
        )
        logger.info(
            "Spelling folds: %d British spellings, against %d known American ones",
            len(spelling_map),
            len(known_spellings),
        )

    analyses: List[BookAnalysis] = []
    for index, (slug, text) in enumerate(documents, start=1):
        analyses.append(
            analyze_book(
                slug,
                fold_text(text, spelling_map),
                capitalization_ratio=NO_NAME_DETECTION,
                phrases=phrases,
            )
        )
        if index % 500 == 0:
            logger.info("[%d/%d] chapters analyzed", index, len(documents))

    # Built uncapped, so the list can be refilled to --max-words once the
    # low-ranked capitalized entries are dropped.
    payload = build_corpus_payload(
        analyses,
        corpus_name=CORPUS_NAME,
        min_books=args.min_chapters,
        max_words=None,
        full_weight_tokens=args.full_weight_tokens,
        min_uppercase_count=args.min_uppercase_count,
        min_uppercase_share=args.min_uppercase_share,
        generator="wordfreq.corpora.build_europarl",
    )
    payload["global_word_frequency"], dropped = drop_low_ranked_capitalized(
        payload["global_word_frequency"], args.max_capitalized_rank, args.max_words
    )
    payload["generation"]["max_words"] = args.max_words
    payload["generation"]["max_capitalized_rank"] = args.max_capitalized_rank
    payload["generation"]["spelling_folds"] = len(spelling_map)
    logger.info(
        "Dropped %d capitalized entries ranked below %d", dropped, args.max_capitalized_rank
    )

    frequencies = payload["global_word_frequency"]
    print(f"\nCorpus: {CORPUS_NAME}")
    print(f"  chapters analyzed: {len(analyses):,}")
    print(f"  tokens counted:    {payload['generation']['total_tokens']:,}")
    print(f"  unique words:      {payload['total_unique_words']:,}")
    print(f"  words written:     {len(frequencies):,}")
    print(f"  spelling folds:    {len(spelling_map):,}")
    if args.show_folds:
        shown = sorted(spelling_map.items())[: args.show_folds]
        print("  " + ", ".join(f"{british}->{american}" for british, american in shown))
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
