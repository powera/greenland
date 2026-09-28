#!/usr/bin/env python3
"""Import the terms of golf at topic level 1210.

Assembled from the R&A / USGA Rules of Golf and the Wikipedia "Glossary of golf"
(CC BY-SA).  The scores (birdie, eagle, bogey) and the course (green, rough,
links) are everyday or animal words with a golf sense, so they carry hints.

Running without ``--execute`` only prints the plan and makes no HTTP requests.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.sports_games.levels import LEVELS, tags_for
from scripts.wordlist_import_helper import SenseEntry as S
from scripts.wordlist_import_helper import SenseList, run_sense_import

SENSES = SenseList(
    level=LEVELS["golf"],
    domain="golf",
    label="golf",
    tags=tags_for("golf"),
    entries=(
        S("par", "the standard number of strokes for a hole or course"),
        S("birdie", "a score of one stroke under par on a hole"),
        S("eagle", "a score of two strokes under par on a hole"),
        S("albatross", "a score of three strokes under par on a hole"),
        S("bogey", "a score of one stroke over par on a hole"),
        S("double bogey", unique=True),
        S("hole in one", "getting the ball into the hole with the first stroke"),
        S("hole", "one of the 18 sections of a course, or the cup on its green"),
        S("round", "a complete game of 18 holes"),
        S("stroke", "one swing at the ball"),
        S("handicap", "a number of strokes that evens out players of different skill"),
        S("tee", "the peg the ball sits on, or the area where a hole starts"),
        S("tee off", "to play the first shot of a hole"),
        S("fairway", "the mown grass between the tee and the green"),
        S("rough", "the long grass beside the fairway"),
        S("green", "the smooth grass around the hole"),
        S("bunker", "a hollow filled with sand"),
        S("links", "a seaside golf course"),
        S("flagstick", unique=True),
        S("divot", unique=True),
        S("club", "the stick used to hit the ball"),
        S("driver", "the club for long shots from the tee"),
        S("iron", "a club with a metal head for middle-distance shots"),
        S("wedge", "a club for short, high shots"),
        S("putter", "the club for rolling the ball on the green"),
        S("putt", "a gentle stroke on the green"),
        S("drive", "a long shot from the tee"),
        S("chip", "a short, low shot onto the green"),
        S("slice", "a shot that curves away to the side of the golfer's strong hand"),
        S("hook", "a shot that curves across the golfer's body"),
        S("backswing", unique=True),
        S("caddie", "a person who carries a golfer's clubs"),
        S("fore", "a warning shout to people in the ball's path"),
        S("mulligan", unique=True),
        S("match play", unique=True),
        S("stroke play", unique=True),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
