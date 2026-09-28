#!/usr/bin/env python3
"""Import the terms of checkers (draughts) at topic level 1208.

Assembled from the World Draughts Federation rules and the Wikipedia articles
on draughts (CC BY-SA).  A short list: the game has few terms of its own, and
the general ones -- board, piece, capture, move -- are in the shared games list
at 406.  The label is "checkers", the US name; "draughts" is here as the game's
British name.

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
    level=LEVELS["checkers"],
    domain="checkers (draughts)",
    label="checkers",
    tags=tags_for("checkers"),
    entries=(
        S(
            "checkers",
            "the board game played with round pieces on a checkered board",
            disambiguation="board game",
        ),
        S("draughts", "the British name for checkers", disambiguation="board game"),
        S("checker", "one of the round playing pieces"),
        S("checkerboard", "the board of 64 light and dark squares"),
        S("man", "an ordinary piece that has not been crowned"),
        S("king", "a piece crowned on reaching the far row, able to move backward"),
        S("crown", "to make a piece a king by stacking a second piece on it"),
        S("king row", unique=True),
        S("jump", "to capture a piece by leaping over it"),
        S("double jump", "two captures in one move"),
        S("huff", "to remove a piece that failed to make a required capture"),
        S("flying king", unique=True),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
