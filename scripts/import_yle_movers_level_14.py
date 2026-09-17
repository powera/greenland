#!/usr/bin/env python3
"""Import the Cambridge YLE A1 Movers words the database is still missing.

the second Cambridge YLE band: weather, hobbies,
the body, and the places a child goes.

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

DIFFICULTY_LEVEL = 14

# 70 words, grouped by their YLE theme.
WORDS: Sequence[str] = (
    # Animals
    "cage",
    "kitten",
    "puppy",
    # Clothes
    "swimsuit",
    # Family & friends
    "grown-up",
    # Food & drink
    "milkshake",
    "noodles",
    "sauce",
    "thirsty",
    "vegetable",
    # General
    "boring",
    "city centre",
    "clever",
    "difference",
    "e-book",
    "exciting",
    "invite",
    "jungle",
    "naughty",
    "shopping centre",
    "treasure",
    "weak",
    # Health
    "earache",
    "stomach-ache",
    "toothache",
    # Numbers
    "hundred",
    "pair",
    # Places & directions
    "café",
    "car park",
    "cinema",
    "circus",
    "funfair",
    "sports centre",
    "supermarket",
    "town centre",
    # School
    # The verb (to text someone) and the noun.
    "text",
    # Sports & leisure
    "CD",
    "DVD",
    "comic",
    # Noun and verb.
    "dance",
    # UK "film" = US "movie" (already a lemma); YLE also lists the verb.
    "film",
    "goal",
    # UK "holiday" = US "vacation"; neither is a lemma yet.
    "holiday",
    "hop",
    "ice skates",
    "player",
    # The swimming pool sense.
    "pool",
    "roller skates",
    "roller skating",
    # starters/movers sense is the verb (to score a goal); flyers adds the noun.
    "score",
    # Noun and verb.
    "skate",
    # Noun and verb.
    "video",
    # The body and the face
    "beard",
    # YLE prints "blond/e"; the -e spelling is a variant, not a separate word.
    "blond",
    "curly",
    # The home
    "address",
    "downstairs",
    # YLE lists US "elevator" against UK "lift" (a verb lemma already).
    "elevator",
    "shower",
    "toothpaste",
    # The world around us
    "countryside",
    "village",
    "world",
    # Weather
    "cloudy",
    "rainbow",
    "sunny",
    "windy",
    # Work
    "clown",
    "pirate",
    "pop star",
)

# Multi-word expressions YLE lists that are not lemmas in their own right.
# They are grammar to be taught in a sentence, not vocabulary to be looked up,
# so they are recorded here and deliberately not imported:
#     "all right",
#     "o’clock",


def main() -> int:
    return run_import(WORDS, DIFFICULTY_LEVEL, __doc__ or "")


if __name__ == "__main__":
    raise SystemExit(main())
