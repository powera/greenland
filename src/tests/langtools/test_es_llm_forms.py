"""Tests for Spanish llm_forms mechanical conjugation shortcut."""

import unittest
from types import SimpleNamespace
from typing import Any, Callable, cast
from unittest.mock import patch

from langtools.es.llm_forms import (
    _project_spanish_forms_to_registry,
    query_spanish_verb_conjugations,
)


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


class TestSpanishVerbLlmForms(unittest.TestCase):
    def test_projects_preterite_as_past(self) -> None:
        projected = _project_spanish_forms_to_registry(
            {
                "1s_present": "hablo",
                "1s_preterite": "hablé",
                "1s_future": "hablaré",
            }
        )
        self.assertEqual(projected["1s_present"], "hablo")
        self.assertEqual(projected["1s_past"], "hablé")
        self.assertEqual(projected["1s_future"], "hablaré")

    def test_uses_mechanical_conjugation_before_llm(self) -> None:
        lemma = SimpleNamespace(id=1, pos_type="verb", lemma_text="to speak")
        client = cast(Any, SimpleNamespace(default_model="fake-model"))

        with (
            patch("langtools.es.llm_forms.get_translation", return_value="hablar"),
            patch(
                "langtools.es.llm_forms.conjugate",
                return_value={
                    "1s_present": "hablo",
                    "1s_preterite": "hablé",
                    "1s_future": "hablaré",
                },
            ),
            patch("langtools.es.llm_forms.query_forms") as mock_query_forms,
            patch("langtools.es.llm_forms.linguistic_db.log_query") as mock_log_query,
        ):
            get_session = cast(Callable[[], Any], lambda: _FakeSession(lemma))
            forms, ok = query_spanish_verb_conjugations(client, 1, get_session)

        self.assertTrue(ok)
        self.assertEqual(forms["1s_present"], "hablo")
        self.assertEqual(forms["1s_past"], "hablé")
        self.assertEqual(forms["1s_future"], "hablaré")
        mock_query_forms.assert_not_called()
        mock_log_query.assert_called_once()

    def test_falls_back_to_llm_when_mechanical_fails(self) -> None:
        lemma = SimpleNamespace(id=1, pos_type="verb", lemma_text="to xyz")
        client = cast(Any, SimpleNamespace(default_model="fake-model"))

        with (
            patch("langtools.es.llm_forms.get_translation", return_value="xyz"),
            patch("langtools.es.llm_forms.conjugate", return_value=None),
            patch(
                "langtools.es.llm_forms.query_forms", return_value=({"1s_present": "xyz"}, True)
            ) as mock_query_forms,
        ):
            get_session = cast(Callable[[], Any], lambda: _FakeSession(lemma))
            forms, ok = query_spanish_verb_conjugations(client, 1, get_session)

        self.assertTrue(ok)
        self.assertEqual(forms, {"1s_present": "xyz"})
        mock_query_forms.assert_called_once()


if __name__ == "__main__":
    unittest.main()
