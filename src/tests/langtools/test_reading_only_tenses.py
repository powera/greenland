"""Rule-built tenses stored for reading, outside the LLM schema and WireWord.

Spanish keeps its imperfect, conditional, present subjunctive and imperative;
French its conditional, present subjunctive, passé simple and imperative.  They
are listed under ``mechanical_forms`` in each forms_config.
"""

from typing import Dict

import pytest

from langtools.es.mechanical import project_verb_forms
from langtools.es.conjugation import conjugate_for_dialect
from langtools.form_patterns import expand_fields, expand_stored_fields, mechanical_only_fields
from langtools.form_registry import FORM_SPECS, is_mechanical_only_form
from langtools.fr.conjugation import conjugate
from langtools.fr.forms_config import VERB_CONFIG as FR_VERB_CONFIG
from langtools.es.forms_config import VERB_CONFIG as ES_VERB_CONFIG
from storage.models.enums import GrammaticalForm


def _values() -> set[str]:
    return {member.value for member in GrammaticalForm}


@pytest.mark.parametrize("language_code", ["es", "es-419"])
def test_spanish_reading_slots_are_registered_but_not_asked_of_the_llm(
    language_code: str,
) -> None:
    for slot in ("1s_imperfect", "3p_conditional", "2s_subjunctive_present", "2p_imperative"):
        value = f"verb/{language_code}_{slot}"
        assert value in _values()
        assert is_mechanical_only_form(language_code, value)
        assert slot not in FORM_SPECS[(language_code, "verb")].form_fields
    # Quiz slots stay quiz slots.
    assert not is_mechanical_only_form(language_code, f"verb/{language_code}_1s_present")
    assert "1s_present" in FORM_SPECS[(language_code, "verb")].form_fields


def test_french_reading_slots_are_registered_but_not_asked_of_the_llm() -> None:
    for slot in ("1s_cond", "3s_subj", "3p_ps", "2s_imp"):
        assert f"verb/fr_{slot}" in _values()
        assert is_mechanical_only_form("fr", f"verb/fr_{slot}")
        assert slot not in FORM_SPECS[("fr", "verb")].form_fields
    assert not is_mechanical_only_form("fr", "verb/fr_1s_present")


def test_stored_fields_extend_the_llm_fields_without_repeats() -> None:
    for config in (ES_VERB_CONFIG, FR_VERB_CONFIG):
        stored = expand_stored_fields(config)
        assert stored[: len(expand_fields(config))] == expand_fields(config)
        assert len(stored) == len(set(stored))
        assert set(mechanical_only_fields(config)).isdisjoint(expand_fields(config))
    assert len(mechanical_only_fields(ES_VERB_CONFIG)) == 6 * 3 + 5
    assert len(mechanical_only_fields(FR_VERB_CONFIG)) == 6 * 3 + 3


def test_spanish_projection_keeps_the_reading_tenses() -> None:
    conjugated = conjugate_for_dialect("hablar", "es")
    assert conjugated is not None
    projected = project_verb_forms(conjugated)
    assert projected["3s_past"] == "habló"
    assert projected["1s_imperfect"] == "hablaba"
    assert projected["1p_conditional"] == "hablaríamos"
    assert projected["3s_subjunctive_present"] == "hable"
    assert projected["2s_imperative"] == "habla"
    assert "1s_imperative" not in projected
    assert "1s_preterite" not in projected  # stored as 1s_past


def _moods(verb: str) -> Dict[str, str]:
    forms = conjugate(verb)
    assert forms is not None
    return forms


@pytest.mark.parametrize(
    "verb, expected",
    [
        (
            "parler",
            {"1s_cond": "parlerais", "3s_subj": "parle", "3p_ps": "parlèrent", "2s_imp": "parle"},
        ),
        ("manger", {"1s_ps": "mangeai", "1p_ps": "mangeâmes", "3p_ps": "mangèrent"}),
        ("commencer", {"3s_ps": "commença", "3p_ps": "commencèrent"}),
        ("finir", {"1p_subj": "finissions", "3s_ps": "finit", "2s_imp": "finis"}),
        ("vendre", {"1s_subj": "vende", "1p_ps": "vendîmes"}),
        ("être", {"1s_subj": "sois", "3s_ps": "fut", "1s_cond": "serais", "2p_imp": "soyez"}),
        ("avoir", {"3s_subj": "ait", "3p_ps": "eurent", "2s_imp": "aie"}),
        ("aller", {"1s_subj": "aille", "1p_subj": "allions", "3s_ps": "alla", "2s_imp": "va"}),
        ("faire", {"1p_subj": "fassions", "3p_ps": "firent", "2p_imp": "faites"}),
        ("refaire", {"1s_subj": "refasse", "1s_ps": "refis"}),
        ("venir", {"1s_subj": "vienne", "1p_subj": "venions", "3s_ps": "vint", "1p_ps": "vînmes"}),
        ("comprendre", {"3s_subj": "comprenne", "3s_ps": "comprit"}),
        ("savoir", {"2s_imp": "sache", "1s_ps": "sus"}),
        ("ouvrir", {"2s_imp": "ouvre", "3s_ps": "ouvrit"}),
    ],
)
def test_french_derived_moods(verb: str, expected: Dict[str, str]) -> None:
    forms = _moods(verb)
    for slot, text in expected.items():
        assert forms[slot] == text, slot


@pytest.mark.parametrize(
    "verb, present_1s, pc_m, ps_3s",
    [
        ("concevoir", "conçois", "conçu", "conçut"),
        ("apercevoir", "aperçois", "aperçu", "aperçut"),
        ("décevoir", "déçois", "déçu", "déçut"),
        ("percevoir", "perçois", "perçu", "perçut"),
    ],
)
def test_cevoir_verbs_drop_the_re_of_recevoir(
    verb: str, present_1s: str, pc_m: str, ps_3s: str
) -> None:
    forms = _moods(verb)
    assert forms["1s_present"] == present_1s
    assert forms["pc_m"] == pc_m
    assert forms["3s_ps"] == ps_3s
    assert forms["1s_future"] == verb[:-3] + "rai"


def test_reflexive_imperative_puts_the_pronoun_after_the_verb() -> None:
    forms = _moods("se lever")
    assert forms["2s_imp"] == "lève-toi"
    assert forms["1p_imp"] == "levons-nous"
    assert forms["2p_imp"] == "levez-vous"
    assert forms["1s_cond"] == "me lèverais"
    assert forms["3s_ps"] == "se leva"
