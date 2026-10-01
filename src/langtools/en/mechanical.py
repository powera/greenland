"""English paradigms built by rule, for langtools.mechanical_forms.

The word is the lemma text.  The builders read countability, number_type,
gradability, the irregular plural/comparative/superlative, and the verb
principal parts (past, past_participle) from the lemma's grammar facts.
"""

from typing import Any, Callable, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from langtools.en.conjugation import expand_verb_forms
from langtools.en.inflection import build_adjective_forms, build_adverb_forms, build_noun_forms
from langtools.mechanical_forms import Paradigm, read_facts

POS_TYPES: Tuple[str, ...] = ("noun", "adjective", "adverb", "verb")

USES_LEMMA_TEXT = True

BASE_FORM_KEYS: Dict[str, str] = {
    "noun": "singular",
    "adjective": "positive",
    "adverb": "positive",
    "verb": "infinitive",
}

# Builder output key -> GrammaticalForm value, per POS. Keys absent from a
# builder's result (a non-gradable adverb has no comparative) are simply not
# written; that is a correct paradigm, not a gap.
FORM_KEYS: Dict[str, Dict[str, str]] = {
    "noun": {
        "singular": "noun/en_singular",
        "plural": "noun/en_plural",
    },
    "adjective": {
        "positive": "adjective/en_positive",
        "comparative": "adjective/en_comparative",
        "superlative": "adjective/en_superlative",
    },
    "adverb": {
        "positive": "adverb/en_positive",
        "comparative": "adverb/en_comparative",
        "superlative": "adverb/en_superlative",
    },
    "verb": {
        "infinitive": "verb/en_infinitive",
        "past": "verb/en_3s_past",
        "past_participle": "verb/en_past_participle",
        "present_participle": "verb/en_present_participle",
        "3s_present": "verb/en_3s_present",
    },
}


def build_paradigm(
    session: Session, lemma: Any, pos_type: str, language_code: str, word: str
) -> Paradigm:
    """Build the English paradigm of *word* (the lemma text)."""
    if pos_type == "noun":
        countability, number_type, irregular_plural = read_facts(
            session, lemma.id, "en", "countability", "number_type", "plural"
        )
        return build_noun_forms(word, countability, number_type, irregular_plural), {}

    if pos_type in ("adjective", "adverb"):
        gradability, comparative, superlative = read_facts(
            session, lemma.id, "en", "gradability", "comparative", "superlative"
        )
        builder: Callable[..., Optional[Dict[str, str]]] = (
            build_adjective_forms if pos_type == "adjective" else build_adverb_forms
        )
        return builder(word, gradability, comparative, superlative), {}

    if pos_type == "verb":
        past, past_participle = read_facts(session, lemma.id, "en", "past", "past_participle")
        # expand_verb_forms always returns a table; an irregular verb with no
        # stored past would get a wrong regular one, so require the facts.
        if not past or not past_participle:
            return None, {}
        paradigm = expand_verb_forms(
            {"infinitive": word, "past": past, "past_participle": past_participle}
        )
        # The full conjugator exposes person-specific past keys, while this
        # compact storage task keeps one representative simple-past slot.
        paradigm["past"] = past
        return paradigm, {}

    return None, {}


def build_variant_paradigm(
    session: Session, lemma: Any, pos_type: str, text: str
) -> Optional[Dict[str, str]]:
    """Inflect a spelling variant's base form ("grey" for "gray").

    The variant shares the lemma's grammar -- "grey" is as gradable as
    "gray", "donut" as countable as "doughnut" -- so the same facts select
    the pattern.  Only irregular *spellings* are dropped: an irregular
    plural stored for the lemma ("people") is not the variant's, and
    applying it would give the variant the lemma's spelling.
    """
    if pos_type == "noun":
        (countability,) = read_facts(session, lemma.id, "en", "countability")
        return build_noun_forms(text, countability, None, None)
    if pos_type in ("adjective", "adverb"):
        (gradability,) = read_facts(session, lemma.id, "en", "gradability")
        builder: Callable[..., Optional[Dict[str, str]]] = (
            build_adjective_forms if pos_type == "adjective" else build_adverb_forms
        )
        return builder(text, gradability, None, None)
    return None
