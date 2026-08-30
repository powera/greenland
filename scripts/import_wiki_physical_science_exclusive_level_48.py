#!/usr/bin/env python3
"""Import the chemistry, physics, astronomy and geology vocabulary that only the wiki_physical_science corpus attests.

Sourced from /word-tokens/corpus-skew?corpus=wiki_physical_science&exclusive=1 -- not the
Zipf-delta list that levels 35-42 were drawn from, but its companion: the words
this corpus has and no other corpus in the collection does.  A word with no
"elsewhere" cannot be scored, so these are reported apart from the skew ranking;
they are also the sharper list, because being unattested everywhere else is a
stronger claim about a word's domain than merely being commoner here.

Level 48 continues from the skew batches at 35-42, reusing their corpora in
the same order.  These lists are disjoint; see the note on the word list below.

The 35 element names this list originally carried (helium, uranium, tungsten,
...) moved to import_chemical_elements_level_54.py, which takes all 118 as a
closed set rather than the arbitrary subset one corpus happens to attest.  What
is left reads as what it always should have: a physical-science *concepts*
list -- processes, quantities, particles and rock types.

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

DIFFICULTY_LEVEL = 48

# The corpus-exclusive words of wiki_physical_science on 2026-08-29, ordered by their rank
# within the corpus and cut at 125, reduced to what words_exist does not already
# account for, then curated.  Dropped: capitalized tokens and tokens carrying
# digits or punctuation (proper nouns and possessives the exclusivity test cannot
# separate), tokens under four letters, mangled diacritics left by the corpus
# load ("mrna", "coli"), wiki markup fragments and
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
# import_unlinked_level_34.py and by the skew batches at 35-42 are removed here,
# since those lists were drawn from the same token table.
WORDS: Sequence[str] = (
    "galaxy",
    "neutron",
    "oxidation",
    "radioactive",
    "bonding",
    "isotope",
    "proton",
    "sulfate",
    "luminosity",
    "hydroxide",
    "spectroscopy",
    "fission",
    "photon",
    "phosphate",
    "convection",
    "dipole",
    "ionic",
    "ammonium",
    "thermodynamic",
    "inorganic",
    "ozone",
    "dioxide",
    "quark",
    "resonance",
    "viscosity",
    "sulfuric",
    "interstellar",
    "valence",
    "supernova",
    "ionization",
    "covalent",
    "magma",
    "fluoride",
    "weathering",
    "sulfide",
    "asteroid",
    "monoxide",
    "shear",
    "accretion",
    "cosmological",
    "inertia",
    "inertial",
    "alkaline",
    "replication",
    "silica",
    "conductivity",
    "methyl",
    "boson",
    "silicate",
    "ethylene",
    "electrostatic",
    "debris",
    "hydrochloric",
    "methanol",
    "fructose",
    "solubility",
    "elemental",
    "electrolysis",
    "electromagnetism",
    "coupling",
    "lithosphere",
    "benzene",
    "fermions",
    "enthalpy",
    "refractive",
    "reactor",
    "geologic",
    "igneous",
    "metamorphic",
    "formaldehyde",
    "equinox",
    "albedo",
    "carboxylic",
    "shale",
    "cyanide",
    "redshift",
    "anion",
    "mitosis",
    "vortex",
    "seawater",
    "testosterone",
    "propane",
    "chlorophyll",
    "neutrino",
    "peroxide",
    "catalytic",
    "bicarbonate",
    "urea",
    "hydrolysis",
    "acetone",
)


if __name__ == "__main__":
    raise SystemExit(run_import(WORDS, DIFFICULTY_LEVEL, __doc__ or ""))
