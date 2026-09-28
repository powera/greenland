#!/usr/bin/env python3
"""Import the terms of swimming and diving at topic level 1216.

Assembled from the World Aquatics swimming and diving rules.  The race
vocabulary shared with athletics -- lane, heat, lap, relay, false start,
starting block -- is in the shared list at 405.  The diving terms carry the
label "diving".

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
    level=LEVELS["swimming"],
    domain="swimming and diving",
    label="swimming",
    tags=tags_for("swimming"),
    entries=(
        S("stroke", "a style of swimming"),
        S("freestyle", "the race in which any stroke may be used, usually front crawl"),
        S("front crawl", unique=True),
        S("backstroke", unique=True),
        S("breaststroke", unique=True),
        S("butterfly", "the stroke with both arms moving together over the water"),
        S("medley", "a race using all four strokes"),
        S("length", "one swim from one end of the pool to the other"),
        S("flip turn", unique=True),
        S("touchpad", "the pad at the end of a lane that stops the clock"),
        S("kickboard", unique=True),
        S("artistic swimming", unique=True),
        S("dive", "a jump into the water, performed and judged", disambiguation="diving"),
        S("springboard", "a flexible diving board", disambiguation="diving"),
        S("platform", "a rigid high diving board", disambiguation="diving"),
        S(
            "pike",
            "a position with the legs straight and the body bent at the hips",
            disambiguation="diving",
        ),
        S("tuck", "a position with the knees drawn up to the chest", disambiguation="diving"),
        S("twist", "a rotation around the length of the body", disambiguation="diving"),
        S("entry", "the moment a diver goes into the water", disambiguation="diving"),
        S("belly flop", "a dive landing flat on the stomach"),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
