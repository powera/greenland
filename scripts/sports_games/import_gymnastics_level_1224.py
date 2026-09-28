#!/usr/bin/env python3
"""Import the terms of gymnastics at topic level 1224.

Assembled from the FIG Code of Points and the Wikipedia "Glossary of
gymnastics terms" (CC BY-SA): the apparatus and events, then the moves.

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
    level=LEVELS["gymnastics"],
    domain="gymnastics",
    label="gymnastics",
    tags=tags_for("gymnastics"),
    entries=(
        S("artistic gymnastics", unique=True),
        S("rhythmic gymnastics", unique=True),
        S("apparatus", "a piece of equipment an event is performed on"),
        S("vault", "the event of leaping over a padded table, or the leap itself"),
        S("pommel horse", unique=True),
        S("rings", "two hanging rings the gymnast holds and swings on"),
        S("parallel bars", unique=True),
        S("uneven bars", unique=True),
        S("horizontal bar", unique=True),
        S("balance beam", unique=True),
        S("beam", "the balance beam"),
        S("floor exercise", unique=True),
        S("all-around", "the competition combining every event"),
        S("routine", "a gymnast's complete performance on one apparatus"),
        S("dismount", "the move a gymnast leaves an apparatus with"),
        S("handspring", unique=True),
        S("round-off", unique=True),
        S("salto", unique=True),
        S("tumbling", "a series of flips and handsprings on the floor"),
        S("splits", "a position with the legs stretched flat in opposite directions"),
        S("stick", "to land without moving the feet"),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
