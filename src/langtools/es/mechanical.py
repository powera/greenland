"""Spanish paradigms built by rule, for es and es-419.

Used by langtools.mechanical_forms (bootstrap, release export) and by the rules-first
path in langtools.es.llm_forms, so the two produce the same forms.  The word is
the lemma's translation in the variety asked for; es-419 differs only in the 2p
verb slot, which takes the ustedes form.  Nouns read the plural and number_type
facts.

Verb forms come back under their registry slot names: the conjugator's
preterite fills "past", and the tenses with no slot (imperfect, conditional,
subjunctive, imperative) are dropped.
"""

from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import Session

from langtools.es.conjugation import conjugate_for_dialect
from langtools.es.forms_config import VERB_CONFIG
from langtools.es.inflection import build_adjective_forms, build_noun_forms
from langtools.form_patterns import expand_fields
from langtools.mechanical_forms import Paradigm, read_facts

POS_TYPES: Tuple[str, ...] = ("noun", "adjective", "verb")

BASE_FORM_KEYS: Dict[str, str] = {
    "noun": "singular",
    "adjective": "singular_m",
    "verb": "infinitive",
}

_VERB_SLOTS: List[str] = expand_fields(VERB_CONFIG)

# Registry slots the conjugator fills under the same name.
_NON_FINITE_FORMS = ("infinitive", "gerund", "past_participle")

# "past" is the preterite, which is how the existing sentence data uses
# verb/es_*_past ("compró", "encontró", "vio"), and the simple past both
# varieties use.
_PAST_SOURCE = "preterite"


def project_verb_forms(forms: Dict[str, str]) -> Dict[str, str]:
    """Project the conjugator's full output onto the registry's verb slots."""
    projected: Dict[str, str] = {}
    for slot in _VERB_SLOTS:
        if slot in _NON_FINITE_FORMS:
            source_key = slot
        else:
            person, tense = slot.split("_", 1)
            source_key = f"{person}_{_PAST_SOURCE}" if tense == "past" else slot
        value = forms.get(source_key)
        if value:
            projected[slot] = value
    return projected


def build_paradigm(
    session: Session, lemma: Any, pos_type: str, language_code: str, word: str
) -> Paradigm:
    """Build the Spanish (es or es-419) paradigm of *word*."""
    if pos_type == "noun":
        irregular_plural, number_type = read_facts(
            session, lemma.id, language_code, "plural", "number_type"
        )
        return build_noun_forms(word, irregular_plural, number_type), {}
    if pos_type == "adjective":
        # Adjective agreement is the same in every Spanish variety.
        return build_adjective_forms(word), {}
    if pos_type == "verb":
        conjugated = conjugate_for_dialect(word, language_code)
        if not conjugated:
            return None, {}
        return project_verb_forms(conjugated) or None, {}
    return None, {}
