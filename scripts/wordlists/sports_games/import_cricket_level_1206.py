#!/usr/bin/env python3
"""Import the terms of cricket at topic level 1206.

Assembled from the MCC Laws of Cricket and the Wikipedia "Glossary of cricket
terms" (CC BY-SA).  Cricket reuses more everyday English than any other sport
here -- over, maiden, duck, bouncer, century -- so nearly every entry carries a
hint.

"Leg before wicket" carries its abbreviation LBW as a variant.  The cricket
"pitch" is the strip between the wickets, a third meaning distinct from the
baseball throw and from the sports field in the shared list.

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
    level=LEVELS["cricket"],
    domain="cricket",
    label="cricket",
    tags=tags_for("cricket"),
    entries=(
        S("wicket", "the set of stumps and bails a bowler aims at, or a batsman's dismissal"),
        S("stumps", "the three upright posts of a wicket"),
        S("bail", "one of the two small pieces resting on top of the stumps"),
        S("crease", "a line marking where the batsman and bowler stand"),
        S("pitch", "the strip of ground between the two wickets"),
        S("batsman", "a player batting"),
        S("bowler", "the player who delivers the ball to the batsman"),
        S("bowl", "to deliver the ball to the batsman"),
        S("wicketkeeper", unique=True),
        S("innings", "one team's turn to bat"),
        S("over", "a set of six deliveries from one bowler"),
        S("maiden", "an over in which no runs are scored"),
        S("run", "a point scored by running between the wickets"),
        S("boundary", "a hit reaching the edge of the field, scoring four or six"),
        S("century", "a score of 100 runs by one batsman"),
        S("half-century", "a score of 50 runs by one batsman"),
        S("duck", "a score of zero by a batsman"),
        S("leg before wicket", unique=True, abbreviation="LBW"),
        S("run out", "dismissal of a batsman whose wicket is broken while running"),
        S("stump", "to dismiss a batsman who has left the crease, by the wicketkeeper"),
        S("no-ball", unique=True),
        S("wide", "a delivery too far from the batsman to be hit"),
        S("bye", "a run scored when the ball passes the batsman untouched"),
        S("leg bye", unique=True),
        S("googly", unique=True),
        S("yorker", unique=True),
        S("bouncer", "a short delivery that rises toward the batsman's head"),
        S("spinner", "a bowler who spins the ball"),
        S("seamer", "a fast bowler who moves the ball off its seam"),
        S("slip", "a fielding position beside the wicketkeeper"),
        S("gully", "a fielding position near the slips"),
        S("all-rounder", "a player good at both batting and bowling"),
        S("opener", "one of the two batsmen who begin an innings"),
        S("tail-ender", unique=True),
        S("nightwatchman", unique=True),
        S("declare", "to end an innings voluntarily"),
        S("follow-on", unique=True),
        S("hat trick", "three wickets from three consecutive deliveries by one bowler"),
        S("appeal", "a fielder asking the umpire to give a batsman out"),
        S("test match", "an international match played over up to five days"),
        S("sledging", unique=True),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
