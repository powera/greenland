#!/usr/bin/env python3
"""Import the terms of association football at topic level 1200.

Assembled from the IFAB Laws of the Game and the Wikipedia "Glossary of
association football terms" (CC BY-SA).  The label is "football", the name
nearly every target language uses; American football is its own unit at 1207.

Terms football shares with other sports in the same meaning -- referee, foul,
goalkeeper, kickoff, hat trick -- are in the shared list at 405, not here.

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
    level=LEVELS["football"],
    domain="association football (soccer)",
    label="football",
    tags=tags_for("football"),
    entries=(
        S("offside", "an attacker being ahead of the last defender when the ball is played"),
        S("corner kick", unique=True),
        S("corner", "a corner kick"),
        S("free kick", "a kick awarded after a foul, taken without interference"),
        S("penalty kick", "a shot from the penalty spot with only the goalkeeper to beat"),
        S("penalty area", "the marked box in front of each goal"),
        S("penalty spot", "the mark from which a penalty kick is taken"),
        S("penalty shootout", "a series of penalty kicks to decide a drawn match"),
        S("goal kick", unique=True),
        S("throw-in", unique=True),
        S("header", "hitting the ball with the head"),
        S("stoppage time", unique=True),
        S("extra time", "two extra periods played when a knockout match is drawn"),
        S("clean sheet", "a match in which a team concedes no goal"),
        S("own goal", "a goal a player accidentally scores against their own team"),
        S("midfielder", unique=True),
        S("midfield", "the middle area of the pitch, or the players who play there"),
        S("center back", "a central defender"),
        S("fullback", "a defender playing on the side of the defense"),
        S("sweeper", "a defender playing behind the other defenders"),
        S("yellow card", "a caution shown by the referee"),
        S("red card", "a card shown by the referee to send a player off"),
        S("booking", "a caution recorded against a player"),
        S("send off", "to order a player to leave the field for the rest of the match"),
        S("handball", "the offense of touching the ball with the hand or arm"),
        S("dive", "falling on purpose to win a foul"),
        S("nutmeg", "playing the ball between an opponent's legs"),
        S("cross", "a pass from the side of the pitch into the penalty area"),
        S("through ball", "a pass played into the space behind the defenders"),
        S("one-two", "a quick exchange of passes between two players"),
        S("chip", "a lofted shot or pass"),
        S("bicycle kick", unique=True),
        S("slide tackle", unique=True),
        S("clearance", "kicking the ball away from one's own goal"),
        S("set piece", "a planned play from a free kick, corner or throw-in"),
        S("wall", "a line of defenders blocking a free kick"),
        S("touchline", "the line along each long side of the pitch"),
        S("derby", "a match between two local rivals"),
        S("assistant referee", "an official on the touchline who signals offside"),
        S("video assistant referee", unique=True, abbreviation="VAR"),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
