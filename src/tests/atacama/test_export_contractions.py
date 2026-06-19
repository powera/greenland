#!/usr/bin/env python3

"""Tests for English contraction handling in the atacama export.

Contractions (don't, isn't, we're, ...) are emitted into the export's
``_stopwords`` section so the atacama-powera annotator token-matches them in
the output. They are flagged as stopwords and not processed further: each
carries a ``pos`` category and a ``lemma`` slot that reuses the stopword
schema's display field to hold the expansion (e.g. "do not").
"""

import json
import os
import tempfile
import unittest
from typing import Dict

import constants
from atacama.export_atacama import CONTRACTIONS, AtacamaExporter


class ContractionTableTest(unittest.TestCase):
    """The CONTRACTIONS constant must be well-formed for the export schema."""

    def test_keys_are_lowercase(self) -> None:
        for key in CONTRACTIONS:
            self.assertEqual(key, key.lower(), f"contraction key not lowercase: {key!r}")

    def test_each_entry_has_pos_and_lemma(self) -> None:
        for key, annotation in CONTRACTIONS.items():
            self.assertEqual(
                set(annotation),
                {"pos", "lemma"},
                f"{key!r} must have exactly pos+lemma",
            )

    def test_pos_uses_known_categories(self) -> None:
        for key, annotation in CONTRACTIONS.items():
            self.assertIn(
                annotation["pos"],
                ("verb", "pronoun"),
                f"unexpected pos for {key!r}: {annotation['pos']!r}",
            )

    def test_common_contractions_present(self) -> None:
        for key in ("don't", "isn't", "can't", "won't", "i'm", "we're", "it's", "let's"):
            self.assertIn(key, CONTRACTIONS)


class LoadStopwordsContractionTest(unittest.TestCase):
    """_load_stopwords seeds the result with the contraction table."""

    def setUp(self) -> None:
        # Point PROJECT_ROOT at a temp dir we control so the stopwords file
        # contents are deterministic for the test.
        self._orig_root = constants.PROJECT_ROOT
        self._tmp = tempfile.TemporaryDirectory()
        constants.PROJECT_ROOT = self._tmp.name
        self._stopwords_path = os.path.join(
            self._tmp.name, "data", "release", "stopwords", "en.jsonl"
        )
        os.makedirs(os.path.dirname(self._stopwords_path), exist_ok=True)

    def tearDown(self) -> None:
        constants.PROJECT_ROOT = self._orig_root
        self._tmp.cleanup()

    def _write_stopwords(self, lines: list[dict]) -> None:
        with open(self._stopwords_path, "w", encoding="utf-8") as f:
            for entry in lines:
                f.write(json.dumps(entry) + "\n")

    def test_contractions_present_with_empty_file(self) -> None:
        self._write_stopwords([])
        result = AtacamaExporter()._load_stopwords()
        self.assertEqual(result["don't"], {"pos": "verb", "lemma": "do not"})
        self.assertEqual(result["we're"], {"pos": "pronoun", "lemma": "we are"})

    def test_contractions_present_when_file_missing(self) -> None:
        # No file written at all → still get the contraction defaults.
        result = AtacamaExporter()._load_stopwords()
        self.assertIn("isn't", result)
        self.assertEqual(result["isn't"], {"pos": "verb", "lemma": "is not"})

    def test_file_entries_merge_with_contractions(self) -> None:
        self._write_stopwords([{"word": "the", "pos": "article", "lemma": "the"}])
        result = AtacamaExporter()._load_stopwords()
        self.assertIn("the", result)  # from file
        self.assertIn("don't", result)  # from contraction table

    def test_file_entry_overrides_contraction_on_collision(self) -> None:
        self._write_stopwords([{"word": "don't", "pos": "curated-pos", "lemma": "curated-lemma"}])
        result: Dict[str, dict] = AtacamaExporter()._load_stopwords()
        self.assertEqual(result["don't"], {"pos": "curated-pos", "lemma": "curated-lemma"})


if __name__ == "__main__":
    unittest.main()
