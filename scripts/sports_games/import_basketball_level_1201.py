#!/usr/bin/env python3
"""Import the terms of basketball at topic level 1201.

Assembled from the FIBA Official Basketball Rules and the Wikipedia "Glossary
of basketball terms" (CC BY-SA).  Basketball is the sport Lithuanian learners
are most likely to follow, so its list is one of the fuller ones.

Terms shared with other sports in the same meaning -- court, assist, turnover,
timeout, baseline -- are in the shared list at 405.

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
    level=LEVELS["basketball"],
    domain="basketball",
    label="basketball",
    tags=tags_for("basketball"),
    entries=(
        S("basket", "the hoop and net, or a score made through it"),
        S("hoop", "the metal ring the ball is thrown through"),
        S("rim", "the metal ring of the basket"),
        S("backboard", "the board behind the basket"),
        S("free throw", "an unopposed shot awarded after a foul"),
        S("three-pointer", "a shot from beyond the arc, worth three points"),
        S("layup", unique=True),
        S("dunk", "to push the ball down through the basket"),
        S("slam dunk", "a forceful dunk"),
        S("jump shot", "a shot taken while jumping"),
        S("hook shot", "a one-handed shot swung over the head"),
        S("bank shot", "a shot that bounces off the backboard into the basket"),
        S("jump ball", "a ball tossed up between two players to start play"),
        S("tip-off", "the jump ball that starts a game"),
        S("rebound", "catching the ball after a missed shot"),
        S("block", "stopping a shot by touching the ball"),
        S("steal", "taking the ball from an opponent"),
        S("fast break", "a quick attack before the defense is set"),
        S("alley-oop", unique=True),
        S("crossover", "a dribble switching the ball from one hand to the other"),
        S("screen", "standing in a defender's way to free a teammate"),
        S("pick and roll", unique=True),
        S("traveling", "moving with the ball without dribbling"),
        S("double dribble", unique=True),
        S("shot clock", unique=True),
        S("buzzer beater", unique=True),
        S("air ball", unique=True),
        S("swish", "a shot that goes in without touching the rim"),
        S("paint", "the painted area under the basket"),
        S("point guard", unique=True),
        S("shooting guard", unique=True),
        S("center", "the tallest player, who plays near the basket"),
        S("power forward", unique=True),
        S("small forward", unique=True),
        S("personal foul", "a foul involving illegal contact with an opponent"),
        S("technical foul", "a foul for unsporting behavior rather than contact"),
        S("double-double", unique=True),
        S("triple-double", unique=True),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
