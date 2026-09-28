#!/usr/bin/env python3
"""Import the terms of the martial arts and wrestling at topic level 1225.

Assembled from the Wikipedia articles on judo, karate, taekwondo, wushu and
amateur wrestling (CC BY-SA).  The arts themselves are one unit: they share
their ranks, their dress and their halls, and no one of them has enough English
terminology to fill a level alone.  The wrestling terms carry the label
"wrestling".  Mixed martial arts carries its abbreviation MMA.

The ranks "dan" and "kyu" are go's as well, and are here rather than there.

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
    level=LEVELS["martial_arts"],
    domain="martial arts and wrestling",
    label="martial arts",
    tags=tags_for("martial_arts"),
    entries=(
        S("judo", unique=True),
        S("karate", unique=True),
        S("taekwondo", unique=True),
        S("kung fu", unique=True),
        S("wushu", unique=True),
        S("sumo", unique=True),
        S("mixed martial arts", unique=True, abbreviation="MMA"),
        S("dojo", unique=True),
        S("tatami", "the mat the martial arts are practiced on"),
        S("sensei", "a martial arts teacher"),
        S("gi", "the loose white uniform worn for judo and karate"),
        S("belt", "the colored belt showing a student's rank"),
        S("black belt", "the belt of an expert, or a person who holds it"),
        S("dan", "one of the expert grades, held by black belts and strong go players"),
        S("kyu", "one of the student grades below dan"),
        S("kata", unique=True),
        S("ippon", unique=True),
        S("throw", "bringing an opponent to the ground by lifting or tripping"),
        S("takedown", "bringing a standing opponent down to the mat"),
        S("submission", "forcing an opponent to give up with a hold"),
        S("grappling", "fighting by holding and throwing rather than striking"),
        S("armlock", unique=True),
        S("pin", "holding an opponent's shoulders to the mat", disambiguation="wrestling"),
        S("fall", "a win by pinning the opponent", disambiguation="wrestling"),
        S(
            "Greco-Roman",
            "the wrestling style forbidding holds below the waist",
            disambiguation="wrestling",
        ),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
