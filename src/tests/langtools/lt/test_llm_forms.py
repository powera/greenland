import unittest
from types import SimpleNamespace
from typing import Any, Callable, cast
from unittest.mock import patch

from langtools.lt.llm_forms import (
    _parse_principal_parts,
    query_lithuanian_noun_declensions,
    query_lithuanian_verb_conjugations,
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


class TestLithuanianMechanicalLlmForms(unittest.TestCase):
    def test_parses_principal_parts(self) -> None:
        self.assertEqual(
            _parse_principal_parts("dirbti, dirba, dirbo"), ("dirbti", "dirba", "dirbo")
        )
        self.assertEqual(
            _parse_principal_parts("dirbti (dirba, dirbo)"), ("dirbti", "dirba", "dirbo")
        )

    def test_uses_mechanical_noun_declension(self) -> None:
        lemma = SimpleNamespace(id=2, pos_type="noun", lemma_text="wolf", guid=None)
        client = cast(Any, SimpleNamespace(default_model="fake-model"))

        with (
            patch("langtools.lt.llm_forms.get_translation", return_value="vilkas"),
            patch("langtools.lt.llm_forms.get_grammatical_gender", return_value=None),
            patch("langtools.lt.llm_forms.query_forms") as mock_query_forms,
            patch("langtools.lt.llm_forms.linguistic_db.log_query") as mock_log_query,
            patch("langtools.lt.llm_forms.linguistic_db.add_grammar_fact") as mock_add_fact,
        ):
            get_session = cast(Callable[[], Any], lambda: _FakeSession(lemma))
            forms, ok = query_lithuanian_noun_declensions(client, 2, get_session)

        self.assertTrue(ok)
        self.assertEqual(forms["genitive_singular"], "vilko")
        self.assertEqual(forms["nominative_plural"], "vilkai")
        mock_query_forms.assert_not_called()
        mock_log_query.assert_called_once()
        self.assertGreaterEqual(mock_add_fact.call_count, 1)

    def test_uses_gender_fact_for_ambiguous_is(self) -> None:
        lemma = SimpleNamespace(id=3, pos_type="noun", lemma_text="castle", guid=None)
        client = cast(Any, SimpleNamespace(default_model="fake-model"))

        with (
            patch("langtools.lt.llm_forms.get_translation", return_value="pilis"),
            patch("langtools.lt.llm_forms.get_grammatical_gender", return_value="feminine"),
            patch("langtools.lt.llm_forms.query_forms") as mock_query_forms,
            patch("langtools.lt.llm_forms.linguistic_db.log_query"),
            patch("langtools.lt.llm_forms.linguistic_db.add_grammar_fact"),
        ):
            get_session = cast(Callable[[], Any], lambda: _FakeSession(lemma))
            forms, ok = query_lithuanian_noun_declensions(client, 3, get_session)

        self.assertTrue(ok)
        self.assertEqual(forms["genitive_singular"], "pilies")
        mock_query_forms.assert_not_called()

    def test_falls_back_for_ambiguous_is_without_gender_fact(self) -> None:
        lemma = SimpleNamespace(id=4, pos_type="noun", lemma_text="castle", guid=None)
        client = cast(Any, SimpleNamespace(default_model="fake-model"))

        with (
            patch("langtools.lt.llm_forms.get_translation", return_value="pilis"),
            patch("langtools.lt.llm_forms.get_grammatical_gender", return_value=None),
            patch(
                "langtools.lt.llm_forms.query_forms",
                return_value=({"nominative_singular": "pilis"}, True),
            ) as mock_query_forms,
            patch("langtools.lt.llm_forms.linguistic_db.log_query") as mock_log_query,
            patch("langtools.lt.llm_forms.linguistic_db.add_grammar_fact"),
        ):
            get_session = cast(Callable[[], Any], lambda: _FakeSession(lemma))
            _forms, ok = query_lithuanian_noun_declensions(client, 4, get_session)

        self.assertTrue(ok)
        mock_query_forms.assert_called_once()
        mock_log_query.assert_not_called()

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

    def test_db_principal_parts_with_legacy_translation(self) -> None:
        """When DB grammar facts exist but translation is in legacy format,
        the infinitive should be extracted cleanly (not the whole string)."""
        lemma = SimpleNamespace(id=1, pos_type="verb", lemma_text="to work", guid="V02_001")
        client = cast(Any, SimpleNamespace(default_model="fake-model"))

        with (
            patch(
                "langtools.lt.llm_forms.get_translation",
                return_value="dirbti, dirba, dirbo",
            ),
            patch(
                "langtools.lt.llm_forms.get_principal_parts",
                return_value=("dirba", "dirbo"),
            ),
            patch("langtools.lt.llm_forms.query_forms") as mock_query_forms,
            patch("langtools.lt.llm_forms.linguistic_db.log_query"),
        ):
            get_session = cast(Callable[[], Any], lambda: _FakeSession(lemma))
            forms, ok = query_lithuanian_verb_conjugations(client, 1, get_session)

        self.assertTrue(ok)
        # The infinitive should be "dirbti", not "dirbti, dirba, dirbo"
        self.assertEqual(forms["1s_future"], "dirbsiu")
        self.assertEqual(forms["1s_present"], "dirbu")
        mock_query_forms.assert_not_called()

    def test_db_principal_parts_with_clean_translation(self) -> None:
        """When DB grammar facts exist and translation is just the infinitive."""
        lemma = SimpleNamespace(id=1, pos_type="verb", lemma_text="to work", guid="V02_001")
        client = cast(Any, SimpleNamespace(default_model="fake-model"))

        with (
            patch("langtools.lt.llm_forms.get_translation", return_value="dirbti"),
            patch(
                "langtools.lt.llm_forms.get_principal_parts",
                return_value=("dirba", "dirbo"),
            ),
            patch("langtools.lt.llm_forms.query_forms") as mock_query_forms,
            patch("langtools.lt.llm_forms.linguistic_db.log_query"),
        ):
            get_session = cast(Callable[[], Any], lambda: _FakeSession(lemma))
            forms, ok = query_lithuanian_verb_conjugations(client, 1, get_session)

        self.assertTrue(ok)
        self.assertEqual(forms["1s_future"], "dirbsiu")
        self.assertEqual(forms["1s_present"], "dirbu")
        mock_query_forms.assert_not_called()
