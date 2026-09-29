#!/usr/bin/python3

"""Generate the WPA life-histories corpus word-frequency JSON.

    PYTHONPATH=src python src/wordfreq/corpora/download_wpalh.py \
        --dest "/Volumes/Dorothy Day/wpalh"
    PYTHONPATH=src python src/wordfreq/corpora/build_wpalh.py \
        --source-dir "/Volumes/Dorothy Day/wpalh" --phrases-from-db

Reads the PDFs ``download_wpalh.py`` cached, strips the questionnaire pages and
header lines (:mod:`wordfreq.corpora.wpalh_text`), drops interviews written in
heavy eye-dialect, and writes ``data/wordfreq/wpa_life_histories.json`` in the
format ``wordfreq.frequency.importer`` expects.

Two stages, the first of which is slow and done once:

1. **Extract.**  Each PDF's text layer is written to
   ``<cache>/text/<shelf id>.txt``, pages separated by form feeds.  About
   21,000 pages; ``--workers`` spreads them over processes.  Needs ``pypdf``,
   which is not a project dependency.  Skipped for PDFs already extracted
   unless ``--reextract`` is given.
2. **Build.**  Cleans each extracted interview and hands it to the shared
   ``frequency_build`` code, so proper-noun detection, per-document weighting
   and the output format are the same as every other corpus.

Interviews whose share of dialect spellings exceeds ``--max-dialect-share``
are left out.  The writers rendered some speakers -- chiefly Southern Black
interviewees -- in eye-dialect ("dey", "gwine", "chillun"), and those
spellings recur across documents, so the minimum-document threshold that
removes one-off OCR errors would keep them.  ``--report`` writes the per-
interview scores so the cut can be checked.

No network.  No database access either, unless ``--phrases-from-db`` is passed:
that reads the multi-word lemma forms so "ice cream" is counted as one token.
"""

import argparse
import csv
import json
import logging
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import constants
from agents.common.common_args import add_backend_args, get_data_source_config
from wordfreq.corpora.download_wpalh import MANIFEST_FILENAME, default_cache_dir, pdf_dir
from wordfreq.corpora.frequency_build import (
    DEFAULT_MIN_NAME_COUNT,
    DEFAULT_MIN_UPPERCASE_COUNT,
    DEFAULT_MIN_UPPERCASE_SHARE,
    BookAnalysis,
    analyze_book,
    build_corpus_payload,
    detect_names,
    write_corpus_json,
)
from wordfreq.corpora.gutenberg_text import TextStats
from wordfreq.corpora.wpalh_text import (
    apply_ocr_corrections,
    build_ocr_corrections,
    clean_pages,
    dialect_share,
    extract_pages,
    slugify_item,
    word_counts,
)

logger = logging.getLogger(__name__)

CORPUS_NAME = "wpa_life_histories"

# ~2,800 interviews, far more documents than the 54 books of the 19th-century
# list, so a word must spread further before it counts as corpus vocabulary
# rather than one interview's subject -- or one interview's OCR error.
DEFAULT_MIN_DOCUMENTS = 10

# Interviews run 1,000-2,000 words; a novel's 20000-token threshold would
# down-weight nearly all of them.
DEFAULT_FULL_WEIGHT_TOKENS = 1500

# Below this, once cleaned, a document is a cover sheet or a fragment.
DEFAULT_MIN_WORDS = 150

# Share of words that are eye-dialect spellings above which an interview is
# left out.  Set from the score distribution over the whole collection; see
# --report.
DEFAULT_MAX_DIALECT_SHARE = 0.01

# Matches the other corpora; see build_scotus.DEFAULT_MAX_WORDS.
DEFAULT_MAX_WORDS = 10000

PAGE_SEPARATOR = "\f"


class Interview(NamedTuple):
    """One cleaned interview and the numbers used to decide whether to keep it."""

    shelf_id: str
    slug: str
    place: str
    text: str
    words: int
    dialect: float


def text_dir(cache_dir: Path) -> Path:
    """Directory of extracted PDF text."""
    return cache_dir / "text"


def _extract_one(pdf: Path, destination: Path) -> Tuple[str, Optional[str]]:
    """Extract one PDF to ``destination``; returns ``(name, error)``."""
    try:
        pages = extract_pages(pdf)
    except RuntimeError:
        raise
    except Exception as error:  # pypdf raises a wide range on damaged files
        return pdf.name, f"{type(error).__name__}: {error}"
    partial = destination.with_name(destination.name + ".part")
    partial.write_text(PAGE_SEPARATOR.join(pages), encoding="utf-8")
    partial.replace(destination)
    return pdf.name, None


def extract_all(cache_dir: Path, *, workers: int, reextract: bool = False) -> int:
    """Write the text of every cached PDF not yet extracted.

    Returns:
        The number of PDFs that could not be read.
    """
    out_dir = text_dir(cache_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs = []
    for pdf in sorted(pdf_dir(cache_dir).glob("*.pdf")):
        destination = out_dir / f"{pdf.stem}.txt"
        if reextract or not destination.exists():
            jobs.append((pdf, destination))
    if not jobs:
        return 0
    logger.info("Extracting %d PDFs with %d workers", len(jobs), workers)
    failures = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_extract_one, pdf, destination) for pdf, destination in jobs]
        for done, future in enumerate(as_completed(futures), start=1):
            name, error = future.result()
            if error:
                failures += 1
                logger.warning("%s: %s", name, error)
            if done % 250 == 0:
                logger.info("[%d/%d] extracted", done, len(jobs))
    return failures


def load_manifest(cache_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Per-item metadata written by the downloader, keyed by shelf id."""
    path = cache_dir / MANIFEST_FILENAME
    if not path.exists():
        return {}
    items = json.loads(path.read_text(encoding="utf-8")).get("items") or {}
    return dict(items)


def read_interviews(cache_dir: Path) -> List[Interview]:
    """Every extracted interview, cleaned and scored."""
    manifest = load_manifest(cache_dir)
    interviews: List[Interview] = []
    for path in sorted(text_dir(cache_dir).glob("*.txt")):
        shelf_id = path.stem
        meta = manifest.get(shelf_id) or {}
        pages = path.read_text(encoding="utf-8").split(PAGE_SEPARATOR)
        text = clean_pages(pages)
        interviews.append(
            Interview(
                shelf_id=shelf_id,
                slug=slugify_item(shelf_id, str(meta.get("title") or "")),
                place=str(meta.get("place") or ""),
                text=text,
                words=len(text.split()),
                dialect=dialect_share(text),
            )
        )
    return interviews


def load_known_words(data_dir: Path) -> Dict[str, int]:
    """Every word of every other corpus in ``data_dir``, with its best rank there.

    The vocabulary an OCR correction must land on, and the evidence for
    whether a word this corpus shares with the others is meant or misread
    (see ``build_ocr_corrections``).  This corpus's own previous output is
    left out, or last run's surviving misreadings would vouch for themselves.

    Returns:
        Lowercase word -> its highest (smallest) rank in any other corpus.
    """
    known: Dict[str, int] = {}
    for path in sorted(data_dir.glob("*.json")):
        if path.stem in (CORPUS_NAME, "cooccurrence"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        frequencies = payload.get("global_word_frequency") if isinstance(payload, dict) else None
        if not isinstance(frequencies, dict):
            continue
        ordered = sorted(frequencies.items(), key=lambda entry: -entry[1])
        for rank, (word, _) in enumerate(ordered, start=1):
            lower = word.lower()
            known[lower] = min(rank, known.get(lower, rank))
    return known


def correct_ocr(
    interviews: List[Interview], known: Dict[str, int]
) -> Tuple[List[Interview], Dict[str, str], Counter[str]]:
    """Rewrite recurring OCR misreadings across the whole collection.

    Returns:
        The corrected interviews, the correction map, and the corpus counts of
        each corrected misreading (for the report).
    """
    counts = word_counts(item.text for item in interviews)
    corrections = build_ocr_corrections(counts, known)
    corrected = [
        item._replace(text=apply_ocr_corrections(item.text, corrections, known))
        for item in interviews
    ]
    misreadings = Counter({word: counts[word] for word in corrections})
    return corrected, corrections, misreadings


def remove_pooled_names(analyses: List[BookAnalysis]) -> Dict[str, int]:
    """Treat as names the words the whole collection capitalizes, in every interview.

    ``analyze_book`` decides names one document at a time and needs a word
    mid-sentence at least four times in that document to judge it.  A novel
    mentions its characters hundreds of times; a 1,500-word interview names
    the informant ("Mr. Lovett") two or three times, so it slips through and
    is published as the word "lovett".  Pooling the capitalization evidence
    over all interviews and applying the same test catches those names.

    Mutates each analysis: pooled names move from the content counts to
    ``names``.

    Returns:
        Each pooled name and its total count across the interviews.
    """
    pooled = TextStats()
    for analysis in analyses:
        pooled.counts.update(analysis.stats.counts)
        pooled.mid_sentence_total.update(analysis.stats.mid_sentence_total)
        pooled.mid_sentence_capitalized.update(analysis.stats.mid_sentence_capitalized)
    names = detect_names(pooled)
    moved: Counter[str] = Counter()
    for analysis in analyses:
        for word in names.keys() & analysis.content_counts.keys():
            count = analysis.content_counts.pop(word)
            analysis.upper_counts.pop(word, None)
            analysis.lower_counts.pop(word, None)
            analysis.names[word] = analysis.names.get(word, 0) + count
            moved[word] += count
    return dict(moved)


def write_report(path: Path, interviews: List[Interview], kept: set[str]) -> None:
    """Per-interview word counts, dialect scores and whether each was kept."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["shelf_id", "slug", "place", "words", "dialect_share", "kept"])
        for interview in sorted(interviews, key=lambda item: -item.dialect):
            writer.writerow(
                [
                    interview.shelf_id,
                    interview.slug,
                    interview.place,
                    interview.words,
                    f"{interview.dialect:.4f}",
                    "yes" if interview.slug in kept else "no",
                ]
            )


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
        "--source-dir",
        type=Path,
        default=None,
        help=f"Download cache directory (default: {default_cache_dir()})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=f"Output JSON path (default: data/wordfreq/{CORPUS_NAME}.json)",
    )
    parser.add_argument(
        "--workers", type=int, default=4, help="Processes for PDF extraction (default: 4)"
    )
    parser.add_argument(
        "--reextract", action="store_true", help="Re-extract PDFs already extracted"
    )
    parser.add_argument("--extract-only", action="store_true", help="Extract the PDF text and stop")
    parser.add_argument(
        "--max-dialect-share",
        type=float,
        default=DEFAULT_MAX_DIALECT_SHARE,
        help=f"Leave out interviews above this dialect share (default: {DEFAULT_MAX_DIALECT_SHARE})",
    )
    parser.add_argument(
        "--min-words",
        type=int,
        default=DEFAULT_MIN_WORDS,
        help=f"Leave out interviews shorter than this once cleaned (default: {DEFAULT_MIN_WORDS})",
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
        help=f"Interviews a word must appear in (default: {DEFAULT_MIN_DOCUMENTS})",
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
        help=f"Length at which an interview gets full weight "
        f"(default: {DEFAULT_FULL_WEIGHT_TOKENS})",
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
        "--no-ocr-corrections",
        dest="ocr_corrections",
        action="store_false",
        help="Count OCR misreadings as they are instead of correcting them",
    )
    parser.add_argument(
        "--report", type=Path, default=None, help="Write per-interview scores to this CSV"
    )
    parser.add_argument("--top", type=int, default=25, help="Top words to print")
    parser.add_argument("--dry-run", action="store_true", help="Report without writing")
    add_backend_args(parser)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    cache_dir: Path = args.source_dir or default_cache_dir()
    if not pdf_dir(cache_dir).is_dir():
        logger.error("PDF directory not found: %s", pdf_dir(cache_dir))
        return 1

    try:
        failures = extract_all(cache_dir, workers=args.workers, reextract=args.reextract)
    except RuntimeError as error:
        logger.error("%s", error)
        return 1
    if failures:
        logger.warning("%d PDFs could not be read", failures)
    if args.extract_only:
        return 0

    interviews = read_interviews(cache_dir)
    if not interviews:
        logger.error("No extracted interviews in %s", text_dir(cache_dir))
        return 1
    too_short = [item for item in interviews if item.words < args.min_words]
    dialect = [
        item
        for item in interviews
        if item.words >= args.min_words and item.dialect > args.max_dialect_share
    ]
    kept = [
        item
        for item in interviews
        if item.words >= args.min_words and item.dialect <= args.max_dialect_share
    ]

    corrections: Dict[str, str] = {}
    if args.ocr_corrections:
        known = load_known_words(Path(constants.WORDFREQ_DATA_DIR))
        kept, corrections, misreadings = correct_ocr(kept, known)
        logger.info(
            "OCR: %d misreadings corrected (%d occurrences), against %d known words",
            len(corrections),
            sum(misreadings.values()),
            len(known),
        )
        for word, count in misreadings.most_common(15):
            logger.info("  %-12s -> %-12s %d", word, corrections[word], count)

    phrases: Optional[Dict[str, int]] = None
    if args.phrases_from_db:
        phrases = _load_phrases(args)
        logger.info("Phrase index: %d multi-word forms", len(phrases))

    analyses: List[BookAnalysis] = []
    for index, item in enumerate(kept, start=1):
        analyses.append(analyze_book(item.slug, item.text, phrases=phrases))
        if index % 500 == 0:
            logger.info("[%d/%d] interviews analyzed", index, len(kept))

    pooled_names = remove_pooled_names(analyses)
    logger.info(
        "Pooled name detection: %d more names (%d occurrences)",
        len(pooled_names),
        sum(pooled_names.values()),
    )

    if args.report:
        write_report(args.report, interviews, {item.slug for item in kept})
        logger.info("Wrote %s", args.report)

    payload = build_corpus_payload(
        analyses,
        corpus_name=CORPUS_NAME,
        min_books=args.min_documents,
        max_words=args.max_words,
        min_name_count=args.min_name_count,
        full_weight_tokens=args.full_weight_tokens,
        min_uppercase_count=args.min_uppercase_count,
        min_uppercase_share=args.min_uppercase_share,
        generator="wordfreq.corpora.build_wpalh",
    )

    frequencies = payload["global_word_frequency"]
    print(f"\nCorpus: {CORPUS_NAME}")
    print(f"  interviews extracted:    {len(interviews):,}")
    print(f"  left out, too short:     {len(too_short):,}")
    print(f"  left out, dialect:       {len(dialect):,}")
    print(f"  interviews analyzed:     {len(analyses):,}")
    print(f"  words in kept interviews:{sum(item.words for item in kept):>12,}")
    print(f"  tokens counted:          {payload['generation']['total_tokens']:,}")
    print(f"  unique words:            {payload['total_unique_words']:,}")
    print(f"  words written:           {len(frequencies):,}")
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
