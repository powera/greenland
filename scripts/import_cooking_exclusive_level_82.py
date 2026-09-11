#!/usr/bin/env python3
"""Import the ingredients, utensils and cooking technique vocabulary that only the cooking corpus attests.

Sourced from /word-tokens/corpus-skew?corpus=cooking&exclusive=1 -- not the
Zipf-delta list that levels 66-73 were drawn from, but its companion: the words
this corpus has and no other corpus in the collection does.  A word with no
"elsewhere" cannot be scored, so these are reported apart from the skew ranking;
they are also the sharper list, because being unattested everywhere else is a
stronger claim about a word's domain than merely being commoner here.

Forty broadly useful kitchen words form a general-curriculum sample at level
82. The remaining terms belong to the cooking extension at topic level 110.

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

from scripts.wordlist_import_helper import run_domain_import

DIFFICULTY_LEVEL = 82
TOPIC_DIFFICULTY_LEVEL = 110

# The corpus-exclusive words of cooking on 2026-08-29, ordered by their rank
# within the corpus and cut at 125, reduced to what words_exist does not already
# account for, then curated.  Dropped: capitalized tokens and tokens carrying
# digits or punctuation (proper nouns and possessives the exclusivity test cannot
# separate), tokens under four letters, mangled diacritics left by the corpus
# load ("saut", "cocoanut"), wiki markup fragments and
# participles whose headword survives in the list.  Plurals are dropped whenever
# the singular is an attested word at all, not merely when the singular also
# appears in this list -- the earlier, narrower rule left ~120 plurals behind; a
# few -s words that are their own lemma are kept (blues, goods, ethics, memoirs,
# archives, arts, texts, rights, peoples, relics).  Also dropped: words whose
# exclusivity is
# an accident of this corpus's register rather than a fact about their domain.
#
# A word exclusive to one corpus is by construction absent from the others, so
# these ten lists cannot collide with each other.  Words already claimed by
# import_unlinked_level_65.py and by the skew batches at 66-73 are removed here,
# since those lists were drawn from the same token table.
WORDS: Sequence[str] = (
    "teaspoonful",
    "bake",
    "teaspoon",
    "tablespoonful",
    "grated",
    "saucepan",
    "cupful",
    "quart",
    "tablespoon",
    "vanilla",
    "sieve",
    "nutmeg",
    "paprika",
    "sift",
    "heaping",
    "simmer",
    "garnish",
    "custard",
    "soak",
    "macaroni",
    "molasses",
    "cayenne",
    "gravy",
    "veal",
    "shortening",
    "pare",
    "asparagus",
    "froth",
    "thicken",
    "gelatine",
    "mash",
    "omelet",
    "knead",
    "moisten",
    "cornstarch",
    "aspic",
    "griddle",
    "shredded",
    "flavoring",
    "seasoning",
    "puree",
    "steak",
    "chafing",
    "lukewarm",
    "icing",
    "cracker",
    "cookery",
    "baste",
    "rhubarb",
    "spoonful",
    "sherry",
    "scald",
    "tartar",
    "creamy",
    "citron",
    "currant",
    "allspice",
    "saltspoonful",
    "tapioca",
    "thyme",
    "broth",
    "cress",
    "suet",
    "hominy",
    "rinse",
    "roux",
    "mince",
    "tureen",
    "skim",
    "reheat",
    "chives",
    "marinate",
    "pimento",
    "stuffing",
    "teacupful",
    "sweeten",
    "meringue",
    "tarragon",
    "tart",
    "oatmeal",
    "halibut",
    "muffin",
    "scoop",
    "parboil",
    "horseradish",
    "maraschino",
    "broil",
    "endive",
    "anchovy",
    "mush",
    "clove",
    "cornmeal",
    "frosting",
    "caramel",
    "harden",
    "broiler",
    "casserole",
    "loin",
    "utensil",
    "clam",
    "timbale",
    "grapefruit",
    "marmalade",
    "spiced",
    "peck",
    "molding",
    "strew",
    "forcemeat",
    "fillet",
    "savory",
    "catsup",
    "croutons",
    "marjoram",
    "pecan",
    "spaghetti",
    "fondant",
    "sprig",
    "waffle",
    "arrowroot",
    "dessertspoonful",
    "scum",
    "gallon",
    "codfish",
)

GENERAL_WORDS: Sequence[str] = (
    "bake",
    "teaspoon",
    "tablespoon",
    "grated",
    "saucepan",
    "vanilla",
    "sieve",
    "nutmeg",
    "paprika",
    "sift",
    "simmer",
    "garnish",
    "custard",
    "soak",
    "macaroni",
    "molasses",
    "cayenne",
    "gravy",
    "veal",
    "shortening",
    "asparagus",
    "froth",
    "thicken",
    "mash",
    "omelet",
    "knead",
    "cornstarch",
    "griddle",
    "shredded",
    "flavoring",
    "seasoning",
    "puree",
    "steak",
    "icing",
    "cracker",
    "rhubarb",
    "creamy",
    "broth",
    "rinse",
    "muffin",
)


if __name__ == "__main__":
    raise SystemExit(
        run_domain_import(
            WORDS,
            GENERAL_WORDS,
            DIFFICULTY_LEVEL,
            TOPIC_DIFFICULTY_LEVEL,
            __doc__ or "",
        )
    )
