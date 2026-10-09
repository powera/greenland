#!/usr/bin/env python3
"""Import the terms of rugby at topic level 1212.

Assembled from the World Rugby Laws of the Game and the Wikipedia "Glossary of
rugby union terms" (CC BY-SA).  Rugby union and league share most of this
vocabulary and are one unit.  Terms shared with other sports in the same
meaning -- tackle, kickoff, winger, interception -- are in the shared list at
405.

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
    level=LEVELS["rugby"],
    domain="rugby",
    label="rugby",
    tags=tags_for("rugby"),
    entries=(
        S("try", "grounding the ball over the opponent's goal line, worth five points"),
        S("try line", unique=True),
        S("conversion", "a kick at goal after a try"),
        S("penalty try", unique=True),
        S("drop goal", "a goal kicked from a ball dropped to the ground"),
        S("scrum", "a set piece in which the forwards bind together and push"),
        S("lineout", "throwing the ball in between two lines of players"),
        S("ruck", "players pushing over the ball on the ground"),
        S("maul", "players pushing around a ball carrier who is on his feet"),
        S("breakdown", "the contest for the ball after a tackle"),
        S("knock-on", "losing or knocking the ball forward"),
        S("forward pass", "an illegal pass toward the opponent's goal line"),
        S("offload", "a pass made while being tackled"),
        S("grubber", unique=True),
        S("touch", "the area outside the touchlines"),
        S("sin bin", "a ten-minute suspension from play"),
        S("scrum-half", unique=True),
        S("fly-half", unique=True),
        S("hooker", "the front-row forward who hooks the ball in the scrum"),
        S("prop", "a front-row forward beside the hooker"),
        S("lock", "a second-row forward"),
        S("flanker", "a back-row forward on the side of the scrum"),
        S("fullback", "the last line of defense, at the back"),
        S("sevens", "rugby played seven players a side"),
        S("haka", "a Maori ceremonial dance performed before a match"),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
