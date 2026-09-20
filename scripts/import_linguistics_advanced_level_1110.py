#!/usr/bin/env python3
"""Import the technical linguistics vocabulary -- the long tail.

The companion to import_linguistics_basic_level_460.py, and the other side of
one dividing line: could a beginner meet this word in an ordinary lesson
instruction?  "Vowel" and "tense" could, and are at 18.  "Allophone" and
"ergative" could not, however close their subject matter, and are here.

Topic level 112. Like the elements this is a specialist set learned as a body
rather than encountered word by word, but unlike the elements it is not closed:
linguistics has no equivalent of "there are exactly 118", so this is a
defensible selection rather than a complete one.

Sourced from the wiki_linguistics corpus, which is what that corpus was built
for -- Wikipedia's Level 5 Language list, 592 articles of grammar, phonetics,
writing systems and language families.  Terms already in the wiki_society
batches at 390 and 1060 are pulled out of those lists in the same change; the
corpus put them there because encyclopedic prose about language is
society-adjacent, which is a fact about the corpus and not about the word.

The list runs both import paths.  The ordinary English terms go through sense
discovery; the borrowings and the writing systems are given with their POS and
definition, because the LLM has no native headword to resolve them to.  See
TERMS below.

Two entries are dual-use.  "Isolate" is a language isolate here and an ordinary
verb elsewhere, and "articulation" is a place of articulation here and a joint
-- or a clearly expressed idea -- elsewhere.  Both are kept for the same reason
"transitive" is (below): add_word resolves senses server-side, so the unrelated
senses do not collide.

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

from scripts.wordlist_import_helper import TermEntry, run_mixed_import

DIFFICULTY_LEVEL = 1110

# Grouped by subfield.  Every one of these is attested in wiki_linguistics;
# the terms a beginner needs went to level 18 instead.
#
# "transitive" also appears at topic level 1080 (wiki_math), the one word shared with
# another list.  The senses are unrelated -- a transitive *relation* and a
# transitive *verb* -- and add_word resolves senses server-side, so the pair is
# kept here rather than split from "intransitive", which is unintelligible
# alone. Words that were merely duplicated (carbon and sodium at 71,
# intonation at 66, lemma at 83) were dropped from the newer list instead,
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
    "linguist",
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
    "phonetic",
    "phonological",
    "phonemic",
    "voiceless",
    "articulation",
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
    "lexicon",
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
    "grammatical",
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
    "cognate",
    # Writing systems.
    "orthography",
    "diacritic",
    "logogram",
    "transliteration",
    "romanization",
    "grapheme",
    "ligature",
    "syllabic",
    # Language change and contact.
    "loanword",
    "borrowing",
    "attested",
    "vernacular",
    "register",
    "colloquial",
    "isolate",
    "corpus",
)

# The writing systems and the language-contact vocabulary, given explicitly.
# Two reasons a term is here rather than in WORDS above.  Most are borrowings
# that every language keeps as themselves -- "abjad" is Arabic, "calque" and
# "koine" French and Greek, "sprachbund" German-inside-English -- so sense
# discovery has no native headword to find and invents a descriptive gloss
# instead, translating that.  "Substrate" is the opposite problem: ordinary
# English whose dominant sense is not this one, so the LLM resolves it to the
# chemistry sense.  Either way the definition is a fact the curated list
# already knows.  ("Proto-" was dropped rather than defined: it is a bound
# prefix, not a word, and nothing is gained by storing it as a lemma.)
TERMS: Sequence[TermEntry] = (
    # Writing systems.
    TermEntry(
        "syllabary",
        "noun",
        "symbolic_element",
        "a writing system whose characters each stand for a syllable",
    ),
    TermEntry(
        "abjad",
        "noun",
        "symbolic_element",
        "a writing system recording consonants only, as in Arabic and Hebrew",
    ),
    TermEntry(
        "abugida",
        "noun",
        "symbolic_element",
        "a writing system whose consonant signs carry an inherent vowel",
    ),
    TermEntry(
        "braille",
        "noun",
        "symbolic_element",
        "a writing system of raised dots read by touch",
    ),
    TermEntry(
        "kanji",
        "noun",
        "symbolic_element",
        "the Chinese characters used in Japanese writing",
    ),
    TermEntry(
        "cuneiform",
        "noun",
        "symbolic_element",
        "the wedge-shaped script of ancient Mesopotamia",
    ),
    # Language contact and change.
    TermEntry(
        "calque",
        "noun",
        "communication_information",
        "a word formed by translating the parts of a foreign expression",
    ),
    TermEntry(
        "koine",
        "noun",
        "communication_information",
        "a common dialect arising from the mixing of related varieties",
    ),
    TermEntry(
        "diglossia",
        "noun",
        "concept_idea",
        "the use of two varieties of a language for separate social purposes",
    ),
    TermEntry(
        "isogloss",
        "noun",
        "concept_idea",
        "a boundary on a map marking where a linguistic feature changes",
    ),
    TermEntry(
        "sprachbund",
        "noun",
        "concept_idea",
        "a group of unrelated languages made alike by long contact",
    ),
    TermEntry(
        "creole",
        "noun",
        "communication_information",
        "a stable language that has developed from a pidgin",
    ),
    TermEntry(
        "pidgin",
        "noun",
        "communication_information",
        "a simplified contact language used between groups with no common tongue",
    ),
    TermEntry(
        "substrate",
        "noun",
        "communication_information",
        "an earlier language leaving traces in the one that displaced it",
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_mixed_import(WORDS, TERMS, DIFFICULTY_LEVEL, __doc__ or ""))
