from types import SimpleNamespace
from typing import Any, Callable, cast
from unittest.mock import patch

from langtools.de.llm_forms import query_german_verb_conjugations
from langtools.es.llm_forms import query_spanish_verb_conjugations
from langtools.form_registry import FORM_SPECS
from langtools.it.llm_forms import query_italian_verb_conjugations


class _FakeQuery:
    def __init__(self, lemma: SimpleNamespace | None) -> None:
        self._lemma = lemma

    def filter(self, *_args: object, **_kwargs: object) -> "_FakeQuery":
        return self

    def first(self) -> SimpleNamespace | None:
        return self._lemma


class _FakeSession:
    def __init__(self, lemma: SimpleNamespace | None) -> None:
        self._lemma = lemma

    def query(self, _model: object) -> _FakeQuery:
        return _FakeQuery(self._lemma)


def _complete_overrides(language_code: str, value_prefix: str) -> dict[str, str]:
    return {
        form_key: f"{value_prefix}_{form_key}"
        for form_key in FORM_SPECS[(language_code, "verb")].form_mapping
    }


def test_spanish_regular_forms_apply_exact_overrides() -> None:
    lemma = SimpleNamespace(id=1, pos_type="verb", lemma_text="to speak")
    client = cast(Any, SimpleNamespace(default_model="fake-model"))

    with (
        patch("langtools.es.llm_forms.get_translation", return_value="hablar"),
        patch(
            "langtools.es.llm_forms.get_verb_form_overrides",
            return_value={"1s_present": "hablo-override"},
        ),
        patch("langtools.es.llm_forms.query_forms") as mock_query_forms,
        patch("langtools.es.llm_forms.linguistic_db.log_query"),
    ):
        get_session = cast(Callable[[], Any], lambda: _FakeSession(lemma))
        forms, ok = query_spanish_verb_conjugations(client, 1, get_session)

    assert ok
    assert forms["1s_present"] == "hablo-override"
    assert forms["2s_present"] == "hablas"
    mock_query_forms.assert_not_called()


def test_german_complete_overrides_bypass_llm_when_conjugator_falls_back() -> None:
    lemma = SimpleNamespace(id=2, pos_type="verb", lemma_text="to be")
    client = cast(Any, SimpleNamespace(default_model="fake-model"))
    overrides = _complete_overrides("de", "sein")

    with (
        patch("langtools.de.llm_forms.get_translation", return_value="sein"),
        patch("langtools.de.llm_forms.get_complete_verb_form_overrides", return_value=overrides),
        patch("langtools.de.llm_forms.query_forms") as mock_query_forms,
        patch("langtools.de.llm_forms.linguistic_db.log_query"),
    ):
        get_session = cast(Callable[[], Any], lambda: _FakeSession(lemma))
        forms, ok = query_german_verb_conjugations(client, 2, get_session)

    assert ok
    assert forms == overrides
    mock_query_forms.assert_not_called()


def test_italian_principal_parts_and_exact_overrides_coexist() -> None:
    lemma = SimpleNamespace(id=3, pos_type="verb", lemma_text="to eat")
    client = cast(Any, SimpleNamespace(default_model="fake-model"))

    with (
        patch("langtools.it.llm_forms.get_translation", return_value="mangiare"),
        patch(
            "langtools.it.llm_forms.get_grammar_fact_value",
            side_effect=lambda _session, _lemma_id, _language_code, fact_type: {
                "1s_present": "mangio",
                "1s_future": "mangerò",
            }.get(fact_type),
        ),
        patch(
            "langtools.it.llm_forms.get_verb_form_overrides",
            return_value={"3s_future": "mangerà-override"},
        ),
        patch("langtools.it.llm_forms.query_forms") as mock_query_forms,
        patch("langtools.it.llm_forms.linguistic_db.log_query"),
    ):
        get_session = cast(Callable[[], Any], lambda: _FakeSession(lemma))
        forms, ok = query_italian_verb_conjugations(client, 3, get_session)

    assert ok
    assert forms["1s_present"] == "mangio"
    assert forms["1s_future"] == "mangerò"
    assert forms["3s_future"] == "mangerà-override"
    mock_query_forms.assert_not_called()
