#!/usr/bin/env python3
"""Import the terms of backgammon at topic level 1226.

Assembled from the Wikipedia "Glossary of backgammon terms" (CC BY-SA).  The
pieces are "checkers", the same word and object as in checkers at 1208, so
they are not repeated here; dice and rolling are in the shared games list.

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
    level=LEVELS["backgammon"],
    domain="backgammon",
    label="backgammon",
    tags=tags_for("backgammon"),
    entries=(
        S("backgammon", unique=True),
        S("point", "one of the 24 long triangles on the board"),
        S("bar", "the raised strip dividing the board, where hit checkers wait"),
        S("home board", unique=True),
        S("blot", "a single checker alone on a point, open to being hit"),
        S("hit", "to land on an opponent's blot and send it to the bar"),
        S("prime", "six blocked points in a row"),
        S("anchor", "two of one's checkers on a point in the opponent's home board"),
        S("bear off", "to remove checkers from the board at the end of the game"),
        S("pip", "one point of distance a checker moves"),
        S("double", "to offer to double the stakes"),
        S("doubling cube", unique=True),
        S("gammon", "a win before the opponent has borne off any checker"),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
