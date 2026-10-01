"""Lithuanian paradigms built by rule, for langtools.mechanical_forms.

The word is the lemma's Lithuanian translation.  Verbs need the stored
principal parts (3s_present, 3s_past); nouns use the stored gender and
number_type when there are any.
"""

from typing import Any, Dict, Tuple

from sqlalchemy.orm import Session

from langtools.lt.conjugation import conjugate
from langtools.lt.declension import decline_noun
from langtools.mechanical_forms import Paradigm, read_facts

POS_TYPES: Tuple[str, ...] = ("noun", "verb")

BASE_FORM_KEYS: Dict[str, str] = {
    "noun": "nominative_singular",
    "verb": "infinitive",
}

# decline_noun returns grammatical metadata alongside the case forms; these
# keys describe the paradigm rather than naming a form to store.
NOUN_METADATA_KEYS = frozenset({"number_type", "declension_class", "gender"})


def build_paradigm(
    session: Session, lemma: Any, pos_type: str, language_code: str, word: str
) -> Paradigm:
    """Build the Lithuanian paradigm of *word*."""
    if pos_type == "verb":
        # Lithuanian conjugation is not recoverable from the infinitive
        # alone; both principal parts are stored as grammar facts.
        present_3, past_3 = read_facts(session, lemma.id, "lt", "3s_present", "3s_past")
        if not present_3 or not past_3:
            return None, {}
        return conjugate(word, present_3, past_3), {}

    if pos_type == "noun":
        gender, number_type = read_facts(
            session, lemma.id, "lt", "grammatical_gender", "number_type"
        )
        declined = decline_noun(word, gender, number_type)
        if not declined:
            return None, {}
        # The forms are stored as derivative_forms and the inferred gender as
        # a grammar fact.  Only report a gender the noun did not already have
        # -- a stored gender is what selected the pattern, so re-reporting it
        # would claim the generator derived what it was told.
        metadata: Dict[str, str] = {}
        if declined.get("gender") and not gender:
            metadata["gender"] = declined["gender"]
        return (
            {key: value for key, value in declined.items() if key not in NOUN_METADATA_KEYS},
            metadata,
        )

    return None, {}
