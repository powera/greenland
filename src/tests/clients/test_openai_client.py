#!/usr/bin/python3
"""Unit tests for OpenAI client helpers."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from clients.openai.client import is_gpt5_nano_or_mini_model, reasoning_effort_for_model


class ReasoningEffortTestCase(unittest.TestCase):
    """Tests for reasoning_effort_for_model."""

    def test_gpt5_standard_passes_through(self) -> None:
        """gpt-5 (non-5.4) should pass 'minimal' unchanged."""
        self.assertEqual(reasoning_effort_for_model("gpt-5-mini", "minimal"), "minimal")

    def test_gpt54_mini_maps_minimal_to_low(self) -> None:
        """gpt-5.4-mini does not support 'minimal'; should map to 'low'."""
        self.assertEqual(reasoning_effort_for_model("gpt-5.4-mini", "minimal"), "low")

    def test_gpt54_nano_maps_minimal_to_low(self) -> None:
        """gpt-5.4-nano does not support 'minimal'; should map to 'low'."""
        self.assertEqual(reasoning_effort_for_model("gpt-5.4-nano", "minimal"), "low")

    def test_gpt54_passes_non_minimal_unchanged(self) -> None:
        """gpt-5.4 with an already-valid effort value should not be changed."""
        self.assertEqual(reasoning_effort_for_model("gpt-5.4-mini", "low"), "low")
        self.assertEqual(reasoning_effort_for_model("gpt-5.4-mini", "high"), "high")
        self.assertEqual(reasoning_effort_for_model("gpt-5.4-mini", "none"), "none")

    def test_non_gpt5_passes_through(self) -> None:
        """Non-gpt5 models should pass effort unchanged."""
        self.assertEqual(reasoning_effort_for_model("gpt-4o", "minimal"), "minimal")


class IsGpt5NanoOrMiniTestCase(unittest.TestCase):
    """Tests for is_gpt5_nano_or_mini_model."""

    def test_gpt5_mini(self) -> None:
        self.assertTrue(is_gpt5_nano_or_mini_model("gpt-5-mini"))

    def test_gpt54_mini(self) -> None:
        self.assertTrue(is_gpt5_nano_or_mini_model("gpt-5.4-mini"))

    def test_gpt5_nano(self) -> None:
        self.assertTrue(is_gpt5_nano_or_mini_model("gpt-5-nano"))

    def test_gpt54_nano(self) -> None:
        self.assertTrue(is_gpt5_nano_or_mini_model("gpt-5.4-nano"))

    def test_gpt5_full(self) -> None:
        self.assertFalse(is_gpt5_nano_or_mini_model("gpt-5"))

    def test_gpt4o(self) -> None:
        self.assertFalse(is_gpt5_nano_or_mini_model("gpt-4o"))


if __name__ == "__main__":
    unittest.main()
