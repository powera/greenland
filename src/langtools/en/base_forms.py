"""The English base (dictionary) grammatical form for each part of speech."""

from typing import Dict

from storage.models.enums import GrammaticalForm

# Base (dictionary) form per part of speech, for English. The definitions
# prompt analyses one English word per definition, so the form follows from the
# POS -- there is nothing to ask the LLM about. Language-tagged ("en_") values
# only; the untagged generic forms (verb/infinitive, noun/singular, ...) are
# deprecated because they carry no language code.
#
# The en_ members are added by _auto_extend_grammatical_form() at import time
# and are not real class attributes, so they must be looked up by name via
# GrammaticalForm[...] rather than GrammaticalForm.NAME.
EN_BASE_FORM_BY_POS: Dict[str, str] = {
    "verb": GrammaticalForm["VERB_EN_INFINITIVE"].value,
    "noun": GrammaticalForm["NOUN_EN_SINGULAR"].value,
    "adjective": GrammaticalForm["ADJ_EN_POSITIVE"].value,
    "adverb": GrammaticalForm["ADVERB_EN_POSITIVE"].value,
    "pronoun": GrammaticalForm["PRONOUN_EN_SUBJECTIVE"].value,
    "preposition": GrammaticalForm.PREPOSITION.value,
    "conjunction": GrammaticalForm.CONJUNCTION.value,
    "interjection": GrammaticalForm.INTERJECTION.value,
    "determiner": GrammaticalForm.DETERMINER.value,
    "numeral": GrammaticalForm["NUMERAL_EN_CARDINAL"].value,
    "article": GrammaticalForm["ARTICLE_EN_BASE"].value,
}


def en_base_form(pos_type: str) -> str:
    """Return the English base-form grammatical form for ``pos_type``."""
    return EN_BASE_FORM_BY_POS.get(pos_type.lower(), GrammaticalForm.OTHER.value)
