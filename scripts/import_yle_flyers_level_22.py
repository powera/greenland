#!/usr/bin/env python3
"""Import the Cambridge YLE A2 Flyers words the database is still missing.

the third Cambridge YLE band: school subjects,
transport, and the adjectives for describing people.

The list is the gap between ``data/cambridge/yle_wordlist.json`` and the
lemma table, computed with ``wordfreq.tiers.cambridge_yle.CambridgeYleImporter``
-- the same resolver that populates ``lemma_tiers`` -- so a word counted missing
here is one that importer could not resolve to any lemma, by text or by POS.

Filtered out of the raw gap before this list was written:

* function words and modals (``the``, ``his``, ``must``, ``shall``), which the
  curriculum handles as grammar rather than vocabulary;
* inflected forms of lemmas we already have (``feet``, ``mice``, ``teeth``);
* UK spellings of existing US lemmas (``colour``, ``pyjamas``, ``yoghurt``).

Where YLE carries a sense hint, or where the word is a homograph of a lemma we
already hold, the intended sense is noted in a comment above the word. The
server's LLM still chooses the senses -- ``api.lemmas.add_word`` takes only the
word -- so those notes are for the reviewer of the pending queue, not the API.

Running without ``--execute`` only prints the plan and makes no HTTP requests.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.wordlist_import_helper import run_import

DIFFICULTY_LEVEL = 22

# 111 words, grouped by their YLE theme.
WORDS: Sequence[str] = (
    # Animals
    "beetle",
    "dinosaur",
    "extinct",
    "nest",
    "tortoise",
    # Clothes
    "costume",
    # Filed under Clothes in YLE -- the headwear.
    "crown",
    # Patterned, not the past tense of spot.
    "spotted",
    "stripe",
    "striped",
    "sunglasses",
    "uniform",
    # Family & friends
    "surname",
    # Food & drink
    "biscuit",
    "cereal",
    "cookie",
    "olives",
    # General
    "adventure",
    "arrive",
    "businessman",
    "chat",
    # The verb (to ride a bike).
    "cycle",
    "delicious",
    "expensive",
    "explore",
    "fetch",
    "file",
    "fire engine",
    "frightening",
    "furry",
    "horrible",
    "interesting",
    "lovely",
    "mix",
    "pleased",
    "popular",
    "postcard",
    "repeat",
    # Noun and verb.
    "search",
    "spend",
    # Adjective and verb.
    "tidy",
    "unfriendly",
    "unhappy",
    "unkind",
    "untidy",
    "unusual",
    "wifi",
    "wonderful",
    # Health
    # YLE sense hint "chemist’s" -- the UK pharmacy, not the scientist.
    "chemist",
    "x-ray",
    # Numbers
    "million",
    "thousand",
    # Places & directions
    # The social club, not the weapon.
    "club",
    "college",
    "skyscraper",
    "theatre",
    "university",
    # School
    "backpack",
    # UK "bin" = US trash can.
    "bin",
    "dictionary",
    # Noun and verb.
    "glue",
    "rucksack",
    "student",
    "timetable",
    # Sports & leisure
    "cartoon",
    # The TV channel sense.
    "channel",
    "diary",
    "drum",
    "festival",
    "invitation",
    "magazine",
    "member",
    "pop music",
    "prize",
    "quiz",
    "rock music",
    # starters/movers sense is the verb (to score a goal); flyers adds the noun.
    "score",
    # Noun and verb.
    "ski",
    "snowball",
    "snowboard",
    "snowboarding",
    "snowman",
    # The playground swing (noun) and the motion (verb).
    "swing",
    # The melody sense.
    "tune",
    "violin",
    "winner",
    # The home
    # UK "cooker" = US stove.
    "cooker",
    "entrance",
    "fridge",
    "shampoo",
    # The world around us
    "Earth",
    "environment",
    "exit",
    # Time
    "calendar",
    "midday",
    # Transport
    "motorway",
    "passenger",
    "platform",
    # YLE sense hint "racing car; bike" -- attributive use.
    "racing",
    "railway",
    "rocket",
    "spaceship",
    # The journey sense.
    "tour",
    "traffic",
    # Weather
    "foggy",
    # Work
    "astronaut",
    "designer",
    "fire fighter",
    "newspaper",
    "queen",
    "singer",
)

# Multi-word expressions YLE lists that are not lemmas in their own right.
# They are grammar to be taught in a sentence, not vocabulary to be looked up,
# so they are recorded here and deliberately not imported:
#     "as ... as",
#     "at the moment",
#     "by myself",
#     "by yourself",
#     "of course",
#     "straight on",


def main() -> int:
    return run_import(WORDS, DIFFICULTY_LEVEL, __doc__ or "")


if __name__ == "__main__":
    raise SystemExit(main())
