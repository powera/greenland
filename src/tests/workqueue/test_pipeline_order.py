#!/usr/bin/env python3
"""Tests for workqueue.pipeline_order module.

Tests the canonical pipeline ordering for Barsukas agents, ensuring tasks
execute in the correct dependency order.
"""

import unittest

from workqueue.pipeline_order import (
    TASK_PIPELINE_ORDER,
    get_pipeline_step,
    has_earlier_step,
)


class TestGetPipelineStep(unittest.TestCase):
    """Test get_pipeline_step returns correct step numbers."""

    def test_known_task_types(self) -> None:
        """Each known task type returns its defined step number."""
        self.assertEqual(get_pipeline_step("add_missing_translations"), 2)
        self.assertEqual(get_pipeline_step("generate_forms"), 3)
        self.assertEqual(get_pipeline_step("generate_pronunciations"), 4)
        self.assertEqual(get_pipeline_step("generate_synonyms"), 5)
        self.assertEqual(get_pipeline_step("generate_grammar_fact"), 6)
        self.assertEqual(get_pipeline_step("translate_sentence"), 8)
        self.assertEqual(get_pipeline_step("generate_audio"), 9)

    def test_unknown_task_type_returns_none(self) -> None:
        """Unknown task types return None (no pipeline constraint)."""
        self.assertIsNone(get_pipeline_step("unknown_task"))
        self.assertIsNone(get_pipeline_step(""))
        self.assertIsNone(get_pipeline_step("generate_sentence_audio"))

    def test_all_pipeline_entries_have_positive_steps(self) -> None:
        """All entries in TASK_PIPELINE_ORDER have positive step numbers."""
        for task_type, step in TASK_PIPELINE_ORDER.items():
            with self.subTest(task_type=task_type):
                self.assertGreater(step, 0)


class TestHasEarlierStep(unittest.TestCase):
    """Test has_earlier_step ordering comparisons."""

    def test_translations_before_forms(self) -> None:
        self.assertTrue(has_earlier_step("add_missing_translations", "generate_forms"))

    def test_translations_before_pronunciations(self) -> None:
        self.assertTrue(has_earlier_step("add_missing_translations", "generate_pronunciations"))

    def test_forms_before_pronunciations(self) -> None:
        self.assertTrue(has_earlier_step("generate_forms", "generate_pronunciations"))

    def test_pronunciations_before_synonyms(self) -> None:
        self.assertTrue(has_earlier_step("generate_pronunciations", "generate_synonyms"))

    def test_grammar_facts_before_audio(self) -> None:
        self.assertTrue(has_earlier_step("generate_grammar_fact", "generate_audio"))

    def test_translate_sentence_before_audio(self) -> None:
        self.assertTrue(has_earlier_step("translate_sentence", "generate_audio"))

    def test_later_task_not_earlier(self) -> None:
        """A later task should not be considered earlier than a preceding one."""
        self.assertFalse(has_earlier_step("generate_audio", "add_missing_translations"))
        self.assertFalse(has_earlier_step("generate_pronunciations", "generate_forms"))

    def test_same_task_not_earlier(self) -> None:
        """A task is not earlier than itself."""
        self.assertFalse(has_earlier_step("generate_forms", "generate_forms"))

    def test_unknown_task_returns_false(self) -> None:
        """If either task is not in pipeline, returns False."""
        self.assertFalse(has_earlier_step("unknown_task", "generate_forms"))
        self.assertFalse(has_earlier_step("generate_forms", "unknown_task"))
        self.assertFalse(has_earlier_step("unknown_a", "unknown_b"))

    def test_full_pipeline_ordering(self) -> None:
        """Tasks in pipeline should satisfy total ordering."""
        ordered_types = sorted(TASK_PIPELINE_ORDER.keys(), key=lambda t: TASK_PIPELINE_ORDER[t])
        for i in range(len(ordered_types)):
            for j in range(i + 1, len(ordered_types)):
                earlier = ordered_types[i]
                later = ordered_types[j]
                with self.subTest(earlier=earlier, later=later):
                    self.assertTrue(has_earlier_step(earlier, later))
                    self.assertFalse(has_earlier_step(later, earlier))


if __name__ == "__main__":
    unittest.main()
