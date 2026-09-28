#!/usr/bin/env python3
"""Import the terms of card games -- trick-taking, bridge and rummy -- at 1214.

Assembled from the Laws of Duplicate Bridge and the Wikipedia "Glossary of card
game terms" and "Glossary of contract bridge terms" (CC BY-SA).  The deck and
the handling every game shares (suits, deal, shuffle) are at 1205; poker is at
1220.

The general terms carry the label "cards", as the deck vocabulary does; the
ones that exist only in bridge carry "bridge".  "Grand slam" is the bridge
contract for all thirteen tricks, distinct from baseball's.

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
    level=LEVELS["card_games"],
    domain="card games",
    label="cards",
    tags=tags_for("card_games"),
    entries=(
        S("card game", unique=True),
        S("trick", "the cards played by each player in one round, won by one of them"),
        S("trump", "a card of the suit that beats all other suits"),
        S("follow suit", "to play a card of the suit that was led"),
        S("revoke", "failing to follow suit when able to"),
        S("lead", "to play the first card of a trick"),
        S("bid", "an offer to win a number of tricks"),
        S("pass", "to decline to bid"),
        S("meld", "a set of matching cards laid down to score"),
        S("rummy", "a card game of collecting sets and runs", disambiguation="card game"),
        S(
            "bridge",
            "the card game for four players in two partnerships",
            disambiguation="card game",
        ),
        S("hearts", "a card game in which players avoid taking hearts", disambiguation="card game"),
        S("no-trump", "a contract played without a trump suit", disambiguation="bridge"),
        S("contract", "the final bid, which the declarer must make", disambiguation="bridge"),
        S("declarer", unique=True),
        S("dummy", "the declarer's partner, whose cards are laid face up", disambiguation="bridge"),
        S("rubber", "a match won by the first side to win two games", disambiguation="bridge"),
        S("grand slam", "a contract to win all thirteen tricks", disambiguation="bridge"),
        S("small slam", unique=True),
        S(
            "finesse",
            "trying to win a trick with a card that is not the highest",
            disambiguation="bridge",
        ),
        S("redouble", "to double an opponent's double of one's bid", disambiguation="bridge"),
        S("vulnerable", "facing larger penalties after winning a game", disambiguation="bridge"),
        S("overtrick", unique=True),
        S("undertrick", unique=True),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
