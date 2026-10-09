#!/usr/bin/env python3
"""Import the terms of xiangqi (Chinese chess) at topic level 1217.

Assembled from the Asian Xiangqi Federation rules and the Wikipedia article on
xiangqi (CC BY-SA).  The pieces have conventional English names that are
ordinary words (general, elephant, cannon), which the hints tie to the game;
Chinese and Vietnamese have the game's native vocabulary.

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
    level=LEVELS["xiangqi"],
    domain="xiangqi (Chinese chess)",
    label="xiangqi",
    tags=tags_for("xiangqi"),
    entries=(
        S("xiangqi", unique=True),
        S("Chinese chess", unique=True),
        S("general", "the piece that must be protected, like the king in chess"),
        S("advisor", "a piece that guards the general inside the palace"),
        S("elephant", "a piece that moves two points diagonally and cannot cross the river"),
        S("horse", "a piece that moves like a chess knight but can be blocked"),
        S("chariot", "a piece that moves in straight lines, like a rook"),
        S("cannon", "a piece that captures by jumping over one other piece"),
        S("soldier", "a pawn-like piece that moves forward"),
        S("river", "the empty middle row dividing the board"),
        S("palace", "the three-by-three area the general must stay in"),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
