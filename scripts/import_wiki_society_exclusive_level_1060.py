#!/usr/bin/env python3
"""Import the linguistics, philosophy, religion and the social sciences vocabulary that only the wiki_society corpus attests.

Sourced from /word-tokens/corpus-skew?corpus=wiki_society&exclusive=1 -- not the
Zipf-delta list that levels 330-400 were drawn from, but its companion: the words
this corpus has and no other corpus in the collection does.  A word with no
"elsewhere" cannot be scored, so these are reported apart from the skew ranking;
they are also the sharper list, because being unattested everywhere else is a
stronger claim about a word's domain than merely being commoner here.

Topic level 107 joins the tail of the ranked society list. These
corpus-exclusive words are too domain-specific for the general curriculum.

The language and linguistics terms live in import_linguistics_basic_level_460.py
and import_linguistics_advanced_level_1110.py, not here.  The corpus attests
them here because encyclopedic prose about language sits inside the Level 4
Society list, which is a fact about the corpus rather than about the words:
"noun" and "vowel" are the app's own metalanguage and belong early, and
"phoneme", "orthography" and the writing-system and phonetics terms belong with
the rest of the technical tail.

This script deliberately uses the public ``ROOT/api`` facade.  In particular,
``api.lemmas.add_word`` runs Barsukas' intelligent word workflow: the server's
LLM identifies the senses and supplies their translations, then the server
selects and stores the useful senses.  The wordlist supplies no definitions or
translations of its own.

The religious borrowings are the exception, and go through ``add_term`` with
their POS and definition supplied.  See TERMS below.

Running without ``--execute`` only prints the plan and makes no HTTP requests.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.wordlist_import_helper import TermEntry, run_mixed_import

DIFFICULTY_LEVEL = 1060

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
# import_unlinked_level_320.py and by the skew batches at 330-400 are removed here,
# since those lists were drawn from the same token table.
WORDS: Sequence[str] = (
    "sociology",
    "anthropology",
    "capitalism",
    "baptism",
    "epistemology",
    "metaphysical",
    "metaphysics",
    "capitalist",
    "underworld",
    "liturgical",
    "sociological",
    "afterlife",
    "rebirth",
    "cognition",
    "normative",
    "organizational",
    "authoritarian",
    "materialism",
    "orthodox",
    "dualism",
    "activism",
    "globalization",
    "racism",
    "archaic",
    "empathy",
    "ontological",
    "veneration",
    "determinism",
    "monotheistic",
    "spirituality",
    "denomination",
    "idealism",
    "mystical",
    "theologian",
    "monism",
    "circumcision",
    "esoteric",
    "humanistic",
    "heresy",
    "liberalism",
    "communal",
    "anthropologist",
    "innate",
    "humanitarian",
    "sociologist",
    "atheism",
    "euthanasia",
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
    "worldview",
    "epistemological",
    "colonialism",
    "cannibalism",
    "smuggling",
    "anthropological",
    "celibacy",
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
    "theistic",
    "fallacy",
    "empiricism",
    "liturgy",
    "epithet",
    "taboo",
    "feminism",
    "methodological",
    "ecumenical",
)

# The religious vocabulary the corpus attests here, given explicitly rather than
# sent through sense discovery.  Each is a borrowing that the target languages
# take unchanged or transliterate, so there is no native English headword for
# the LLM to find: asked what "halal" means it settles on "permissible" and
# translates that instead, which is a different word and lands the entry in the
# pending queue.  The definition below is what the term denotes; the server is
# asked for the translations alone.
TERMS: Sequence[TermEntry] = (
    TermEntry(
        "dharma",
        "noun",
        "mental_construct",
        "the moral law and duty underlying Hindu and Buddhist teaching",
    ),
    TermEntry(
        "hadith",
        "noun",
        "communication_information",
        "a recorded saying or act of Muhammad, used as a source of Islamic law",
    ),
    TermEntry(
        "jinn",
        "noun",
        "human",
        "a spirit of Islamic belief, able to appear in human or animal form",
    ),
    TermEntry(
        "mantra",
        "noun",
        "communication_information",
        "a word or phrase repeated in meditation or prayer",
    ),
    TermEntry(
        "nirvana",
        "noun",
        "abstract_condition",
        "the release from suffering and rebirth sought in Buddhism",
    ),
    TermEntry(
        "halal",
        "adjective",
        "belief_cultural",
        "permitted under Islamic law, especially of food",
    ),
    TermEntry(
        "kosher",
        "adjective",
        "belief_cultural",
        "prepared according to Jewish dietary law",
    ),
    TermEntry(
        "rabbi",
        "noun",
        "human",
        "a Jewish religious leader and teacher of the law",
    ),
    TermEntry(
        "rabbinic",
        "adjective",
        "belief_cultural",
        "of rabbis or the Jewish legal tradition they developed",
    ),
    TermEntry(
        "tantric",
        "adjective",
        "belief_cultural",
        "of the esoteric ritual texts and practices of Tantra",
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_mixed_import(WORDS, TERMS, DIFFICULTY_LEVEL, __doc__ or ""))
