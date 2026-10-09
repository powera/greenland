#!/usr/bin/env python3
"""Import the vocabulary shared across board and table games at level 406.

The words that mean the same thing in chess, checkers, go, backgammon, mahjong
and the rest: the board and its squares, the pieces, taking turns, dice, and
winning and losing.  Like the shared sports list at 405, this is general
vocabulary in the general band; the terms of any one game are in its own unit.

Running without ``--execute`` only prints the plan and makes no HTTP requests.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.wordlists.sports_games.levels import SHARED_GAMES_LEVEL, THEME_TAG
from scripts.wordlists.wordlist_import_helper import SenseEntry as S
from scripts.wordlists.wordlist_import_helper import SenseList, run_sense_import

SENSES = SenseList(
    level=SHARED_GAMES_LEVEL,
    domain="board and table games in general",
    label="games",
    tags=(THEME_TAG, "games"),
    entries=(
        S("board game", unique=True),
        S("board", "the flat surface a board game is played on"),
        S("square", "one of the spaces on a board"),
        S("piece", "one of the objects moved in a board game"),
        S("counter", "a small disk used as a piece"),
        S("token", "a small object marking a player's place"),
        S("tile", "a flat piece used in games such as mahjong and dominoes"),
        S("domino", "a small rectangular tile marked with dots"),
        S("die", "a small cube with one to six dots, thrown in games"),
        S("dice", "small cubes with dots, thrown in games"),
        S("roll", "to throw dice"),
        S("move", "one player's action on their turn"),
        S("turn", "a player's chance to move"),
        S("capture", "to take an opponent's piece off the board"),
        S("resign", "to give up a game before it is over"),
        S("forfeit", "to lose a game by not playing or by breaking the rules"),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
