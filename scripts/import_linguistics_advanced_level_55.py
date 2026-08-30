#!/usr/bin/env python3
"""Import the technical linguistics vocabulary -- the long tail.

The companion to import_linguistics_basic_level_18.py, and the other side of
one dividing line: could a beginner meet this word in an ordinary lesson
instruction?  "Vowel" and "tense" could, and are at 18.  "Allophone" and
"ergative" could not, however close their subject matter, and are here.

Level 55, above the corpus batches at 35-53 and the elements at 54.  Like the
elements this is a specialist set learned as a body rather than encountered
word by word, but unlike the elements it is not closed: linguistics has no
equivalent of "there are exactly 118", so this is a defensible selection rather
than a complete one.

Sourced from the wiki_linguistics corpus, which is what that corpus was built
for -- Wikipedia's Level 5 Language list, 592 articles of grammar, phonetics,
writing systems and language families.  Terms already in the wiki_society
batches at 41 and 49 are pulled out of those lists in the same change; the
corpus put them there because encyclopedic prose about language is
society-adjacent, which is a fact about the corpus and not about the word.

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

DIFFICULTY_LEVEL = 55

# Grouped by subfield.  Every one of these is attested in wiki_linguistics;
# the terms a beginner needs went to level 18 instead.
#
# "transitive" also appears at level 52 (wiki_math), the one word shared with
# another list.  The senses are unrelated -- a transitive *relation* and a
# transitive *verb* -- and add_word resolves senses server-side, so the pair is
# kept here rather than split from "intransitive", which is unintelligible
# alone.  Words that were merely duplicated (carbon and sodium at 40,
# intonation at 35, lemma at 52) were dropped from the newer list instead,
# since a learner should meet a word at the earlier level.
WORDS: Sequence[str] = (
    # The field and its branches.
    "linguistics",
    "linguistic",
    "phonetics",
    "phonology",
    "morphology",
    "semantics",
    "pragmatics",
    "sociolinguistics",
    "etymology",
    "philology",
    "typology",
    "lexicography",
    # Sound structure.
    "phoneme",
    "allophone",
    "diphthong",
    "fricative",
    "plosive",
    "sibilant",
    "nasal",
    "glottal",
    "palatal",
    "velar",
    "labial",
    "rhotic",
    "sonorant",
    "prosody",
    "tone",
    "assimilation",
    # Word structure.
    "morpheme",
    "affix",
    "infix",
    "clitic",
    "reduplication",
    "derivation",
    "compounding",
    "lexeme",
    "inflection",
    "declension",
    "conjugation",
    "paradigm",
    # Grammar and syntax.
    "ergative",
    "accusative",
    "nominative",
    "genitive",
    "dative",
    "ablative",
    "locative",
    "vocative",
    "aspect",
    "mood",
    "valency",
    "transitive",
    "intransitive",
    "copula",
    "determiner",
    "modifier",
    "agreement",
    "anaphora",
    "deixis",
    # Meaning.
    "semantic",
    "lexical",
    "polysemy",
    "homonym",
    "hyponym",
    "connotation",
    "denotation",
    "metonymy",
    "calque",
    "cognate",
    # Writing systems.
    "orthography",
    "diacritic",
    "logogram",
    "syllabary",
    "abjad",
    "abugida",
    "transliteration",
    "romanization",
    "grapheme",
    "ligature",
    # Language change and contact.
    "substrate",
    "creole",
    "pidgin",
    "koine",
    "diglossia",
    "isogloss",
    "sprachbund",
    "loanword",
    "borrowing",
    "attested",
    "proto",
    "vernacular",
    "register",
    "corpus",
)


if __name__ == "__main__":
    raise SystemExit(run_import(WORDS, DIFFICULTY_LEVEL, __doc__ or ""))
