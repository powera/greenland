#!/usr/bin/env python3
"""Import the terms of boxing at topic level 1213.

Assembled from the Wikipedia "Glossary of boxing" and the weight-class tables
(CC BY-SA).  The weight classes are shared with wrestling and the other combat
sports but are boxing's in origin, so they are here.  "Technical knockout"
carries its abbreviation TKO; plain "KO" is left out, because it would be
stored as a variant spelling of go's "ko".

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
    level=LEVELS["boxing"],
    domain="boxing",
    label="boxing",
    tags=tags_for("boxing"),
    entries=(
        S("bout", "a boxing match"),
        S("ring", "the roped square platform boxers fight in"),
        S("corner", "the corner of the ring where a boxer rests between rounds"),
        S("round", "one of the three-minute periods of a bout"),
        S("bell", "the bell rung to start and end each round"),
        S("jab", "a quick straight punch with the lead hand"),
        S("cross", "a straight punch with the rear hand"),
        S("hook", "a short punch swung from the side"),
        S("uppercut", "an upward punch to the chin"),
        S("combination", "a series of punches thrown together"),
        S("counterpunch", "a punch thrown in answer to an opponent's"),
        S("clinch", "holding the opponent to stop them punching"),
        S("knockout", "ending a bout by knocking the opponent out"),
        S("technical knockout", unique=True, abbreviation="TKO"),
        S("knockdown", "a boxer being knocked to the floor"),
        S("count", "the referee counting to ten over a fallen boxer"),
        S("split decision", "a win on points that the judges do not agree on"),
        S("southpaw", "a boxer who leads with the right hand"),
        S("orthodox", "the stance leading with the left hand"),
        S("weigh-in", "the official weighing of boxers before a bout"),
        S("boxing glove", unique=True),
        S("heavyweight", "the heaviest weight class"),
        S("middleweight", "a middle weight class"),
        S("lightweight", "a light weight class"),
        S("welterweight", unique=True),
        S("featherweight", "a light weight class, below lightweight"),
        S("bantamweight", unique=True),
        S("flyweight", unique=True),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
