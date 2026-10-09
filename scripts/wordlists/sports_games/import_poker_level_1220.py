#!/usr/bin/env python3
"""Import the terms of poker at topic level 1220.

Assembled from the Robert's Rules of Poker and the Wikipedia "Glossary of poker
terms" (CC BY-SA): the hand rankings, the betting, and Texas hold 'em's board.
The deck and its handling are at 1205.

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
    level=LEVELS["poker"],
    domain="poker",
    label="poker",
    tags=tags_for("poker"),
    entries=(
        S("Texas hold 'em", unique=True),
        S("pair", "two cards of the same rank"),
        S("two pair", unique=True),
        S("three of a kind", "three cards of the same rank"),
        S("straight", "five cards in sequence"),
        S("flush", "five cards of the same suit"),
        S("full house", "three of a kind together with a pair"),
        S("four of a kind", "four cards of the same rank"),
        S("straight flush", unique=True),
        S("royal flush", unique=True),
        S("high card", "a hand with no combination, ranked by its highest card"),
        S("kicker", "an unpaired card that breaks a tie between equal hands"),
        S("nuts", "the best possible hand at that moment"),
        S("pot", "the money or chips bet in one hand"),
        S("chip", "a token used in place of money"),
        S("ante", "a small bet every player makes before the deal"),
        S("blind", "a forced bet made before the cards are dealt"),
        S("check", "to decline to bet while staying in the hand"),
        S("call", "to match the current bet"),
        S("raise", "to increase the current bet"),
        S("fold", "to give up the hand"),
        S("all-in", "betting all of one's chips"),
        S("bluff", "betting on a weak hand to make others fold"),
        S("tell", "an unconscious sign that gives away a player's hand"),
        S("poker face", "an expression that reveals nothing"),
        S("flop", "the first three shared cards dealt face up"),
        S("turn", "the fourth shared card"),
        S("river", "the fifth and last shared card"),
        S("showdown", "the players revealing their hands at the end"),
        S("button", "the marker showing which player is the nominal dealer"),
        S("bad beat", unique=True),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
