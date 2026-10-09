#!/usr/bin/env python3
"""Import the terms of tennis at topic level 1203.

Assembled from the ITF Rules of Tennis and the Wikipedia "Glossary of tennis
terms" (CC BY-SA).  The racket-sport words that mean the same in badminton,
table tennis and volleyball -- serve, rally, ace, set, singles, forehand -- are
in the shared list at 405.

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
    level=LEVELS["tennis"],
    domain="tennis",
    label="tennis",
    tags=tags_for("tennis"),
    entries=(
        S("love", "a score of zero"),
        S("deuce", "a score of 40-40"),
        S("advantage", "the point won after deuce"),
        S("fault", "a serve that does not land in the service box"),
        S("double fault", unique=True),
        S("foot fault", "a fault for stepping on the baseline while serving"),
        S("let", "a serve that touches the net and is replayed"),
        S("break", "winning a game on the opponent's serve"),
        S("break point", "a point that would win a game on the opponent's serve"),
        S("lob", "a high shot over the opponent's head"),
        S("drop shot", "a soft shot that lands just over the net"),
        S("slice", "a shot hit with backspin"),
        S("groundstroke", unique=True),
        S("passing shot", unique=True),
        S("approach shot", unique=True),
        S("return", "hitting back the opponent's serve"),
        S("unforced error", unique=True),
        S("service line", "the line marking the back of the service box"),
        S("service box", unique=True),
        S("clay court", unique=True),
        S("grass court", unique=True),
        S("hard court", unique=True),
        S("racket", "the strung frame used to hit the ball"),
        S("ball boy", unique=True),
        S("ball girl", unique=True),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
