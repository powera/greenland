#!/usr/bin/env python3
"""Import the terms of mahjong at topic level 1223.

Assembled from the Wikipedia articles on mahjong and mahjong tiles (CC BY-SA).
The tile suits and honors have ordinary English names that the hints tie to the
game.  The melds are left out: English has no shared word for them across the
variants (pung/kong/chow in Chinese-style rules, pon/kan/chi in riichi, and no
chow at all in American mahjong), and "pair" is the general sense.  "Tile" itself is in the shared games list at 406, since dominoes and
other games use it the same way.

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
    level=LEVELS["mahjong"],
    domain="mahjong",
    label="mahjong",
    tags=tags_for("mahjong"),
    entries=(
        S("mahjong", "the tile game for four players", disambiguation="tile game"),
        S("wall", "the square of stacked tiles that tiles are drawn from"),
        S("bamboo", "one of the three suits of tiles"),
        S("character", "one of the three suits of tiles, marked with Chinese numerals"),
        S("circle", "one of the three suits of tiles, marked with round coins or dots"),
        S("honor tile", unique=True),
        S("dragon", "one of the red, green and white honor tiles"),
        S("wind", "one of the four honor tiles named for compass directions"),
        S("flower", "a bonus tile"),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
