#!/usr/bin/env python3
"""Import the modern life vocabulary that leans toward the wiki_modern_life corpus.

Sourced from /word-tokens/corpus-skew?corpus=wiki_modern_life -- the words whose Zipf
here is furthest above their Zipf in the other corpora, which is what surfaces
everyday material life and technology -- appliances, clothing, sport, computing and transport rather than the function words a raw frequency list would return.

Level 39 places this with the other corpus-skew batches (35-41, one per
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

DIFFICULTY_LEVEL = 39

# The top 200 rows of /word-tokens/corpus-skew?corpus=wiki_modern_life on 2026-08-29,
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
    "switch",
    "receiver",
    "player",
    "armour",
    "coil",
    "parking",
    "device",
    "aircraft",
    "sport",
    "gin",
    "spinning",
    "woven",
    "ammunition",
    "launch",
    "fibre",
    "alcoholic",
    "mechanical",
    "protocol",
    "conditioning",
    "kite",
    "efficiency",
    "fuel",
    "powered",
    "tank",
    "stored",
    "engineering",
    "packaging",
    "firing",
    "electrical",
    "circuit",
    "mounted",
    "storage",
    "equipment",
    "digital",
    "consumption",
    "embroidery",
    "opponent",
    "dial",
    "wireless",
    "file",
    "user",
    "shaft",
    "signal",
    "dam",
    "manufactured",
    "arcade",
    "injection",
    "vehicle",
    "dairy",
    "cable",
    "league",
    "code",
    "jet",
    "adolescents",
    "handling",
    "equipped",
    "exit",
    "inventor",
    "lever",
    "technology",
    "prostitution",
    "penetration",
    "access",
    "expensive",
    "racing",
    "weaving",
    "drilling",
    "proprietary",
    "conventional",
    "plough",
    "polo",
    "combat",
    "operating",
    "gaming",
    "toilet",
    "outdoor",
    "drying",
    "manufacturing",
    "parenting",
    "display",
    "coated",
)


if __name__ == "__main__":
    raise SystemExit(run_import(WORDS, DIFFICULTY_LEVEL, __doc__ or ""))
