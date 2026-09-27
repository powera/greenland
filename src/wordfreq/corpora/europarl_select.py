#!/usr/bin/python3

"""Choose the Europarl chapters that make up the parliament-debates corpus.

    PYTHONPATH=src python src/wordfreq/corpora/europarl_select.py --dry-run
    PYTHONPATH=src python src/wordfreq/corpora/europarl_select.py

The full English release is about 60M words; the corpus wants about 5M, the
size of ``legal_scotus``.  This script reads the cached session files, drops
procedural chapters and short ones, draws a year-balanced sample, and writes
the chosen chapter slugs with their titles to ``europarl_chapters.yaml``
beside it.  The builder reads that file rather than re-deciding, so a build is
reproducible and the list can be reviewed -- and hand-edited -- like the wiki
article lists.

**Year-balanced** because sittings grew longer and more frequent over the
release, and a proportional sample would let the late 2000s decide the
vocabulary.  Each year is offered an equal share of the target; a year with
less than its share contributes everything it has and the remainder is spread
over the others.

**Deterministic**: within a year chapters are taken in the order of the MD5 of
their slug, so a re-run over the same cache chooses the same chapters, and
adding sessions to the cache disturbs the choice only in their own years.

Selection is on every speech, whatever language it was spoken in.  The report
prints how much of the sample is *known* to be translated (tagged with a
source language other than English); the rest is English originals and
untagged translations in unknown proportion.

No network, no database.
"""

import argparse
import hashlib
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import yaml

from wordfreq.corpora.download_europarl import EUROPARL_VERSION, default_cache_dir
from wordfreq.corpora.europarl_text import (
    Chapter,
    is_procedural_title,
    iter_session_files,
    read_session,
)

logger = logging.getLogger(__name__)

SELECTION_PATH = Path(__file__).parent / "europarl_chapters.yaml"

# Twice legal_scotus's ~5M tokens.  At 5M the 5500th word was down to ~10
# occurrences per million, too few to rank the tail reliably; the release has
# ~44M eligible words, so doubling costs nothing but build time.
DEFAULT_TARGET_WORDS = 10_000_000

# A chapter under this many words is a one-speaker statement or a stub of
# procedure the title filter missed, not a debate.
DEFAULT_MIN_WORDS = 800


@dataclass(frozen=True)
class ChapterSummary:
    """What selection needs to know about one chapter."""

    slug: str
    year: int
    title: str
    words: int
    translated_words: int


def summarize(chapter: Chapter) -> Optional[ChapterSummary]:
    """Word counts for one chapter, or ``None`` when its year is unknown."""
    year = chapter.year
    if year is None:
        return None
    sources: set[str] = {
        speech.language
        for speech in chapter.speeches
        if speech.language is not None and speech.language != "EN"
    }
    return ChapterSummary(
        slug=chapter.slug,
        year=year,
        title=chapter.title,
        words=len(chapter.text().split()),
        translated_words=len(chapter.text(languages=sources).split()) if sources else 0,
    )


def eligible(summary: ChapterSummary, *, min_words: int) -> bool:
    """A debate long enough to count, not a procedural agenda item."""
    return summary.words >= min_words and not is_procedural_title(summary.title)


def _draw_order(slug: str) -> str:
    return hashlib.md5(slug.encode("utf-8")).hexdigest()


def select_chapters(
    summaries: Iterable[ChapterSummary], *, target_words: int
) -> List[ChapterSummary]:
    """Draw a year-balanced, deterministic sample of about ``target_words``.

    Years are filled smallest-supply first: each takes the lesser of what it
    has and an equal share of what remains, so a thin year's shortfall goes to
    the years that can cover it.  Within a year chapters are taken in slug-hash
    order until the year's share is met; the chapter that crosses the line is
    kept, so a year overshoots by at most one chapter.
    """
    by_year: Dict[int, List[ChapterSummary]] = defaultdict(list)
    for summary in summaries:
        by_year[summary.year].append(summary)
    if not by_year:
        return []

    supply = {year: sum(item.words for item in items) for year, items in by_year.items()}
    remaining_target = target_words
    remaining_years = len(by_year)
    selected: List[ChapterSummary] = []
    for year in sorted(by_year, key=lambda key: (supply[key], key)):
        share = min(supply[year], remaining_target // remaining_years)
        taken = 0
        for item in sorted(by_year[year], key=lambda entry: _draw_order(entry.slug)):
            if taken >= share:
                break
            selected.append(item)
            taken += item.words
        remaining_target = max(0, remaining_target - taken)
        remaining_years -= 1
    return sorted(selected, key=lambda item: item.slug)


def scan_cache(cache_dir: Path, *, min_words: int) -> List[ChapterSummary]:
    """Summaries of every eligible chapter in the cached English sessions."""
    summaries: List[ChapterSummary] = []
    files = list(iter_session_files(cache_dir))
    for index, (_, path) in enumerate(files, start=1):
        for chapter in read_session(path):
            summary = summarize(chapter)
            if summary is not None and eligible(summary, min_words=min_words):
                summaries.append(summary)
        if index % 500 == 0:
            logger.info(
                "[%d/%d] sessions read, %d eligible chapters", index, len(files), len(summaries)
            )
    return summaries


def selection_payload(
    selected: Sequence[ChapterSummary], *, target_words: int, min_words: int
) -> Dict[str, Any]:
    """The YAML document: criteria, then ``slug: title`` grouped by year."""
    years: Dict[str, Dict[str, str]] = {}
    for item in sorted(selected, key=lambda entry: (entry.year, entry.slug)):
        years.setdefault(str(item.year), {})[item.slug] = item.title
    return {
        "source": f"Europarl {EUROPARL_VERSION} source release, English",
        "criteria": {"target_words": target_words, "min_words": min_words},
        "chapters": years,
    }


def write_selection(
    payload: Dict[str, Any], path: Path, selected: Sequence[ChapterSummary]
) -> None:
    words = sum(item.words for item in selected)
    header = (
        "# Europarl chapters for the eu_parliament_debates corpus.\n"
        "# Written by wordfreq/corpora/europarl_select.py; edit by hand to drop a\n"
        "# chapter, and re-run the selector only to redraw the whole sample.\n"
        f"#\n# {len(selected)} chapters, {words:,} words.\n\n"
    )
    body = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=1000)
    path.write_text(header + body, encoding="utf-8")


def load_selection(path: Path = SELECTION_PATH) -> List[str]:
    """Every chapter slug in the selection file, in file order."""
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    chapters = data.get("chapters")
    if not isinstance(chapters, dict):
        raise ValueError(f"{path}: no 'chapters' mapping")
    slugs: List[str] = []
    for entries in chapters.values():
        slugs.extend(str(slug) for slug in (entries or {}))
    return slugs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help=f"Europarl cache directory (default: {default_cache_dir()})",
    )
    parser.add_argument(
        "--output", type=Path, default=SELECTION_PATH, help=f"(default: {SELECTION_PATH.name})"
    )
    parser.add_argument(
        "--target-words",
        type=int,
        default=DEFAULT_TARGET_WORDS,
        help=f"Approximate size of the sample (default: {DEFAULT_TARGET_WORDS:,})",
    )
    parser.add_argument(
        "--min-words",
        type=int,
        default=DEFAULT_MIN_WORDS,
        help=f"Skip chapters shorter than this (default: {DEFAULT_MIN_WORDS})",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report without writing")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    cache_dir: Path = args.source_dir or default_cache_dir()
    summaries = scan_cache(cache_dir, min_words=args.min_words)
    if not summaries:
        logger.error("No eligible chapters under %s; run download_europarl.py first", cache_dir)
        return 1

    selected = select_chapters(summaries, target_words=args.target_words)
    available = sum(item.words for item in summaries)
    words = sum(item.words for item in selected)
    translated = sum(item.translated_words for item in selected)

    print(f"\nEligible: {len(summaries):,} chapters, {available:,} words")
    print(f"Selected: {len(selected):,} chapters, {words:,} words")
    print(f"  known translated:  {translated:,} words ({translated / max(words, 1):.0%})")
    per_year: Dict[int, List[int]] = defaultdict(lambda: [0, 0])
    for item in selected:
        per_year[item.year][0] += 1
        per_year[item.year][1] += item.words
    for year in sorted(per_year):
        count, year_words = per_year[year]
        print(f"  {year}: {count:>4} chapters {year_words:>10,} words")

    if args.dry_run:
        print("\n(dry run; nothing written)")
        return 0

    payload = selection_payload(selected, target_words=args.target_words, min_words=args.min_words)
    write_selection(payload, args.output, selected)
    print(f"\nWrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
