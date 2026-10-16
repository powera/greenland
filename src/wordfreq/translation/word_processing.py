#!/usr/bin/python3

"""English grammatical-form heuristics for words added from a definitions call."""

import logging

from storage.models.enums import GrammaticalForm
from langtools.en.base_forms import EN_BASE_FORM_BY_POS

logger = logging.getLogger(__name__)

# Inflected English forms used by the suffix heuristics below.
_EN_INFLECTED = {
    name: GrammaticalForm[name].value
    for name in (
        "VERB_EN_PRESENT_PARTICIPLE",
        "VERB_EN_PAST_PARTICIPLE",
        "NOUN_EN_PLURAL",
        "ADJ_EN_COMPARATIVE",
        "ADJ_EN_SUPERLATIVE",
        "ADVERB_EN_COMPARATIVE",
        "ADVERB_EN_SUPERLATIVE",
    )
}


def determine_default_grammatical_form(word_text: str, pos_type: str, lemma_text: str) -> str:
    """
    Determine the English grammatical form for a word given its POS and lemma.

    The definitions and sense calls analyse one English word and do not ask for
    its grammatical form, so the form is derived here rather than asked for.
    When the word is its own lemma the form is the POS's base form; otherwise a
    few suffix heuristics cover the common inflections.
    """
    pos_lower = pos_type.lower()

    if word_text == lemma_text:
        return str(EN_BASE_FORM_BY_POS.get(pos_lower, GrammaticalForm.OTHER.value))

    # Basic heuristics for English inflected forms
    if pos_lower == "verb":
        if word_text.endswith("ing"):
            return str(_EN_INFLECTED["VERB_EN_PRESENT_PARTICIPLE"])
        elif word_text.endswith("ed"):
            return str(_EN_INFLECTED["VERB_EN_PAST_PARTICIPLE"])

    elif pos_lower == "noun":
        if word_text.endswith("s") and not lemma_text.endswith("s"):
            return str(_EN_INFLECTED["NOUN_EN_PLURAL"])

    elif pos_lower == "adjective":
        if word_text.endswith("er"):
            return str(_EN_INFLECTED["ADJ_EN_COMPARATIVE"])
        elif word_text.endswith("est"):
            return str(_EN_INFLECTED["ADJ_EN_SUPERLATIVE"])

    elif pos_lower == "adverb":
        if word_text.endswith("er"):
            return str(_EN_INFLECTED["ADVERB_EN_COMPARATIVE"])
        elif word_text.endswith("est"):
            return str(_EN_INFLECTED["ADVERB_EN_SUPERLATIVE"])

    return str(GrammaticalForm.OTHER.value)
