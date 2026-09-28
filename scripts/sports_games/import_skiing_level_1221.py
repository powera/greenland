#!/usr/bin/env python3
"""Import the terms of skiing and snowboarding at topic level 1221.

Assembled from the FIS International Competition Rules and the Wikipedia
"Glossary of skiing terms" (CC BY-SA).  The snowboard events carry the label
"snowboarding".

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
    level=LEVELS["skiing"],
    domain="skiing and snowboarding",
    label="skiing",
    tags=tags_for("skiing"),
    entries=(
        S("slalom", "a race zigzagging between gates"),
        S("giant slalom", unique=True),
        S("super-G", unique=True),
        S("downhill", "the fastest alpine race, straight down a long course"),
        S("gate", "a pair of poles a skier must pass between"),
        S("piste", "a prepared ski run"),
        S("off-piste", "away from the prepared runs"),
        S("moguls", "a slope of bumps, or the freestyle event skied on it"),
        S("ski jumping", unique=True),
        S("cross-country skiing", unique=True),
        S("biathlon", unique=True),
        S("telemark", "a turn or style with the free heel and bent knee"),
        S("schuss", unique=True),
        S("snowplow", "a turn or stop with the ski tips pointed together"),
        S("carve", "to turn on the edges of the skis without skidding"),
        S("binding", "the fitting that holds the boot to the ski"),
        S("ski pole", unique=True),
        S("ski lift", unique=True),
        S("chairlift", unique=True),
        S("gondola", "an enclosed cable car carrying skiers uphill"),
        S("bunny slope", unique=True),
        S("après-ski", unique=True),
        S("halfpipe", "a U-shaped channel for tricks", disambiguation="snowboarding"),
        S("slopestyle", "a course of jumps and rails for tricks", disambiguation="snowboarding"),
        S("big air", "an event judged on one large jump", disambiguation="snowboarding"),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
