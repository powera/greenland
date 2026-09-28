#!/usr/bin/env python3
"""Import the vocabulary shared across sports at general level 405.

The words that mean the same thing in several sports: the officials, the
competition (league, season, final), the time (halftime, overtime), the
positions and plays several sports share (goalkeeper, assist, tackle), the net
sports' scoring (serve, rally, set) and the race vocabulary of athletics,
swimming and cycling (lane, heat, lap, relay).  A word whose meaning differs by
sport is not here: "pitch" is the sports field in this list, and the baseball
throw and the cricket strip are in their own units.

This is general vocabulary, not a topic unit, so it sits beside the other
staged imports in the general band.  Many of these already exist from earlier
imports; the server's check tags those rather than duplicating them.
"League", whose sports sense was created at topic level 1040, was moved here
by GUID beforehand.

Running without ``--execute`` only prints the plan and makes no HTTP requests.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.sports_games.levels import SHARED_SPORTS_LEVEL, THEME_TAG
from scripts.wordlist_import_helper import SenseEntry as S
from scripts.wordlist_import_helper import SenseList, run_sense_import

SENSES = SenseList(
    level=SHARED_SPORTS_LEVEL,
    domain="sports in general",
    label="sports",
    tags=(THEME_TAG, "sports"),
    entries=(
        # Officials, teams and people.
        S("referee", "the official who enforces the rules during a match"),
        S("umpire", "an official who rules on play, in baseball, cricket or tennis"),
        S("linesman", "an official who watches the lines"),
        S("line judge", "an official who rules whether the ball is in or out"),
        S("coach", "the person who trains a team or athlete"),
        S("captain", "the player who leads a team"),
        S("teammate", unique=True),
        S("opponent", "the player or team one plays against"),
        S("athlete", "a person who competes in sports"),
        S("spectator", "a person watching a match"),
        S("rookie", "a player in their first season"),
        S("substitute", "a player who comes on to replace another"),
        S("substitution", "replacing one player with another during a match"),
        S("bench", "where the substitutes and coaches sit"),
        S("lineup", "the list of players starting a match"),
        S("forward", "an attacking player"),
        S("defender", "a player whose role is to stop the other side scoring"),
        S("goalkeeper", "the player who guards the goal"),
        S("goalie", "a goalkeeper"),
        S("winger", "an attacking player on the side of the field"),
        # Places.
        S(
            "pitch",
            "the field on which football, rugby or cricket is played",
            disambiguation="sports field",
        ),
        S("field", "the area on which a game is played"),
        S("court", "the marked area for tennis, basketball or volleyball"),
        S("track", "the oval course for running races"),
        S("rink", "an area of ice for skating or hockey"),
        S("stadium", "a sports ground surrounded by seats"),
        S("arena", "an enclosed area for sports events"),
        S("scoreboard", unique=True),
        S("goal line", "the line a ball must cross to score, or the end line of the field"),
        S("goalpost", unique=True),
        S("crossbar", "the bar joining the two goalposts"),
        S("net", "the net dividing the court in tennis, volleyball and badminton"),
        S("baseline", "the line at each end of a court"),
        # Competition.
        S("league", "a group of teams that play one another over a season"),
        S("season", "the part of the year when a sport's matches are played"),
        S("fixture", "a match scheduled for a particular date"),
        S("match", "a contest between two players or teams"),
        S("tournament", "a series of contests to find a winner"),
        S("championship", "a competition to find the best team or player"),
        S("champion", "the winner of a competition"),
        S("title", "the status of being champion"),
        S("trophy", "a cup or other prize for winning"),
        S("medal", "a metal disk awarded to the top finishers"),
        S("podium", "the stand where the first three finishers receive medals"),
        S("final", "the last match, which decides the winner"),
        S("semifinal", "one of the two matches deciding who plays in the final"),
        S("quarterfinal", unique=True),
        S("group stage", unique=True),
        S("seed", "a player or team ranked in advance so the strongest meet late"),
        S("wild card", "an entry to a competition given without qualifying"),
        S("draft", "the annual selection of new players by professional teams"),
        S("transfer", "a player's move from one club to another"),
        S("relegation", "a team's being moved down to a lower division"),
        S("promotion", "a team's being moved up to a higher division"),
        S("upset", "an unexpected win by the weaker side"),
        S("draw", "a match that ends with equal scores"),
        S("tie", "an equal score"),
        S("tiebreak", "a way of deciding a winner when the score is level"),
        S("home advantage", unique=True),
        # Time.
        S("kickoff", "the kick that starts or restarts a match"),
        S("halftime", "the break between the two halves of a match"),
        S("half", "one of the two periods of a match"),
        S("period", "one of the divisions of playing time"),
        S("overtime", "extra playing time when the score is level"),
        S("timeout", "a short break in play called by a team"),
        # Play.
        S("foul", "an action that breaks the rules"),
        S("penalty", "a punishment or free shot awarded for breaking the rules"),
        S("offense", "the team or players trying to score"),
        S("defense", "the team or players trying to stop the other side scoring"),
        S("pass", "sending the ball to a teammate"),
        S("shot", "an attempt to score"),
        S("save", "the goalkeeper stopping a shot"),
        S("assist", "a pass that leads directly to a score"),
        S("dribble", "to move the ball along with repeated small touches or bounces"),
        S("tackle", "taking the ball from an opponent, or bringing the ball carrier down"),
        S("interception", "catching or taking a pass meant for an opponent"),
        S("turnover", "losing possession of the ball to the other side"),
        S("equalizer", "a goal that makes the score level"),
        S("hat trick", "three goals or scores by one player in a game"),
        S("volley", "hitting the ball before it touches the ground"),
        # Net and racket sports.
        S("serve", "to put the ball in play by hitting it to the opponent"),
        S("server", "the player who serves"),
        S("rally", "an exchange of shots before a point is won"),
        S("ace", "a serve the opponent cannot touch"),
        S("set", "a group of games or points counting as one unit of a match"),
        S("match point", "a point that would win the match"),
        S("singles", "a match between two players"),
        S("doubles", "a match between two pairs"),
        S("forehand", "a stroke with the palm facing forward"),
        S("backhand", "a stroke with the back of the hand facing forward"),
        S("smash", "a hard overhead shot hit downward"),
        S("topspin", "forward spin put on a ball"),
        # Races.
        S("race", "a contest of speed"),
        S("lane", "the marked strip each competitor races in"),
        S("heat", "a preliminary race deciding who goes through"),
        S("lap", "one complete circuit of a track or length of a pool"),
        S("relay", "a race in which team members take turns"),
        S("false start", "starting before the signal"),
        S("finish line", unique=True),
        S("photo finish", "a finish so close a photograph decides it"),
        S("personal best", unique=True),
        S("world record", unique=True),
        # Around the sport.
        S("warm-up", "light exercise before a game or race"),
        S("spar", "to practice fighting with a partner"),
        S("mouthguard", unique=True),
        S("doping", "the illegal use of drugs to improve performance"),
        S("sportsmanship", unique=True),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([SENSES], __doc__ or ""))
