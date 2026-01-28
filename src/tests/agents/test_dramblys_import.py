#!/usr/bin/env python3
"""
Tests for DRAMBLYS JSONL import functionality.

Tests the field difference detection algorithm without requiring database access.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock
import importlib.util

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Mock the SQLAlchemy-dependent modules BEFORE importing jsonl_import
# This allows us to test the pure-Python logic without database dependencies
mock_schema = MagicMock()
mock_schema.Lemma = MagicMock
mock_schema.LemmaTranslation = MagicMock
sys.modules["wordfreq.storage.models.schema"] = mock_schema

mock_translation_helpers = MagicMock()
mock_translation_helpers.LANGUAGE_FIELDS = {"en", "es", "fr", "de", "zh", "ja", "ko"}
sys.modules["wordfreq.storage.translation_helpers"] = mock_translation_helpers

# Also mock the agents.dramblys package itself to prevent __init__.py from loading
sys.modules["agents.dramblys"] = MagicMock()

import unittest

# Import the module directly to bypass the package __init__.py
_module_path = Path(__file__).parent.parent.parent / "agents" / "dramblys" / "jsonl_import.py"
_spec = importlib.util.spec_from_file_location("agents.dramblys.jsonl_import", _module_path)
assert _spec is not None, "Could not load module spec"
_jsonl_import = importlib.util.module_from_spec(_spec)
sys.modules["agents.dramblys.jsonl_import"] = _jsonl_import
assert _spec.loader is not None, "Module spec has no loader"
_spec.loader.exec_module(_jsonl_import)
JSONLImporter = _jsonl_import.JSONLImporter


class MockLemma:
    """Mock Lemma object for testing without database."""

    def __init__(self, **kwargs):
        self.guid = kwargs.get("guid")
        self.lemma_text = kwargs.get("lemma_text", "")
        self.definition_text = kwargs.get("definition_text", "")
        self.pos_type = kwargs.get("pos_type", "")
        self.pos_subtype = kwargs.get("pos_subtype", "")
        self.difficulty_level = kwargs.get("difficulty_level")


class TestJSONLImportDiff(unittest.TestCase):
    """Test the field difference detection algorithm."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a mock importer (no session needed for diff tests)
        self.importer = JSONLImporter(session=None, dry_run=True)

    def test_no_differences(self):
        """Test when existing lemma matches JSONL data exactly."""
        existing = MockLemma(
            guid="A01_001",
            lemma_text="red",
            definition_text="The color of blood",
            pos_type="adjective",
            pos_subtype="color",
            difficulty_level=1,
        )

        jsonl_data = {
            "guid": "A01_001",
            "concept_label": "red",
            "concept_definition": "The color of blood",
            "pos_type": "adjective",
            "pos_subtype": "color",
            "difficulty_level": 1,
        }

        diffs = self.importer.get_field_differences(existing, jsonl_data)
        self.assertEqual(diffs, [])

    def test_concept_label_change(self):
        """Test detection of concept_label (lemma_text) change."""
        existing = MockLemma(
            guid="A01_001",
            lemma_text="red",
            definition_text="The color of blood",
            pos_type="adjective",
            pos_subtype="color",
            difficulty_level=1,
        )

        jsonl_data = {
            "guid": "A01_001",
            "concept_label": "crimson",
            "concept_definition": "The color of blood",
            "pos_type": "adjective",
            "pos_subtype": "color",
            "difficulty_level": 1,
        }

        diffs = self.importer.get_field_differences(existing, jsonl_data)
        self.assertEqual(len(diffs), 1)
        self.assertIn("lemma_text", diffs[0])
        self.assertIn("red", diffs[0])
        self.assertIn("crimson", diffs[0])

    def test_definition_change(self):
        """Test detection of definition change."""
        existing = MockLemma(
            guid="A01_001",
            lemma_text="red",
            definition_text="The color of blood",
            pos_type="adjective",
            pos_subtype="color",
            difficulty_level=1,
        )

        jsonl_data = {
            "guid": "A01_001",
            "concept_label": "red",
            "concept_definition": "A primary color between orange and violet in the visible spectrum",
            "pos_type": "adjective",
            "pos_subtype": "color",
            "difficulty_level": 1,
        }

        diffs = self.importer.get_field_differences(existing, jsonl_data)
        self.assertEqual(len(diffs), 1)
        self.assertIn("definition", diffs[0])

    def test_definition_truncation(self):
        """Test that long definitions are truncated in diff output."""
        existing = MockLemma(
            guid="A01_001",
            lemma_text="red",
            definition_text="A very long definition that exceeds sixty characters and should be truncated for display purposes",
            pos_type="adjective",
            pos_subtype="color",
            difficulty_level=1,
        )

        jsonl_data = {
            "guid": "A01_001",
            "concept_label": "red",
            "concept_definition": "Another very long definition that also exceeds sixty characters and will be truncated",
            "pos_type": "adjective",
            "pos_subtype": "color",
            "difficulty_level": 1,
        }

        diffs = self.importer.get_field_differences(existing, jsonl_data)
        self.assertEqual(len(diffs), 1)
        # Check that truncation occurred (should contain "...")
        self.assertIn("...", diffs[0])

    def test_difficulty_level_change(self):
        """Test detection of difficulty_level change."""
        existing = MockLemma(
            guid="A01_001",
            lemma_text="red",
            definition_text="The color of blood",
            pos_type="adjective",
            pos_subtype="color",
            difficulty_level=1,
        )

        jsonl_data = {
            "guid": "A01_001",
            "concept_label": "red",
            "concept_definition": "The color of blood",
            "pos_type": "adjective",
            "pos_subtype": "color",
            "difficulty_level": 2,
        }

        diffs = self.importer.get_field_differences(existing, jsonl_data)
        self.assertEqual(len(diffs), 1)
        self.assertIn("difficulty_level", diffs[0])
        self.assertIn("1", diffs[0])
        self.assertIn("2", diffs[0])

    def test_category_change(self):
        """Test detection of category (pos_type/pos_subtype) change."""
        existing = MockLemma(
            guid="A01_001",
            lemma_text="red",
            definition_text="The color of blood",
            pos_type="adjective",
            pos_subtype="color",
            difficulty_level=1,
        )

        jsonl_data = {
            "guid": "A01_001",
            "concept_label": "red",
            "concept_definition": "The color of blood",
            "pos_type": "noun",
            "pos_subtype": "color",
            "difficulty_level": 1,
        }

        diffs = self.importer.get_field_differences(existing, jsonl_data)
        self.assertEqual(len(diffs), 1)
        self.assertIn("category", diffs[0])
        self.assertIn("adjective/color", diffs[0])
        self.assertIn("noun/color", diffs[0])

    def test_multiple_changes(self):
        """Test detection of multiple field changes."""
        existing = MockLemma(
            guid="A01_001",
            lemma_text="red",
            definition_text="The color of blood",
            pos_type="adjective",
            pos_subtype="color",
            difficulty_level=1,
        )

        jsonl_data = {
            "guid": "A01_001",
            "concept_label": "crimson",
            "concept_definition": "A deep red color",
            "pos_type": "adjective",
            "pos_subtype": "color",
            "difficulty_level": 2,
        }

        diffs = self.importer.get_field_differences(existing, jsonl_data)
        self.assertEqual(len(diffs), 3)  # label, definition, difficulty

        # Check that all expected changes are present
        diff_str = " ".join(diffs)
        self.assertIn("lemma_text", diff_str)
        self.assertIn("definition", diff_str)
        self.assertIn("difficulty_level", diff_str)

    def test_none_vs_empty_string(self):
        """Test handling of None vs empty string in pos_subtype."""
        existing = MockLemma(
            guid="A01_001",
            lemma_text="red",
            definition_text="The color of blood",
            pos_type="adjective",
            pos_subtype=None,
            difficulty_level=1,
        )

        jsonl_data = {
            "guid": "A01_001",
            "concept_label": "red",
            "concept_definition": "The color of blood",
            "pos_type": "adjective",
            "pos_subtype": "",
            "difficulty_level": 1,
        }

        diffs = self.importer.get_field_differences(existing, jsonl_data)
        # None and "" should be treated as different
        self.assertEqual(len(diffs), 1)
        self.assertIn("category", diffs[0])


if __name__ == "__main__":
    unittest.main()
