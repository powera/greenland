#!/usr/bin/python3

"""Report the corpus mix of each Trakaido level.

Read-only.  For every levelled English lemma, splits one unit of weight between
the corpora it leans toward (see ``wordfreq.frequency.level_profile``), then
prints:

  * per level: "330 (n=42): 81% wiki_arts, 12% general, 7% wiki_history"
  * per corpus: the levels with the largest share of that corpus's words --
    "wiki_arts: 330 (81%), 335 (55%), 105 (20%)"

Measuring every levelled lemma against every corpus takes a few minutes.
--json saves the raw measurements (each lemma's Zipf per corpus), and
--from-json re-scores a saved file in seconds, which is the way to try other
--min-skew values.  A saved file keeps the levels it was measured at: re-measure
after levels or sense prominences change.

    GREENLAND_TEST_MODE=1 PYTHONPATH=src python src/wordfreq/tools/level_corpus_profile.py \
        --json /tmp/level_profiles.json
    GREENLAND_TEST_MODE=1 PYTHONPATH=src python src/wordfreq/tools/level_corpus_profile.py \
        --from-json /tmp/level_profiles.json --min-skew 0.7 --exclude-general
"""

import sys
from pathlib import Path

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import argparse
import contextlib
import json
import logging
from typing import Dict, List, Optional, Sequence

from storage.backend import create_session
from storage.backend.config import DataSourceConfig
from wordfreq.frequency.corpus import get_enabled_corpus_names
from wordfreq.frequency.level_profile import (
    DEFAULT_MIN_SKEW,
    GENERAL,
    LemmaCorpusProfile,
    LevelProfile,
    aggregate_levels,
    build_level_profiles,
    profiles_from_json,
    profiles_to_json,
    rank_levels_for_corpus,
)

logger = logging.getLogger(__name__)


def format_level_line(
    profile: LevelProfile, include_general: bool = True, max_corpora: int = 4
) -> str:
    """One line summarising a level's corpus mix."""
    ranked = profile.ranked_corpora(include_general)
    parts = [f"{share:.0%} {name}" for name, share in ranked[:max_corpora]]
    if len(ranked) > max_corpora:
        rest = sum(share for _name, share in ranked[max_corpora:])
        parts.append(f"{rest:.0%} other")
    notes = ""
    if not include_general:
        notes += f", {profile.share(GENERAL):.0%} general omitted"
    if profile.unattested_count:
        notes += f", {profile.unattested_count} unattested"
    return f"{profile.level:>4} (n={profile.lemma_count}{notes}): " + ", ".join(parts)


def _example_words(
    lemma_profiles: List[LemmaCorpusProfile], level: int, corpus_name: str, count: int
) -> List[str]:
    """The level's words putting the most weight on this corpus."""
    matches = [
        lemma_profile
        for lemma_profile in lemma_profiles
        if lemma_profile.level == level and corpus_name in lemma_profile.weights
    ]
    matches.sort(
        key=lambda lemma_profile: (
            -lemma_profile.weights[corpus_name],
            -lemma_profile.skew_by_corpus.get(corpus_name, 0.0),
        )
    )
    return [lemma_profile.display_text for lemma_profile in matches[:count]]


def print_report(
    level_profiles: Dict[int, LevelProfile],
    lemma_profiles: List[LemmaCorpusProfile],
    corpus_names: Sequence[str],
    min_skew: float,
    include_general: bool,
    min_lemmas: int,
    top_levels: int,
    examples: int,
) -> None:
    print(f"== Corpus mix by level (min skew {min_skew}) ==")
    for _level, profile in sorted(level_profiles.items()):
        print(format_level_line(profile, include_general))

    print()
    print("== Levels by corpus (share of level, weight/lemmas, lift vs. all levels) ==")
    names = list(corpus_names) + ([GENERAL] if include_general else [])
    for corpus_name in names:
        candidates = rank_levels_for_corpus(
            level_profiles, corpus_name, min_lemmas, top_levels, include_general
        )
        if not candidates:
            continue
        print(f"{corpus_name}:")
        for candidate in candidates:
            words = _example_words(lemma_profiles, candidate.level, corpus_name, examples)
            print(
                f"  {candidate.level:>4}  {candidate.share:>4.0%} "
                f"({candidate.weight:.1f}/{candidate.lemma_count}, x{candidate.lift:.1f})  "
                + ", ".join(words)
            )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--db-path", type=str, default=None, help="SQLite database path")
    parser.add_argument(
        "--min-skew",
        type=float,
        default=DEFAULT_MIN_SKEW,
        help=f"Zipf skew a corpus needs to get any of a lemma's weight (default {DEFAULT_MIN_SKEW})",
    )
    parser.add_argument(
        "--exclude-general",
        action="store_true",
        help="Leave general words out of each level's shares, showing its topical mix alone",
    )
    parser.add_argument("--level", type=int, action="append", help="Only these levels")
    parser.add_argument("--limit", type=int, default=None, help="Profile at most N lemmas")
    parser.add_argument(
        "--min-lemmas",
        type=int,
        default=5,
        help="Ignore levels with fewer profiled lemmas in the per-corpus ranking (default 5)",
    )
    parser.add_argument(
        "--top-levels", type=int, default=8, help="Levels listed per corpus (default 8)"
    )
    parser.add_argument(
        "--examples", type=int, default=3, help="Example words per corpus/level pairing"
    )
    parser.add_argument("--json", type=str, default=None, help="Save the measurements here")
    parser.add_argument(
        "--from-json",
        type=str,
        default=None,
        help="Re-score measurements saved by --json instead of reading the database",
    )
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.WARNING)

    if args.from_json:
        with open(args.from_json, "r", encoding="utf-8") as handle:
            saved = json.load(handle)
        lemma_profiles, unattested_by_level, corpus_names = profiles_from_json(
            saved, args.min_skew, args.level
        )
        if args.limit is not None:
            lemma_profiles = lemma_profiles[: args.limit]
        level_profiles = aggregate_levels(lemma_profiles, unattested_by_level)
    else:
        config = DataSourceConfig(sqlite_path=args.db_path, debug=args.debug)
        corpus_names = get_enabled_corpus_names()

        def progress(done: int, total: int) -> None:
            if done % 250 == 0 or done == total:
                print(f"  profiled {done}/{total} lemmas", file=sys.stderr)

        with contextlib.closing(create_session(config, readonly=True)) as session:
            level_profiles, lemma_profiles = build_level_profiles(
                session,
                min_skew=args.min_skew,
                levels=args.level,
                corpus_names=corpus_names,
                limit=args.limit,
                progress=progress,
            )
        unattested_by_level = {
            level: profile.unattested_count
            for level, profile in level_profiles.items()
            if profile.unattested_count
        }

    print_report(
        level_profiles,
        lemma_profiles,
        corpus_names,
        args.min_skew,
        not args.exclude_general,
        args.min_lemmas,
        args.top_levels,
        args.examples,
    )

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(
                profiles_to_json(lemma_profiles, unattested_by_level, corpus_names, args.min_skew),
                handle,
                ensure_ascii=False,
                indent=1,
            )
        print(f"\nWrote {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
