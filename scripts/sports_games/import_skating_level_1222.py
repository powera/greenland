#!/usr/bin/env python3
"""Import the terms of figure and speed skating at topic level 1222.

Assembled from the ISU Special Regulations and the Wikipedia "Glossary of
figure skating terms" (CC BY-SA).  The jumps are named after their inventors
(axel, lutz, salchow) and are ordinary lowercase terms of the sport.  The speed
skating terms carry the label "speed skating"; the rink is in the shared list
at 405.

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
    level=LEVELS["skating"],
    domain="figure skating and speed skating",
    label="figure skating",
    tags=tags_for("skating"),
    entries=(
        S("axel", unique=True),
        S("lutz", unique=True),
        S("salchow", unique=True),
        S("toe loop", unique=True),
        S("flip", "a jump taken off from the back inside edge with a toe pick"),
        S("quad", "a jump with four rotations"),
        S("spin", "rotating on the spot on one skate"),
        S("camel spin", unique=True),
        S("sit spin", unique=True),
        S("death spiral", unique=True),
        S("edge", "the inside or outside of the skate blade"),
        S("toe pick", unique=True),
        S("pairs", "skating by a man and a woman together"),
        S("ice dance", unique=True),
        S("short program", unique=True),
        S("free skate", unique=True),
        S("kiss and cry", unique=True),
        S("speed skating", unique=True),
        S(
            "short track",
            "speed skating on a small oval track in packs",
            disambiguation="speed skating",
        ),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
