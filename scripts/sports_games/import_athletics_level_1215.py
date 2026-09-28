#!/usr/bin/env python3
"""Import the terms of athletics (track and field) at topic level 1215.

Assembled from the World Athletics Competition Rules and the event list.  The
race vocabulary athletics shares with swimming and cycling -- lane, heat, lap,
relay, false start, finish line, personal best -- is in the shared list at 405;
this unit is the events and their equipment.

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
    level=LEVELS["athletics"],
    domain="athletics (track and field)",
    label="athletics",
    tags=tags_for("athletics"),
    entries=(
        S("track and field", unique=True),
        S("sprint", "a short running race run at full speed"),
        S("sprinter", "a runner who races short distances"),
        S("hurdles", "a race over a series of barriers"),
        S("hurdle", "one of the barriers jumped in a hurdles race"),
        S("steeplechase", "a running race over barriers and a water jump"),
        S("marathon", "a running race of 42.195 kilometers"),
        S("half marathon", unique=True),
        S("cross-country", "running races over open country"),
        S("race walking", unique=True),
        S("baton", "the stick passed between runners in a relay"),
        S("anchor", "the last runner in a relay team"),
        S("pacemaker", "a runner who sets the pace for others"),
        S("starting block", "the foot braces a sprinter pushes off from"),
        S("field event", unique=True),
        S("high jump", unique=True),
        S("long jump", unique=True),
        S("triple jump", unique=True),
        S("pole vault", unique=True),
        S("shot put", unique=True),
        S("discus", "the heavy disk thrown for distance"),
        S("javelin", "the spear thrown for distance"),
        S("hammer throw", unique=True),
        S("decathlon", unique=True),
        S("heptathlon", unique=True),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
