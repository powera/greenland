"""Tests for the English llm_forms mechanical-inflection shortcut."""

import unittest
from types import SimpleNamespace
from typing import Any, Callable, Dict, Optional, cast
from unittest.mock import patch

from langtools.en.llm_forms import (
    query_english_adjective_forms,
    query_english_adverb_forms,
    query_english_noun_forms,
)


class _FakeQuery:
    def __init__(self, row: Optional[SimpleNamespace]) -> None:
        self._row = row

    def filter(self, *_args: object, **_kwargs: object) -> "_FakeQuery":
        return self

    def first(self) -> Optional[SimpleNamespace]:
        return self._row


class _FakeFactQuery:
    """Stands in for a GrammarFact query, resolving by fact_type.

    ``get_grammar_fact_value`` chains ``.filter()`` calls whose criteria this
    stub cannot inspect, so the fact type is instead recovered from the
    right-hand value of each equality criterion.
    """

    def __init__(self, facts: Dict[str, str]) -> None:
        self._facts = facts
        self._fact_type: Optional[str] = None

    def filter(self, *args: object, **_kwargs: object) -> "_FakeFactQuery":
        for criterion in args:
            right = getattr(criterion, "right", None)
            value = getattr(right, "value", None)
            if isinstance(value, str) and value in self._facts:
                self._fact_type = value
        return self

    def first(self) -> Optional[SimpleNamespace]:
        if self._fact_type is None:
            return None
        return SimpleNamespace(fact_value=self._facts[self._fact_type])


class _FakeSession:
    """Session stub returning a lemma for Lemma queries, facts otherwise.

    The English builders look up several per-lemma grammar facts before
    inflecting, so the stub distinguishes the two queries by model.
    """

    def __init__(
        self, lemma: Optional[SimpleNamespace], facts: Optional[Dict[str, str]] = None
    ) -> None:
        self._lemma = lemma
        self._facts = facts or {}

    def query(self, model: object) -> Any:
        if getattr(model, "__name__", "") == "GrammarFact":
            return _FakeFactQuery(self._facts)
        return _FakeQuery(self._lemma)


def _session_for(
    lemma: Optional[SimpleNamespace], facts: Optional[Dict[str, str]] = None
) -> Callable[[], Any]:
    return cast(Callable[[], Any], lambda: _FakeSession(lemma, facts))


_CLIENT = cast(Any, SimpleNamespace(default_model="fake-model"))


class TestEnglishNounLlmForms(unittest.TestCase):
    def test_uses_mechanical_pluralization_before_llm(self) -> None:
        lemma = SimpleNamespace(id=1, pos_type="noun", lemma_text="book")

        with (
            patch("langtools.en.llm_forms.query_forms") as mock_query_forms,
            patch("langtools.en.llm_forms.linguistic_db.log_query") as mock_log_query,
        ):
            forms, ok = query_english_noun_forms(_CLIENT, 1, _session_for(lemma))

        self.assertTrue(ok)
        self.assertEqual(forms, {"singular": "book", "plural": "books"})
        mock_query_forms.assert_not_called()
        mock_log_query.assert_called_once()
        self.assertIn("mechanical", mock_log_query.call_args.kwargs["prompt"])

    def test_stored_plural_fact_is_used(self) -> None:
        lemma = SimpleNamespace(id=1, pos_type="noun", lemma_text="child")

        with (
            patch("langtools.en.llm_forms.query_forms") as mock_query_forms,
            patch("langtools.en.llm_forms.linguistic_db.log_query"),
        ):
            forms, ok = query_english_noun_forms(
                _CLIENT, 1, _session_for(lemma, {"plural": "children"})
            )

        self.assertTrue(ok)
        self.assertEqual(forms, {"singular": "child", "plural": "children"})
        mock_query_forms.assert_not_called()

    def test_uncountable_number_type_stores_singular_only(self) -> None:
        lemma = SimpleNamespace(id=1, pos_type="noun", lemma_text="information")

        with (
            patch("langtools.en.llm_forms.query_forms") as mock_query_forms,
            patch("langtools.en.llm_forms.linguistic_db.log_query"),
        ):
            forms, ok = query_english_noun_forms(
                _CLIENT, 1, _session_for(lemma, {"number_type": "uncountable"})
            )

        self.assertTrue(ok)
        self.assertEqual(forms, {"singular": "information"})
        mock_query_forms.assert_not_called()

    def test_plurale_tantum_repeats_the_lemma(self) -> None:
        lemma = SimpleNamespace(id=1, pos_type="noun", lemma_text="scissors")

        with (
            patch("langtools.en.llm_forms.query_forms") as mock_query_forms,
            patch("langtools.en.llm_forms.linguistic_db.log_query"),
        ):
            forms, ok = query_english_noun_forms(
                _CLIENT, 1, _session_for(lemma, {"number_type": "plurale_tantum"})
            )

        self.assertTrue(ok)
        self.assertEqual(forms, {"singular": "scissors", "plural": "scissors"})
        mock_query_forms.assert_not_called()

    def test_countability_separates_the_senses_of_iron(self) -> None:
        """ "iron" is uncountable as a metal but countable as an appliance."""
        lemma = SimpleNamespace(id=1, pos_type="noun", lemma_text="iron")

        with (
            patch("langtools.en.llm_forms.query_forms"),
            patch("langtools.en.llm_forms.linguistic_db.log_query"),
        ):
            appliance, _ = query_english_noun_forms(
                _CLIENT, 1, _session_for(lemma, {"countability": "countable"})
            )
            metal, _ = query_english_noun_forms(
                _CLIENT, 1, _session_for(lemma, {"countability": "uncountable"})
            )

        self.assertEqual(appliance, {"singular": "iron", "plural": "irons"})
        self.assertEqual(metal, {"singular": "iron"})

    def test_falls_back_to_llm_when_rules_decline(self) -> None:
        lemma = SimpleNamespace(id=1, pos_type="noun", lemma_text="air conditioner")

        with patch(
            "langtools.en.llm_forms.query_forms",
            return_value=({"singular": "air conditioner"}, True),
        ) as mock_query_forms:
            forms, ok = query_english_noun_forms(_CLIENT, 1, _session_for(lemma))

        self.assertTrue(ok)
        self.assertEqual(forms, {"singular": "air conditioner"})
        mock_query_forms.assert_called_once()

    def test_falls_back_to_llm_for_ambiguous_ending_without_facts(self) -> None:
        """ "cactus" now needs a stored plural; the LLM handles it meanwhile."""
        lemma = SimpleNamespace(id=1, pos_type="noun", lemma_text="cactus")

        with patch(
            "langtools.en.llm_forms.query_forms", return_value=({"singular": "cactus"}, True)
        ) as mock_query_forms:
            _, ok = query_english_noun_forms(_CLIENT, 1, _session_for(lemma))

        self.assertTrue(ok)
        mock_query_forms.assert_called_once()

    def test_missing_lemma_falls_back_to_llm(self) -> None:
        with patch(
            "langtools.en.llm_forms.query_forms", return_value=({}, False)
        ) as mock_query_forms:
            forms, ok = query_english_noun_forms(_CLIENT, 1, _session_for(None))

        self.assertFalse(ok)
        self.assertEqual(forms, {})
        mock_query_forms.assert_called_once()


class TestEnglishAdjectiveLlmForms(unittest.TestCase):
    def test_uses_mechanical_comparison_before_llm(self) -> None:
        lemma = SimpleNamespace(id=1, pos_type="adjective", lemma_text="good")

        with (
            patch("langtools.en.llm_forms.query_forms") as mock_query_forms,
            patch("langtools.en.llm_forms.linguistic_db.log_query") as mock_log_query,
        ):
            forms, ok = query_english_adjective_forms(_CLIENT, 1, _session_for(lemma))

        self.assertTrue(ok)
        self.assertEqual(
            forms, {"positive": "good", "comparative": "better", "superlative": "best"}
        )
        mock_query_forms.assert_not_called()
        mock_log_query.assert_called_once()

    def test_non_gradable_fact_stores_positive_only(self) -> None:
        lemma = SimpleNamespace(id=1, pos_type="adjective", lemma_text="dead")

        with (
            patch("langtools.en.llm_forms.query_forms") as mock_query_forms,
            patch("langtools.en.llm_forms.linguistic_db.log_query"),
        ):
            forms, ok = query_english_adjective_forms(
                _CLIENT, 1, _session_for(lemma, {"gradability": "non_gradable"})
            )

        self.assertTrue(ok)
        self.assertEqual(forms, {"positive": "dead"})
        mock_query_forms.assert_not_called()

    def test_periphrastic_fact_forces_more_most(self) -> None:
        lemma = SimpleNamespace(id=1, pos_type="adjective", lemma_text="glad")

        with (
            patch("langtools.en.llm_forms.query_forms") as mock_query_forms,
            patch("langtools.en.llm_forms.linguistic_db.log_query"),
        ):
            forms, ok = query_english_adjective_forms(
                _CLIENT, 1, _session_for(lemma, {"gradability": "periphrastic"})
            )

        self.assertTrue(ok)
        self.assertEqual(forms["comparative"], "more glad")
        mock_query_forms.assert_not_called()

    def test_stored_comparison_forms_are_used(self) -> None:
        lemma = SimpleNamespace(id=1, pos_type="adjective", lemma_text="far")

        with (
            patch("langtools.en.llm_forms.query_forms") as mock_query_forms,
            patch("langtools.en.llm_forms.linguistic_db.log_query"),
        ):
            forms, ok = query_english_adjective_forms(
                _CLIENT,
                1,
                _session_for(lemma, {"comparative": "further", "superlative": "furthest"}),
            )

        self.assertTrue(ok)
        self.assertEqual(
            forms, {"positive": "far", "comparative": "further", "superlative": "furthest"}
        )
        mock_query_forms.assert_not_called()

    def test_falls_back_to_llm_for_ambiguous_disyllable(self) -> None:
        lemma = SimpleNamespace(id=1, pos_type="adjective", lemma_text="common")

        with patch(
            "langtools.en.llm_forms.query_forms", return_value=({"positive": "common"}, True)
        ) as mock_query_forms:
            _, ok = query_english_adjective_forms(_CLIENT, 1, _session_for(lemma))

        self.assertTrue(ok)
        mock_query_forms.assert_called_once()


class TestEnglishAdverbLlmForms(unittest.TestCase):
    def test_uses_mechanical_comparison_before_llm(self) -> None:
        lemma = SimpleNamespace(id=1, pos_type="adverb", lemma_text="quickly")

        with (
            patch("langtools.en.llm_forms.query_forms") as mock_query_forms,
            patch("langtools.en.llm_forms.linguistic_db.log_query") as mock_log_query,
        ):
            forms, ok = query_english_adverb_forms(_CLIENT, 1, _session_for(lemma))

        self.assertTrue(ok)
        self.assertEqual(forms["comparative"], "more quickly")
        mock_query_forms.assert_not_called()
        mock_log_query.assert_called_once()

    def test_non_gradable_fact_stores_positive_only(self) -> None:
        lemma = SimpleNamespace(id=1, pos_type="adverb", lemma_text="never")

        with (
            patch("langtools.en.llm_forms.query_forms") as mock_query_forms,
            patch("langtools.en.llm_forms.linguistic_db.log_query"),
        ):
            forms, ok = query_english_adverb_forms(
                _CLIENT, 1, _session_for(lemma, {"gradability": "non_gradable"})
            )

        self.assertTrue(ok)
        self.assertEqual(forms, {"positive": "never"})
        mock_query_forms.assert_not_called()

    def test_synthetic_fact_covers_flat_adverbs(self) -> None:
        lemma = SimpleNamespace(id=1, pos_type="adverb", lemma_text="fast")

        with (
            patch("langtools.en.llm_forms.query_forms") as mock_query_forms,
            patch("langtools.en.llm_forms.linguistic_db.log_query"),
        ):
            forms, ok = query_english_adverb_forms(
                _CLIENT, 1, _session_for(lemma, {"gradability": "synthetic"})
            )

        self.assertTrue(ok)
        self.assertEqual(forms["comparative"], "faster")
        mock_query_forms.assert_not_called()

    def test_falls_back_to_llm_for_unlisted_adverb(self) -> None:
        lemma = SimpleNamespace(id=1, pos_type="adverb", lemma_text="often")

        with patch(
            "langtools.en.llm_forms.query_forms", return_value=({"positive": "often"}, True)
        ) as mock_query_forms:
            _, ok = query_english_adverb_forms(_CLIENT, 1, _session_for(lemma))

        self.assertTrue(ok)
        mock_query_forms.assert_called_once()

    def test_falls_back_to_llm_for_flat_adverb_without_a_fact(self) -> None:
        lemma = SimpleNamespace(id=1, pos_type="adverb", lemma_text="fast")

        with patch(
            "langtools.en.llm_forms.query_forms", return_value=({"positive": "fast"}, True)
        ) as mock_query_forms:
            _, ok = query_english_adverb_forms(_CLIENT, 1, _session_for(lemma))

        self.assertTrue(ok)
        mock_query_forms.assert_called_once()


if __name__ == "__main__":
    unittest.main()
