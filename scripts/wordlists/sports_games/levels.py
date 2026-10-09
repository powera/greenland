"""Levels and tags for the sports-and-games wordlists in this directory.

One topic level per sport or game, 1200-1226, with the games interleaved among
the sports rather than banded after them: a level number in the topic band is
a unit's identity, not a teaching order, and nothing about chess makes it come
after tennis.  Levels 1227-1249 are left for sports added later.

The vocabulary shared across sports (referee, overtime, relay) and across games
(dice, capture, resign) is general vocabulary rather than any one unit's, so it
goes in the general band at 405 and 406, beside the other staged imports.

Every sense these scripts create or match is tagged with the theme and with its
unit, so a re-run recognises its own work without an LLM call and a sport can be
selected without reading level numbers.
"""

from __future__ import annotations

from typing import Mapping

THEME_TAG = "sports_games"

SHARED_SPORTS_LEVEL = 405
SHARED_GAMES_LEVEL = 406

LEVELS: Mapping[str, int] = {
    "football": 1200,
    "basketball": 1201,
    "chess": 1202,
    "tennis": 1203,
    "baseball": 1204,
    "playing_cards": 1205,
    "cricket": 1206,
    "american_football": 1207,
    "checkers": 1208,
    "ice_hockey": 1209,
    "golf": 1210,
    "go": 1211,
    "rugby": 1212,
    "boxing": 1213,
    "card_games": 1214,
    "athletics": 1215,
    "swimming": 1216,
    "xiangqi": 1217,
    "cycling": 1218,
    "volleyball": 1219,
    "poker": 1220,
    "skiing": 1221,
    "skating": 1222,
    "mahjong": 1223,
    "gymnastics": 1224,
    "martial_arts": 1225,
    "backgammon": 1226,
}


def tags_for(unit: str) -> tuple[str, str]:
    """The tags for one unit's senses: the theme, then the unit."""
    return (THEME_TAG, unit)
