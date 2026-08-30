#!/usr/bin/env python3
"""Import the geography vocabulary that leans toward the wiki_geography corpus.

Sourced from /word-tokens/corpus-skew?corpus=wiki_geography -- the words whose Zipf
here is furthest above their Zipf in the other corpora, which is what surfaces
physical geography and settlement, from terrain and climate to the vocabulary of towns and administration rather than the function words a raw frequency list would return.

Level 37 places this with the other corpus-skew batches (35-41, one per
Wikipedia corpus except wiki_math): specialised vocabulary a learner meets well
after the core.  These lists are disjoint; see the note on the word list below.

This script deliberately uses the public ``ROOT/api`` facade.  In particular,
``api.lemmas.add_word`` runs Barsukas' intelligent word workflow: the server's
LLM identifies the senses and supplies their translations, then the server
selects and stores the useful senses.  The script never supplies definitions or
translations itself.

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

DIFFICULTY_LEVEL = 37

# The top 200 rows of /word-tokens/corpus-skew?corpus=wiki_geography on 2026-08-29,
# reduced to what words_exist does not already account for, then curated:
# capitalized tokens are dropped (proper-noun residue the skew score cannot
# separate -- River, Empire, Shakespeare), along with possessives and
# participles whose headword is already in the list.  Plurals are dropped
# whenever the singular is an attested word at all, not merely when the
# singular also appears in this list -- the earlier, narrower rule left ~120
# plurals behind.  A few -s words that are their own lemma are kept (blues,
# goods, ethics, memoirs, archives, arts, texts, rights, peoples, relics), tokenization and markup
# fragments (sup, fa, et, al, de, non), and URL debris still in the database
# from the pre-fix corpus load (com, web).
#
# A word that scores in more than one corpus is assigned to whichever corpus it
# leans toward hardest, so these lists are disjoint and a word cannot be
# imported twice at two different levels.  Words already claimed by
# import_unlinked_level_34.py are removed here for the same reason.
WORDS: Sequence[str] = (
    "metropolitan",
    "downtown",
    "mayor",
    "climate",
    "border",
    "located",
    "province",
    "eastern",
    "economy",
    "urban",
    "independence",
    "territory",
    "southern",
    "provincial",
    "railway",
    "western",
    "populated",
    "route",
    "football",
    "municipality",
    "rainy",
    "founded",
    "district",
    "centre",
    "rural",
    "settlement",
    "geographically",
    "situated",
    "president",
    "headquarters",
    "trading",
    "waterway",
    "canal",
    "annual",
    "outskirts",
    "inland",
    "administered",
    "million",
    "historic",
    "traffic",
    "summit",
    "boom",
    "inhabited",
    "destination",
    "tourist",
    "southeast",
    "sector",
    "industrial",
    "regional",
    "coastal",
    "shipping",
    "ethnic",
    "northeast",
    "colonial",
    "northwest",
    "heritage",
    "defeated",
    "mainland",
    "transit",
)


if __name__ == "__main__":
    raise SystemExit(run_import(WORDS, DIFFICULTY_LEVEL, __doc__ or ""))
