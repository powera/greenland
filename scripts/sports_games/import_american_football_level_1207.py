#!/usr/bin/env python3
"""Import the terms of American football at topic level 1207.

Assembled from the NFL Rulebook and the Wikipedia "Glossary of American
football" (CC BY-SA).  Terms shared with other sports in the same meaning --
kickoff, interception, turnover, offense, defense, draft -- are in the shared
list at 405.

"Safety" is the scoring play; the defensive position of the same name is left
out, since one script cannot hold two senses of one headword.

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
    level=LEVELS["american_football"],
    domain="American football",
    label="American football",
    tags=tags_for("american_football"),
    entries=(
        S("touchdown", "carrying or catching the ball in the opponent's end zone, worth six"),
        S("field goal", "a kick through the goalposts, worth three points"),
        S("extra point", "a kick after a touchdown, worth one point"),
        S("two-point conversion", unique=True),
        S("safety", "a two-point score for tackling a ball carrier in their own end zone"),
        S("end zone", "the scoring area at each end of the field"),
        S("yard line", "one of the lines marking distance on the field"),
        S("line of scrimmage", unique=True),
        S("gridiron", "the field, or the sport itself"),
        S("quarterback", unique=True),
        S("running back", unique=True),
        S("wide receiver", unique=True),
        S("tight end", unique=True),
        S("lineman", "a player on the line of scrimmage"),
        S("linebacker", unique=True),
        S("cornerback", unique=True),
        S("kicker", "the player who kicks field goals and extra points"),
        S("punter", "the player who punts"),
        S("punt", "a kick made by dropping the ball and kicking it before it lands"),
        S("snap", "passing the ball back between the legs to start a play"),
        S("huddle", "the team gathering before a play to decide it"),
        S("down", "one of the four attempts to advance ten yards"),
        S("first down", "a new set of four downs, earned by gaining ten yards"),
        S("sack", "tackling the quarterback behind the line of scrimmage"),
        S("fumble", "a ball carrier losing hold of the ball"),
        S("blitz", "extra defenders rushing the quarterback"),
        S("Hail Mary", "a long, desperate pass at the end of a half"),
        S("onside kick", unique=True),
        S("fair catch", unique=True),
        S("holding", "the penalty of illegally grabbing an opponent"),
        S("pick-six", unique=True),
        S("red zone", "the area within twenty yards of the opponent's end zone"),
        S("audible", "a play changed by the quarterback at the line"),
        S("special teams", unique=True),
        S("playbook", "the book of a team's planned plays"),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
