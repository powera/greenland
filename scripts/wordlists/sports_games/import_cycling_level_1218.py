#!/usr/bin/env python3
"""Import the terms of cycling at topic level 1218.

Assembled from the UCI Cycling Regulations and the Wikipedia "Glossary of
cycling" (CC BY-SA): road racing first, then the track events.  Much of road
racing's vocabulary is French (peloton, domestique), which the prompt keeps as
borrowings where a language borrows it.  Race names, the Tour's jerseys among
them, wait for the names work.

Running without ``--execute`` only prints the plan and makes no HTTP requests.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.wordlists.sports_games.levels import LEVELS, tags_for
from scripts.wordlists.wordlist_import_helper import SenseEntry as S
from scripts.wordlists.wordlist_import_helper import SenseList, run_sense_import

SENSES = SenseList(
    level=LEVELS["cycling"],
    domain="bicycle racing",
    label="cycling",
    tags=tags_for("cycling"),
    entries=(
        S("peloton", unique=True),
        S("breakaway", "riders who have ridden clear of the main group"),
        S("attack", "a sudden acceleration to get away from other riders"),
        S("stage", "one day's race within a race of several days"),
        S("stage race", unique=True),
        S("time trial", "a race against the clock, riders starting separately"),
        S("prologue", "a short time trial opening a stage race"),
        S("general classification", unique=True),
        S("domestique", unique=True),
        S("lead-out", "riders pulling a sprinter up to speed before the finish"),
        S("drafting", "riding close behind another rider to save effort"),
        S("echelon", "a diagonal line of riders sheltering from a crosswind"),
        S("criterium", unique=True),
        S("cyclo-cross", unique=True),
        S("broom wagon", unique=True),
        S("cadence", "the rate of pedaling"),
        S("derailleur", unique=True),
        S("velodrome", unique=True),
        S("keirin", unique=True),
        S("omnium", unique=True),
        S("pursuit", "a track race in which riders start on opposite sides and chase"),
        S("madison", "a track relay race for teams of two"),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
