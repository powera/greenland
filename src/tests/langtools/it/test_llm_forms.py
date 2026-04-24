import unittest
from types import SimpleNamespace
from typing import Any, Callable, cast
from unittest.mock import patch

from langtools.it.llm_forms import (
    query_italian_adjective_forms,
    query_italian_noun_forms,
    query_italian_verb_conjugations,
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

    def add(self, _obj: object) -> None:
        return None

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


class TestItalianMechanicalLlmForms(unittest.TestCase):
    def test_uses_mechanical_conjugation(self) -> None:
        lemma = SimpleNamespace(id=1, pos_type="verb", lemma_text="to speak")
        client = cast(Any, SimpleNamespace(default_model="fake-model"))

        with (
            patch("langtools.it.llm_forms.get_translation", return_value="parlare"),
            patch("langtools.it.llm_forms.get_grammar_fact_value", return_value=None),
            patch("langtools.it.llm_forms.query_forms") as mock_query_forms,
            patch("langtools.it.llm_forms.linguistic_db.log_query") as mock_log_query,
        ):
            get_session = cast(Callable[[], Any], lambda: _FakeSession(lemma))
            forms, ok = query_italian_verb_conjugations(client, 1, get_session)

        self.assertTrue(ok)
        self.assertEqual(forms["1s_present"], "parlo")
        self.assertEqual(forms["1s_future"], "parlerò")
        mock_query_forms.assert_not_called()
        mock_log_query.assert_called_once()

    def test_noun_uses_grammar_fact_plural(self) -> None:
        lemma = SimpleNamespace(id=2, pos_type="noun", lemma_text="arm")
        client = cast(Any, SimpleNamespace(default_model="fake-model"))

        with (
            patch("langtools.it.llm_forms.get_translation", return_value="braccio"),
            patch("langtools.it.llm_forms.get_grammar_fact_value", return_value="braccia"),
            patch("langtools.it.llm_forms.query_forms") as mock_query_forms,
        ):
            get_session = cast(Callable[[], Any], lambda: _FakeSession(lemma))
            forms, ok = query_italian_noun_forms(client, 2, get_session)

        self.assertTrue(ok)
        self.assertEqual(forms, {"singular": "braccio", "plural": "braccia"})
        mock_query_forms.assert_not_called()

    def test_adjective_mechanical_generation(self) -> None:
        lemma = SimpleNamespace(id=3, pos_type="adjective", lemma_text="Italian")
        client = cast(Any, SimpleNamespace(default_model="fake-model"))

        with (
            patch("langtools.it.llm_forms.get_translation", return_value="italiano"),
            patch("langtools.it.llm_forms.query_forms") as mock_query_forms,
        ):
            get_session = cast(Callable[[], Any], lambda: _FakeSession(lemma))
            forms, ok = query_italian_adjective_forms(client, 3, get_session)

        self.assertTrue(ok)
        self.assertEqual(forms["plural_f"], "italiane")
        mock_query_forms.assert_not_called()


if __name__ == "__main__":
    unittest.main()
