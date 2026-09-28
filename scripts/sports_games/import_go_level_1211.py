#!/usr/bin/env python3
"""Import the terms of go (weiqi, baduk) at topic level 1211.

Assembled from the AGA and Japanese rules and the Wikipedia "Go terms" article
(CC BY-SA).  Go's English vocabulary is largely borrowed from Japanese (atari,
ko, sente, joseki); the prompt asks each language for its usual term, which for
Chinese is the native weiqi vocabulary rather than the Japanese loan.

The ranks (dan, kyu) are shared with the martial arts and are in that list at
1225.

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
    level=LEVELS["go"],
    domain="the board game go (weiqi, baduk)",
    label="go",
    tags=tags_for("go"),
    entries=(
        S(
            "go",
            "the board game of surrounding territory with black and white stones",
            disambiguation="board game",
        ),
        S("goban", unique=True),
        S("stone", "one of the black or white playing pieces"),
        S("point", "an intersection of lines where a stone can be placed"),
        S("liberty", "an empty point next to a stone or group"),
        S("group", "stones of one color connected together"),
        S("atari", "a position in which a stone or group can be captured next move"),
        S("ko", "a repeating capture that the rules forbid immediately retaking"),
        S("eye", "an empty point surrounded by one player's stones"),
        S("territory", "the empty points a player has surrounded"),
        S("ladder", "a chase that captures stones along a diagonal"),
        S("net", "a loose surrounding move that traps a stone"),
        S("life and death", "whether a group can avoid capture"),
        S("seki", unique=True),
        S("sente", unique=True),
        S("gote", unique=True),
        S("komi", unique=True),
        S("joseki", unique=True),
        S("fuseki", unique=True),
        S("pass", "declining to place a stone on one's turn"),
        S("handicap", "stones placed in advance to even out players of different strength"),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
