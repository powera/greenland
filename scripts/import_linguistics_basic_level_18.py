#!/usr/bin/env python3
"""Import the basic linguistics vocabulary -- the app's own metalanguage.

These are the words a language-learning app uses to talk about itself.  A
learner meets "noun", "vowel", "tense" and "plural" not because the syllabus
reaches grammar as a topic but because every explanation of every other word is
phrased in them: an exercise that says "the plural of this noun" has already
assumed both.  Vocabulary a learner needs in order to be taught belongs early,
whatever its corpus frequency says.

Level 18, which the geography and calendar lemmas vacated (see
relevel_geography_temporal_to_14.py).  That is far earlier than the corpus-
derived batches at 35-53, and deliberately so: "consonant" is not a rare word
in this app's terms even though a general corpus makes it look specialised.

The long tail goes to level 55 instead -- allophone, ergative, morpheme and the
rest of the terms only a linguist needs.  The dividing line is whether a
beginner could meet the word in an ordinary lesson instruction.  "Vowel" and
"tense" pass; "phoneme" and "orthography" do not, however close their subject
matter.

Some of these were previously buried in the wiki_society batches at 41 and 49,
where the corpus put them because encyclopedic prose about language is
society-adjacent.  They are pulled out of those lists in the same change: a
word belongs at the level a learner needs it, not the level its corpus ranks
it.

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

DIFFICULTY_LEVEL = 18

# Grouped by what the word is *about*, so a gap is visible: the parts of
# speech, the sounds, the units of writing, the grammar a beginner is taught,
# and the words for language itself.
#
# Six of these also appeared in later lists (stress at 40, translation at 35,
# capital/object/definition/native at 34) and were removed there rather than
# here.  Every one is a word the app uses to explain other words -- the sense
# wanted is the grammatical "object", not the physical one -- and metalanguage
# has to be available before the lessons that depend on it.
#
# "word", "letter", "language", "sentence" and "speech" are deliberately absent:
# they are already lemmas at levels 16-31.
WORDS: Sequence[str] = (
    # Parts of speech: named in the first grammar explanation a learner reads.
    "noun",
    "verb",
    "adjective",
    "adverb",
    "pronoun",
    "preposition",
    "conjunction",
    # Sounds.
    "vowel",
    "consonant",
    "syllable",
    "accent",
    "pronunciation",
    "stress",
    # Writing.
    "alphabet",
    "spelling",
    "script",
    "capital",
    "punctuation",
    "comma",
    "apostrophe",
    # Grammar a beginner is actually taught.
    "grammar",
    "tense",
    "plural",
    "singular",
    "gender",
    "phrase",
    "clause",
    "subject",
    "object",
    "ending",
    "root",
    "prefix",
    "suffix",
    # Talking about language.
    "dialect",
    "vocabulary",
    "translation",
    "meaning",
    "definition",
    "example",
    "phrasebook",
    "fluent",
    "native",
    "bilingual",
    "literacy",
    "idiom",
    "proverb",
    "synonym",
    "opposite",
    "syntax",
)


if __name__ == "__main__":
    raise SystemExit(run_import(WORDS, DIFFICULTY_LEVEL, __doc__ or ""))
