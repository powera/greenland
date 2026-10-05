#!/usr/bin/python3

"""Report the corpus mix of each Trakaido level.

Read-only.  For every levelled English lemma, finds the corpus it leans toward
(see ``wordfreq.frequency.level_profile``), then prints:

  * per level: "330 (n=42): 81% wiki_arts, 12% general, 7% wiki_history"
  * per corpus: the levels with the largest share of that corpus's words --
    "wiki_arts: 330 (81%), 335 (55%), 105 (20%)"

The full run touches every levelled lemma against every corpus and takes a few
minutes; --json saves the result (per-lemma rows included) so later work can
read it instead of recomputing.

    GREENLAND_TEST_MODE=1 PYTHONPATH=src python src/wordfreq/tools/level_corpus_profile.py \
        --json /tmp/level_profiles.json
"""

import sys
from pathlib import Path

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import argparse
import contextlib
import json
import logging
from typing import Any, Dict, List, Optional

from storage.backend import create_session
from storage.backend.config import DataSourceConfig
from wordfreq.frequency.corpus import get_enabled_corpus_names
from wordfreq.frequency.level_profile import (
    DEFAULT_MIN_SKEW,
    GENERAL,
    LemmaCorpusProfile,
    LevelProfile,
    build_level_profiles,
    rank_levels_for_corpus,
)

logger = logging.getLogger(__name__)


def format_level_line(profile: LevelProfile, max_corpora: int = 4) -> str:
    """One line summarising a level's corpus mix."""
    ranked = profile.ranked_corpora()
    parts = [f"{share:.0%} {name}" for name, share in ranked[:max_corpora]]
    if len(ranked) > max_corpora:
        rest = sum(share for _name, share in ranked[max_corpora:])
        parts.append(f"{rest:.0%} other")
    unattested = f", {profile.unattested_count} unattested" if profile.unattested_count else ""
    return f"{profile.level:>4} (n={profile.lemma_count}{unattested}): " + ", ".join(parts)


def _example_words(
    lemma_profiles: List[LemmaCorpusProfile], level: int, corpus_name: str, count: int
) -> List[str]:
    """The level's words leaning hardest toward this corpus."""
    matches = [
        lemma_profile
        for lemma_profile in lemma_profiles
        if lemma_profile.level == level and lemma_profile.top_corpus == corpus_name
    ]
    matches.sort(key=lambda lemma_profile: -lemma_profile.top_skew)
    return [lemma_profile.display_text for lemma_profile in matches[:count]]


def to_json(
    level_profiles: Dict[int, LevelProfile],
    lemma_profiles: List[LemmaCorpusProfile],
    corpus_names: List[str],
    min_skew: float,
    min_lemmas: int,
) -> Dict[str, Any]:
    """Serializable form of the whole report."""
    return {
        "min_skew": min_skew,
        "corpora": corpus_names,
        "levels": {
            str(level): {
                "lemma_count": profile.lemma_count,
                "unattested_count": profile.unattested_count,
                "top_corpus_counts": dict(sorted(profile.top_corpus_counts.items())),
                "mean_skew": {name: round(profile.mean_skew(name), 3) for name in corpus_names},
            }
            for level, profile in sorted(level_profiles.items())
        },
        "levels_by_corpus": {
            name: [
                {
                    "level": candidate.level,
                    "share": round(candidate.share, 3),
                    "count": candidate.count,
                    "lemma_count": candidate.lemma_count,
                    "lift": round(candidate.lift, 2),
                }
                for candidate in rank_levels_for_corpus(level_profiles, name, min_lemmas)
            ]
            for name in corpus_names + [GENERAL]
        },
        "lemmas": [
            {
                "lemma_id": lemma_profile.lemma_id,
                "text": lemma_profile.display_text,
                "level": lemma_profile.level,
                "top_corpus": lemma_profile.top_corpus,
                "top_skew": round(lemma_profile.top_skew, 3),
                "attested": list(lemma_profile.attested_corpora),
                "skew": {
                    name: round(skew, 3) for name, skew in lemma_profile.skew_by_corpus.items()
                },
            }
            for lemma_profile in lemma_profiles
        ],
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db-path", type=str, default=None, help="SQLite database path")
    parser.add_argument(
        "--min-skew",
        type=float,
        default=DEFAULT_MIN_SKEW,
        help=f"Zipf skew a lemma needs to count toward a corpus (default {DEFAULT_MIN_SKEW})",
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
    parser.add_argument("--json", type=str, default=None, help="Write the full result here")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.WARNING)
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

    print(f"== Corpus mix by level (min skew {args.min_skew}) ==")
    for _level, profile in sorted(level_profiles.items()):
        print(format_level_line(profile))

    print()
    print("== Levels by corpus (share of level, lift vs. all levels) ==")
    for corpus_name in corpus_names + [GENERAL]:
        candidates = rank_levels_for_corpus(
            level_profiles, corpus_name, args.min_lemmas, args.top_levels
        )
        if not candidates:
            continue
        print(f"{corpus_name}:")
        for candidate in candidates:
            examples = _example_words(lemma_profiles, candidate.level, corpus_name, args.examples)
            print(
                f"  {candidate.level:>4}  {candidate.share:>4.0%} "
                f"({candidate.count}/{candidate.lemma_count}, x{candidate.lift:.1f})  "
                + ", ".join(examples)
            )

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(
                to_json(
                    level_profiles, lemma_profiles, corpus_names, args.min_skew, args.min_lemmas
                ),
                handle,
                ensure_ascii=False,
                indent=1,
            )
        print(f"\nWrote {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
