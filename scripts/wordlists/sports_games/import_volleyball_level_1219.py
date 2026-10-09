#!/usr/bin/env python3
"""Import the terms of volleyball at topic level 1219.

Assembled from the FIVB Official Volleyball Rules and the Wikipedia "Volleyball
jargon" article (CC BY-SA).  The net-sport words that mean the same across
tennis and badminton -- serve, rally, ace, net, set as a unit of scoring -- are
in the shared list at 405; "set" here is the volleyball pass.

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
    level=LEVELS["volleyball"],
    domain="volleyball",
    label="volleyball",
    tags=tags_for("volleyball"),
    entries=(
        S("spike", "a hard downward hit over the net"),
        S("set", "a pass that places the ball for a teammate to spike"),
        S("setter", "the player who sets the ball for attackers"),
        S("dig", "keeping a hard-driven ball off the floor"),
        S("bump", "a pass off the forearms"),
        S("block", "jumping at the net to stop an opponent's spike"),
        S("kill", "an attack that wins the point outright"),
        S("tip", "a soft push of the ball over the block"),
        S("libero", unique=True),
        S("outside hitter", unique=True),
        S("middle blocker", unique=True),
        S("rotation", "the players moving round one position after winning the serve"),
        S("side out", "winning a rally on the opponent's serve"),
        S("attack line", "the line three meters from the net"),
        S("antenna", "one of the rods on the net marking the sides of the court"),
        S("beach volleyball", unique=True),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
