#!/usr/bin/env python3
"""Import the linguistics, philosophy, religion and the social sciences vocabulary that only the wiki_society corpus attests.

Sourced from /word-tokens/corpus-skew?corpus=wiki_society&exclusive=1 -- not the
Zipf-delta list that levels 35-42 were drawn from, but its companion: the words
this corpus has and no other corpus in the collection does.  A word with no
"elsewhere" cannot be scored, so these are reported apart from the skew ranking;
they are also the sharper list, because being unattested everywhere else is a
stronger claim about a word's domain than merely being commoner here.

Level 49 continues from the skew batches at 35-42, reusing their corpora in
the same order.  These lists are disjoint; see the note on the word list below.

The language and linguistics terms this list originally carried moved to
import_linguistics_basic_level_18.py and import_linguistics_advanced_level_55.py.
The corpus put them here because encyclopedic prose about language sits inside
the Level 4 Society list, which is a fact about the corpus rather than about
the words: "noun" and "vowel" are the app's own metalanguage and belong early,
and "phoneme" and "orthography" belong with the rest of the technical tail.

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

DIFFICULTY_LEVEL = 49

# The corpus-exclusive words of wiki_society on 2026-08-29, ordered by their rank
# within the corpus and cut at 125, reduced to what words_exist does not already
# account for, then curated.  Dropped: capitalized tokens and tokens carrying
# digits or punctuation (proper nouns and possessives the exclusivity test cannot
# separate), tokens under four letters, mangled diacritics left by the corpus
# load ("vara", "socio"), wiki markup fragments and
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
    "grammatical",
    "sociology",
    "anthropology",
    "phonetic",
    "capitalism",
    "baptism",
    "epistemology",
    "metaphysical",
    "metaphysics",
    "phonological",
    "capitalist",
    "underworld",
    "liturgical",
    "sociological",
    "afterlife",
    "rebirth",
    "cognition",
    "dharma",
    "normative",
    "organizational",
    "authoritarian",
    "materialism",
    "orthodox",
    "hadith",
    "jinn",
    "dualism",
    "activism",
    "globalization",
    "racism",
    "archaic",
    "empathy",
    "ontological",
    "veneration",
    "phonemic",
    "determinism",
    "monotheistic",
    "spirituality",
    "denomination",
    "voiceless",
    "idealism",
    "mystical",
    "braille",
    "theologian",
    "monism",
    "kanji",
    "circumcision",
    "esoteric",
    "humanistic",
    "syllabic",
    "heresy",
    "liberalism",
    "mantra",
    "communal",
    "anthropologist",
    "lexicon",
    "colloquial",
    "innate",
    "linguist",
    "isolate",
    "humanitarian",
    "sociologist",
    "atheism",
    "euthanasia",
    "cuneiform",
    "schism",
    "naturalism",
    "reincarnation",
    "phenomenology",
    "anarchism",
    "socialization",
    "cremation",
    "ontology",
    "pantheon",
    "positivism",
    "articulation",
    "worldview",
    "epistemological",
    "colonialism",
    "cannibalism",
    "smuggling",
    "anthropological",
    "celibacy",
    "rabbinic",
    "interpersonal",
    "monastic",
    "paganism",
    "solidarity",
    "witchcraft",
    "humanism",
    "libertarian",
    "rationalism",
    "utilitarianism",
    "hierarchical",
    "causality",
    "evangelical",
    "stratification",
    "halal",
    "theistic",
    "fallacy",
    "nirvana",
    "empiricism",
    "kosher",
    "liturgy",
    "epithet",
    "taboo",
    "tantric",
    "rabbi",
    "feminism",
    "methodological",
    "ecumenical",
)


if __name__ == "__main__":
    raise SystemExit(run_import(WORDS, DIFFICULTY_LEVEL, __doc__ or ""))
