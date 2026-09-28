#!/usr/bin/env python3
"""Import the terms of ice hockey at topic level 1209.

Assembled from the IIHF Official Rule Book and the Wikipedia "Glossary of ice
hockey terms" (CC BY-SA).  Terms shared with other sports in the same meaning
-- rink, period, goaltender's "save", hat trick, winger -- are in the shared
list at 405.

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
    level=LEVELS["ice_hockey"],
    domain="ice hockey",
    label="ice hockey",
    tags=tags_for("ice_hockey"),
    entries=(
        S("puck", "the hard rubber disk played with"),
        S("hockey stick", "the stick used to handle the puck"),
        S("faceoff", "dropping the puck between two players to restart play"),
        S("icing", "shooting the puck from one's own half across the far goal line"),
        S("power play", "playing with more players because an opponent is serving a penalty"),
        S("penalty kill", "defending while a teammate serves a penalty"),
        S("short-handed", "playing with fewer players because of a penalty"),
        S("penalty box", "the bench where penalized players sit out"),
        S("slap shot", unique=True),
        S("wrist shot", unique=True),
        S("one-timer", "a shot hit straight off a pass without stopping the puck"),
        S("blue line", "one of the two lines dividing the rink into zones"),
        S("red line", "the center line of the rink"),
        S("crease", "the marked area in front of the goal"),
        S("boards", "the wall around the rink"),
        S("check", "blocking an opponent with the body or stick"),
        S("cross-checking", unique=True),
        S("high-sticking", unique=True),
        S("tripping", "the penalty of making an opponent fall"),
        S("boarding", "the penalty of pushing an opponent violently into the boards"),
        S("goaltender", "the goalkeeper"),
        S("defenseman", unique=True),
        S("center", "the forward who plays in the middle and takes faceoffs"),
        S("enforcer", "a player whose role is to deter and fight opponents"),
        S("empty net", "a goal left unguarded after the goaltender is pulled"),
        S("shootout", "a series of one-on-one shots to decide a tied game"),
        S("stickhandling", unique=True),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
