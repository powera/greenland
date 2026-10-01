"""French paradigms built by rule.

Used by langtools.mechanical_forms (bootstrap, release export) and by the rules-first
path in langtools.fr.llm_forms, so the two produce the same forms.  The word is
the lemma's French translation; nouns read the plural and number_type facts,
adjectives the feminine_form fact.
"""

from typing import Any, Dict, Tuple

from sqlalchemy.orm import Session

from langtools.fr.conjugation import conjugate
from langtools.fr.inflection import build_adjective_forms, build_noun_forms
from langtools.mechanical_forms import Paradigm, read_facts

POS_TYPES: Tuple[str, ...] = ("noun", "adjective", "verb")

BASE_FORM_KEYS: Dict[str, str] = {
    "noun": "singular",
    "adjective": "singular_m",
    "verb": "infinitive",
}


def build_paradigm(
    session: Session, lemma: Any, pos_type: str, language_code: str, word: str
) -> Paradigm:
    """Build the French paradigm of *word*."""
    if pos_type == "noun":
        irregular_plural, number_type = read_facts(session, lemma.id, "fr", "plural", "number_type")
        return build_noun_forms(word, irregular_plural, number_type), {}
    if pos_type == "adjective":
        (feminine_form,) = read_facts(session, lemma.id, "fr", "feminine_form")
        return build_adjective_forms(word, feminine_form), {}
    if pos_type == "verb":
        return conjugate(word), {}
    return None, {}
