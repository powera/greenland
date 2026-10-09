#!/usr/bin/env python3
"""Import the terms of baseball at topic level 1204.

Assembled from the MLB Official Baseball Rules and the Wikipedia "Glossary of
baseball terms" (CC BY-SA).  Many of these are everyday words with a baseball
sense -- single, walk, strike, pitch -- which is what the hints are for.

"Run batted in" carries its abbreviation RBI as a variant.  Earned run average
is left out: its abbreviation "ERA" would be stored as a variant spelling of
the word "era".

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
    level=LEVELS["baseball"],
    domain="baseball",
    label="baseball",
    tags=tags_for("baseball"),
    entries=(
        S("inning", unique=True),
        S("pitch", "a throw from the pitcher to the batter"),
        S("pitcher", "the player who throws the ball to the batter"),
        S("catcher", "the player who crouches behind home plate"),
        S("batter", "the player whose turn it is to hit"),
        S("shortstop", unique=True),
        S("infield", "the area inside the bases"),
        S("outfield", "the grass area beyond the infield"),
        S("infielder", unique=True),
        S("outfielder", unique=True),
        S("diamond", "the infield, or the whole playing field"),
        S("base", "one of the four stations a runner must touch"),
        S("home plate", unique=True),
        S("first base", "the first of the bases a runner reaches"),
        S("second base", "the base opposite home plate"),
        S("third base", "the last base before home plate"),
        S("mound", "the raised area the pitcher throws from"),
        S("dugout", "the sunken shelter where a team sits"),
        S("bullpen", "the area where relief pitchers warm up"),
        S("strike", "a pitch counted against the batter"),
        S("ball", "a pitch outside the strike zone that the batter does not swing at"),
        S("strike zone", unique=True),
        S("strikeout", "an out made by three strikes"),
        S("count", "the number of balls and strikes on the batter"),
        S("walk", "a batter reaching first base after four balls"),
        S("single", "a hit on which the batter reaches first base"),
        S("double", "a hit on which the batter reaches second base"),
        S("triple", "a hit on which the batter reaches third base"),
        S("home run", "a hit on which the batter rounds all the bases and scores"),
        S("grand slam", "a home run hit with the bases loaded"),
        S("run", "a point scored by a runner reaching home plate"),
        S("run batted in", unique=True, abbreviation="RBI"),
        S("out", "a batter or runner being put out of play"),
        S("bunt", "a softly tapped hit with the bat held still"),
        S("steal", "a runner taking a base while the pitch is thrown"),
        S("stolen base", unique=True),
        S("tag", "touching a runner with the ball to put them out"),
        S("double play", "a play that makes two outs"),
        S("fly ball", unique=True),
        S("ground ball", unique=True),
        S("foul ball", "a batted ball that lands outside the foul lines"),
        S("error", "a fielder's mistake that lets a runner advance"),
        S("fastball", unique=True),
        S("curveball", "a pitch that curves as it approaches the batter"),
        S("changeup", unique=True),
        S("knuckleball", unique=True),
        S("pinch hitter", "a substitute batter"),
        S("designated hitter", unique=True),
        S("no-hitter", unique=True),
        S("mitt", "the padded glove worn by the catcher or first baseman"),
        S("batting average", unique=True),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
