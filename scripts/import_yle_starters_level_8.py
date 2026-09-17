#!/usr/bin/env python3
"""Import the Cambridge YLE Pre A1 Starters words the database is still missing.

the first Cambridge YLE band: the vocabulary of a
classroom, a family and a toybox.

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

DIFFICULTY_LEVEL = 8

# 58 words, grouped by their YLE theme.
WORDS: Sequence[str] = (
    # Animals
    "hippo",
    "jellyfish",
    "lizard",
    "pet",
    # Clothes
    "clothes",
    "handbag",
    # Family & friends
    "classmate",
    "dad",
    "grandma",
    "grandpa",
    "kid",
    "mum",
    # Food & drink
    "burger",
    "candy",
    "chips",
    "fries",
    "kiwi",
    "meatballs",
    "pie",
    # General
    "clap",
    "double",
    "fun",
    "scary",
    "silly",
    "tablet",
    "ugly",
    # Places & directions
    "bookshop",
    "playground",
    # School
    "English",
    "alphabet",
    "classroom",
    "crayon",
    "cupboard",
    # YLE sense hint "computer" -- not the piano keyboard.
    "keyboard",
    "poster",
    "ruler",
    # YLE: the checkmark, not the insect.
    "tick",
    # Sports & leisure
    "TV",
    "bike",
    "bounce",
    "football",
    "hobby",
    "kite",
    "piano",
    "skateboard",
    "sport",
    "tennis racket",
    # The home
    "mat",
    "rug",
    "sofa",
    # The world around us
    # The seashell, not a shell casing.
    "shell",
    # Time
    "birthday",
    # Toys
    "alien",
    "balloon",
    "lorry",
    "motorbike",
    "robot",
    # YLE sense hint "bear".
    "teddy",
)


def main() -> int:
    return run_import(WORDS, DIFFICULTY_LEVEL, __doc__ or "")


if __name__ == "__main__":
    raise SystemExit(main())
