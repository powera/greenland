"""Tests for French llm_forms mechanical conjugation shortcut."""

import unittest
from types import SimpleNamespace
from typing import Any, Callable, cast
from unittest.mock import patch

from langtools.fr.llm_forms import query_french_verb_conjugations


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


class TestFrenchVerbLlmForms(unittest.TestCase):
    def test_uses_mechanical_conjugation_before_llm(self) -> None:
        lemma = SimpleNamespace(id=1, pos_type="verb", lemma_text="to speak")
        client = cast(Any, SimpleNamespace(default_model="fake-model"))

        with (
            patch("langtools.fr.llm_forms.get_translation", return_value="parler"),
            patch(
                "langtools.fr.llm_forms.conjugate",
                return_value=(
                    SimpleNamespace(
                        forms={"1s_present": "parle"}, confidence=1.0, notes="regular -er"
                    ),
                    True,
                ),
            ),
            patch("langtools.fr.llm_forms.query_forms") as mock_query_forms,
            patch("langtools.fr.llm_forms.linguistic_db.log_query") as mock_log_query,
        ):
            get_session = cast(Callable[[], Any], lambda: _FakeSession(lemma))
            forms, ok = query_french_verb_conjugations(client, 1, get_session)

        self.assertTrue(ok)
        self.assertEqual(forms, {"1s_present": "parle"})
        mock_query_forms.assert_not_called()
        mock_log_query.assert_called_once()

    def test_falls_back_to_llm_when_mechanical_fails(self) -> None:
        lemma = SimpleNamespace(id=1, pos_type="verb", lemma_text="to xyz")
        client = cast(Any, SimpleNamespace(default_model="fake-model"))

        with (
            patch("langtools.fr.llm_forms.get_translation", return_value="xyz"),
            patch(
                "langtools.fr.llm_forms.conjugate",
                return_value=(SimpleNamespace(forms={}, confidence=0.0, notes=""), False),
            ),
            patch(
                "langtools.fr.llm_forms.query_forms", return_value=({"1s_present": "xyz"}, True)
            ) as mock_query_forms,
        ):
            get_session = cast(Callable[[], Any], lambda: _FakeSession(lemma))
            forms, ok = query_french_verb_conjugations(client, 1, get_session)

        self.assertTrue(ok)
        self.assertEqual(forms, {"1s_present": "xyz"})
        mock_query_forms.assert_called_once()


if __name__ == "__main__":
    unittest.main()
