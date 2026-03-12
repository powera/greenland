import unittest
from types import SimpleNamespace
from typing import Any, Callable, cast
from unittest.mock import patch

from langtools.lt.llm_forms import _parse_principal_parts, query_lithuanian_verb_conjugations


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


class TestLithuanianMechanicalLlmForms(unittest.TestCase):
    def test_parses_principal_parts(self) -> None:
        self.assertEqual(
            _parse_principal_parts("dirbti, dirba, dirbo"), ("dirbti", "dirba", "dirbo")
        )
        self.assertEqual(
            _parse_principal_parts("dirbti (dirba, dirbo)"), ("dirbti", "dirba", "dirbo")
        )

    def test_uses_mechanical_conjugation(self) -> None:
        lemma = SimpleNamespace(id=1, pos_type="verb", lemma_text="to work", guid=None)
        client = cast(Any, SimpleNamespace(default_model="fake-model"))

        with (
            patch("langtools.lt.llm_forms.get_translation", return_value="dirbti, dirba, dirbo"),
            patch("langtools.lt.llm_forms.query_forms") as mock_query_forms,
            patch("langtools.lt.llm_forms.linguistic_db.log_query") as mock_log_query,
        ):
            get_session = cast(Callable[[], Any], lambda: _FakeSession(lemma))
            forms, ok = query_lithuanian_verb_conjugations(client, 1, get_session)

        self.assertTrue(ok)
        self.assertEqual(forms["1s_present"], "dirbu")
        self.assertEqual(forms["1s_future"], "dirbsiu")
        mock_query_forms.assert_not_called()
        mock_log_query.assert_called_once()
