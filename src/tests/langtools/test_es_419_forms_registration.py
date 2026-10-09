"""es-419 is registered as a form-storing language of its own.

Latin American Spanish is a storage dialect: it keeps its own translations, so
it also keeps its own paradigm rows.  That only works if every layer between
the conjugator and the WireWord export knows the code -- the GrammaticalForm
enum, FORM_SPECS, the mechanical generator's slot map, and the export's key
conversion.  These check the chain rather than the linguistics, which live in
src/regtest/langtools/test_es_conjugation.py.
"""

from typing import Dict

import pytest

from exports.wireword.helpers import (
    convert_to_wireword_grammatical_form_key,
    extract_conjugation_slot,
    extract_conjugation_tense,
)
from langtools.form_registry import FORM_SPECS
from storage.models.enums import GrammaticalForm

PERSONS = ("1s", "2s", "3s", "1p", "2p", "3p")
TENSES = ("present", "past", "future")


def test_es_419_has_a_spec_for_every_part_of_speech() -> None:
    for pos_type in ("noun", "verb", "adjective"):
        assert ("es-419", pos_type) in FORM_SPECS, pos_type


def test_es_419_verb_slots_match_es() -> None:
    """The two varieties carry the same paradigm; only the text differs."""
    peninsular = FORM_SPECS[("es", "verb")]
    latin_american = FORM_SPECS[("es-419", "verb")]
    assert latin_american.form_fields == peninsular.form_fields
    # Plus the infinitive, gerund and past participle.
    assert len(latin_american.form_fields) == len(PERSONS) * len(TENSES) + 3


def test_es_419_enum_values_carry_the_dialect_code() -> None:
    """Rows are filtered by language, so the value must name es-419, not es."""
    mapping: Dict[str, GrammaticalForm] = FORM_SPECS[("es-419", "verb")].form_mapping
    for person in PERSONS:
        for tense in TENSES:
            form = mapping[f"{person}_{tense}"]
            assert form.value == f"verb/es-419_{person}_{tense}"
            # A dash is not valid in an identifier, so the member name uses _.
            assert form.name == f"VERB_ES_419_{person.upper()}_{tense.upper()}"


def test_es_419_enum_members_are_distinct_from_es() -> None:
    peninsular = FORM_SPECS[("es", "verb")].form_mapping
    latin_american = FORM_SPECS[("es-419", "verb")].form_mapping
    overlapping = {
        field for field in peninsular if peninsular[field].value == latin_american[field].value
    }
    assert not overlapping


def test_es_419_reuses_the_spanish_prompts() -> None:
    """There is no langtools/es-419/, so the LLM fallback reads es's prompts."""
    for pos_type in ("noun", "verb", "adjective"):
        assert FORM_SPECS[("es-419", pos_type)].prompt_path.startswith("es/")


def test_es_419_query_types_are_distinct_from_es() -> None:
    """Query logs have to tell the two varieties apart."""
    for pos_type in ("noun", "verb", "adjective"):
        peninsular = FORM_SPECS[("es", pos_type)]
        latin_american = FORM_SPECS[("es-419", pos_type)]
        assert latin_american.query_type != peninsular.query_type
        assert latin_american.schema_name != peninsular.schema_name


@pytest.mark.parametrize("language_code", ["es", "es-419"])
def test_verb_slots_survive_the_wireword_key_conversion(language_code: str) -> None:
    """Every stored slot has to reach the export's conjugation tables."""
    expected_tense = {"present": "pres", "past": "past", "future": "fut"}
    mapping = FORM_SPECS[(language_code, "verb")].form_mapping
    for person in PERSONS:
        for tense in TENSES:
            key = convert_to_wireword_grammatical_form_key(mapping[f"{person}_{tense}"].value)
            assert key == f"{person}_{tense}"
            assert extract_conjugation_slot(key) == person
            assert extract_conjugation_tense(key) == expected_tense[tense]


def test_mechanical_generator_covers_both_spanish_varieties() -> None:
    from words.mechanical_forms import (
        SUPPORTED,
        resolve_grammatical_form,
    )

    for language_code in ("es", "es-419"):
        assert "noun" in SUPPORTED[language_code]
        assert "verb" in SUPPORTED[language_code]
        assert "adjective" in SUPPORTED[language_code]
        for non_finite in ("infinitive", "gerund", "past_participle"):
            assert (
                resolve_grammatical_form(language_code, "verb", non_finite)
                == f"verb/{language_code}_{non_finite}"
            )
        assert (
            resolve_grammatical_form(language_code, "adjective", "singular_m_apocope")
            == f"adjective/{language_code}_singular_m_apocope"
        )
        assert (
            resolve_grammatical_form(language_code, "noun", "plural")
            == f"noun/{language_code}_plural"
        )
        assert (
            resolve_grammatical_form(language_code, "verb", "1s_present")
            == f"verb/{language_code}_1s_present"
        )
        # The builder emits registry slot names ("past" is the preterite).
        assert (
            resolve_grammatical_form(language_code, "verb", "3s_past")
            == f"verb/{language_code}_3s_past"
        )
        # Tenses with no registry slot are skipped, not approximated.
        assert resolve_grammatical_form(language_code, "verb", "1s_imperfect") is None
        assert (
            resolve_grammatical_form(language_code, "adjective", "singular_f")
            == f"adjective/{language_code}_singular_f"
        )


def test_es_419_shares_the_spanish_task_settings() -> None:
    from langtools.form_tasks import get_on_demand_pos_types, get_task_settings

    for pos_type in ("noun", "verb", "adjective"):
        assert get_task_settings("es-419", pos_type) == get_task_settings("es", pos_type)
    assert get_on_demand_pos_types()["es-419"] == ["noun", "verb", "adjective"]


def test_task_generators_exist() -> None:
    """Settings name generators by string, so nothing else catches a typo."""
    import importlib

    from langtools.form_tasks import _load

    settings, module_language = _load()
    for (language_code, pos_type), task_settings in settings.items():
        name = task_settings.get("generator")
        if not name:
            continue
        module = importlib.import_module(f"langtools.{module_language[language_code]}.llm_forms")
        assert callable(
            getattr(module, name, None)
        ), f"{language_code}/{pos_type} names a missing generator: {name}"


def test_es_419_generator_gets_its_language_code() -> None:
    from unittest.mock import patch

    from langtools.form_tasks import generate_forms

    with patch("langtools.es.llm_forms.get_noun_forms", return_value=({}, True)) as generator:
        generate_forms("es-419", "noun", object(), 7, lambda: None)  # type: ignore[arg-type,return-value]
    assert generator.call_args.kwargs == {"language_code": "es-419"}
