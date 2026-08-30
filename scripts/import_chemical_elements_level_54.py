#!/usr/bin/env python3
"""Import the names of the 118 chemical elements.

Assembled rather than mined.  A frequency list cannot produce this set: the
elements a corpus mentions are the common ones, so oxygen and iron rank while
promethium and darmstadtium never appear at all.  What makes the set worth
having is that it is *closed* -- there are exactly 118, the list is settled,
and a learner who has them has the whole category rather than the dozen that
happened to clear a frequency threshold.

Ordered by atomic number, not by frequency or alphabet.  That is the order the
periodic table is read in and the order the names are learned in, and it keeps
the periods and groups together so a reviewer can see the set is complete.

Spellings are American, not IUPAC: aluminum and cesium rather than aluminium
and caesium.  That is what this database uses -- color, meter, liter, theater,
gray and aluminum are all lemmas here and none of their British spellings is --
and it matters more than a nomenclature standard would, because "aluminum" is
already a lemma at level 8.  Importing the IUPAC spelling would not be a
variant of it; ``words_exist`` would report it absent and the run would mint a
second lemma for the same metal.  ("sulfur" is both the IUPAC and the American
spelling, so it is uncontroversial.)

Not pre-deduplicated against the database.  Every other list here was cut down
to what ``words_exist`` did not already know, but this one is a closed set
whose value is its completeness, and the preflight does that filtering at run
time anyway.  Expect most of the common elements to be reported as already
accounted for.

Level 54 sits above the corpus-derived batches (35-53): these are specialist
vocabulary in the same sense the mathematics list is, learned as a set once the
general vocabulary is in place.

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

DIFFICULTY_LEVEL = 54

# The 118 elements in atomic-number order, 1 (hydrogen) to 118 (oganesson).
# The comment every ten keeps the position checkable without counting: the
# name after each marker is that atomic number.
WORDS: Sequence[str] = (
    # 1-10
    "hydrogen",
    "helium",
    "lithium",
    "beryllium",
    "boron",
    "nitrogen",
    "oxygen",
    "fluorine",
    "neon",
    # 11-20
    "magnesium",
    "aluminum",
    "silicon",
    "phosphorus",
    "sulfur",
    "chlorine",
    "argon",
    "potassium",
    "calcium",
    # 21-30
    "scandium",
    "titanium",
    "vanadium",
    "chromium",
    "manganese",
    "iron",
    "cobalt",
    "nickel",
    "copper",
    "zinc",
    # 31-40
    "gallium",
    "germanium",
    "arsenic",
    "selenium",
    "bromine",
    "krypton",
    "rubidium",
    "strontium",
    "yttrium",
    "zirconium",
    # 41-50
    "niobium",
    "molybdenum",
    "technetium",
    "ruthenium",
    "rhodium",
    "palladium",
    "silver",
    "cadmium",
    "indium",
    "tin",
    # 51-60
    "antimony",
    "tellurium",
    "iodine",
    "xenon",
    "cesium",
    "barium",
    "lanthanum",
    "cerium",
    "praseodymium",
    "neodymium",
    # 61-70
    "promethium",
    "samarium",
    "europium",
    "gadolinium",
    "terbium",
    "dysprosium",
    "holmium",
    "erbium",
    "thulium",
    "ytterbium",
    # 71-80
    "lutetium",
    "hafnium",
    "tantalum",
    "tungsten",
    "rhenium",
    "osmium",
    "iridium",
    "platinum",
    "gold",
    "mercury",
    # 81-90
    "thallium",
    "lead",
    "bismuth",
    "polonium",
    "astatine",
    "radon",
    "francium",
    "radium",
    "actinium",
    "thorium",
    # 91-100
    "protactinium",
    "uranium",
    "neptunium",
    "plutonium",
    "americium",
    "curium",
    "berkelium",
    "californium",
    "einsteinium",
    "fermium",
    # 101-110
    "mendelevium",
    "nobelium",
    "lawrencium",
    "rutherfordium",
    "dubnium",
    "seaborgium",
    "bohrium",
    "hassium",
    "meitnerium",
    "darmstadtium",
    # 111-118
    "roentgenium",
    "copernicium",
    "nihonium",
    "flerovium",
    "moscovium",
    "livermorium",
    "tennessine",
    "oganesson",
)


if __name__ == "__main__":
    raise SystemExit(run_import(WORDS, DIFFICULTY_LEVEL, __doc__ or ""))
