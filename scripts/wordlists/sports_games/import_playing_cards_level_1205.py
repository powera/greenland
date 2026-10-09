#!/usr/bin/env python3
"""Import the vocabulary of playing cards at topic level 1205.

The deck itself -- suits, ranks, face cards -- and the handling every card game
shares (shuffle, deal, draw, discard), kept apart from the terms of particular
games: trick-taking and bridge are at 1214, poker at 1220.

Suits are singular headwords ("heart", "spade"), and the hints name the suit
itself as the existing club and spade senses do.  Hints that named "a card of
the suit" made the model treat those as different senses and duplicate them.

The queen of cards (level 200) and the existing senses of "suit", "club" and
"spade" (level 460) were moved here by GUID before this list first ran, so the
list finds them by their tags.

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
    level=LEVELS["playing_cards"],
    domain="playing cards",
    label="cards",
    tags=tags_for("playing_cards"),
    entries=(
        S("playing card", unique=True),
        S("deck", "a full set of 52 playing cards"),
        S("pack", "a deck of cards"),
        S("suit", "one of the four sets of cards: hearts, diamonds, clubs and spades"),
        S("heart", "the suit marked with red hearts, or a card of it"),
        S("diamond", "the suit marked with red diamonds, or a card of it"),
        S("club", "the suit marked with black clovers, or a card of it"),
        S("spade", "the suit marked with black spades, or a card of it"),
        S("ace", "the card with a single symbol, usually ranking highest"),
        S("king", "the card bearing a picture of a king"),
        S("queen", "the card bearing a picture of a queen"),
        S("jack", "the card bearing a picture of a young man, ranking below the queen"),
        S("joker", "an extra card with a jester, often used as a wild card"),
        S("face card", unique=True),
        S("deuce", "a card with the number two"),
        S("wild card", "a card that can stand for any other card"),
        S("shuffle", "to mix the cards into a random order"),
        S("deal", "to give out cards to the players"),
        S("dealer", "the player who deals the cards"),
        S("cut", "to divide the deck in two and swap the halves"),
        S("hand", "the cards a player is holding"),
        S("draw", "to take a card from the deck"),
        S("discard", "to put down a card one does not want"),
        S("face down", "with the front of the card hidden"),
        S("face up", "with the front of the card showing"),
        S("solitaire", "a card game for one player", disambiguation="card game"),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
