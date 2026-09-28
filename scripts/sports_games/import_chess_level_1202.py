#!/usr/bin/env python3
"""Import the terms of chess at topic level 1202.

Assembled from the FIDE Laws of Chess and the Wikipedia "Glossary of chess"
(CC BY-SA): the pieces, the special moves, the tactics and the phases of the
game.  General game words -- capture, resign, draw -- are in the shared lists
at 405 and 406.

The chess queen already existed, created at level 200 with no disambiguation;
it was moved here by GUID before this list first ran, so the list finds it by
its tags.  "King" exists only as the monarch, so the chess king is a new sense.

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
    level=LEVELS["chess"],
    domain="chess",
    label="chess",
    tags=tags_for("chess"),
    entries=(
        S("chessboard", unique=True),
        S("king", "the piece that must be protected from checkmate"),
        S("queen", "the most powerful piece"),
        S("rook", "the castle-shaped piece that moves in straight lines"),
        S("bishop", "the piece that moves diagonally"),
        S("knight", "the horse-shaped piece that moves in an L shape"),
        S("pawn", "the smallest piece, which moves forward one square"),
        S("check", "an attack on the opponent's king"),
        S("checkmate", unique=True),
        S("mate", "short for checkmate"),
        S("stalemate", "a position with no legal move that is not check, ending in a draw"),
        S("castle", "to move the king two squares toward a rook and the rook past it"),
        S("castling", unique=True),
        S("en passant", unique=True),
        S("promotion", "a pawn becoming another piece on reaching the last rank"),
        S("promote", "to turn a pawn into another piece"),
        S("file", "a vertical column of squares"),
        S("rank", "a horizontal row of squares"),
        S("diagonal", "a slanting line of squares of one color"),
        S("opening", "the first moves of a game"),
        S("middlegame", unique=True),
        S("endgame", "the final stage of a game, with few pieces left"),
        S("gambit", "an opening that sacrifices material for position"),
        S("sacrifice", "giving up a piece to gain an advantage"),
        S("exchange", "trading pieces of equal value"),
        S("fork", "one piece attacking two at once"),
        S("pin", "a piece that cannot move without exposing a more valuable piece"),
        S("skewer", "an attack through a valuable piece to one behind it"),
        S("discovered check", unique=True),
        S("perpetual check", unique=True),
        S("threefold repetition", unique=True),
        S("zugzwang", unique=True),
        S("fianchetto", unique=True),
        S("tempo", "a move's worth of time"),
        S("develop", "to bring pieces off their starting squares"),
        S("blunder", "a very bad move"),
        S("grandmaster", "the highest title awarded to a chess player"),
        S("time control", "the time allowed for a game or a number of moves"),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
