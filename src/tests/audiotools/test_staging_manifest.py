#!/usr/bin/env python3
"""Tests for staged-manifest parsing and database matching.

This logic moved out of agents.gandras, where it had no coverage because
exercising it meant constructing an agent with an S3 uploader. As a plain
function over a session it is directly testable.
"""

import unittest
from typing import Any, Dict

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from audiotools.staging_manifest import (
    ManifestEntry,
    match_manifest_to_database,
)
from storage.models.schema import Base, Lemma, Sentence, SentenceTranslation


def make_entry(**overrides: Any) -> ManifestEntry:
    """Build a ManifestEntry with sane defaults for the fields under test."""
    data: Dict[str, Any] = {
        "md5": "abc123",
        "agent": "vieversys",
        "voice_name": "ruta",
        "language_code": "lt",
        "expected_text": "labas",
        "guid": None,
        "sentence_id": None,
        "grammatical_form": None,
        "generated_at": "2026-01-01T00:00:00",
        "file_size_bytes": 1234,
        "generation_params": None,
    }
    data.update(overrides)
    return ManifestEntry.from_dict(data, "audio/key.mp3", "audio/key.json")


class TestFromDict(unittest.TestCase):
    """Parsing a manifest dict."""

    def test_reads_every_field(self) -> None:
        entry = ManifestEntry.from_dict(
            {
                "md5": "deadbeef",
                "agent": "gandras",
                "voice_name": "jonas",
                "language_code": "lt",
                "expected_text": "duona",
                "guid": "N01_001",
                "sentence_id": None,
                "grammatical_form": "plural",
                "generated_at": "2026-02-03T04:05:06",
                "file_size_bytes": 42,
                "generation_params": {"speed": 1.0},
            },
            "a.mp3",
            "a.json",
        )
        self.assertEqual(entry.md5, "deadbeef")
        self.assertEqual(entry.guid, "N01_001")
        self.assertEqual(entry.grammatical_form, "plural")
        self.assertEqual(entry.generation_params, {"speed": 1.0})
        self.assertEqual(entry.s3_audio_key, "a.mp3")
        self.assertEqual(entry.s3_manifest_key, "a.json")

    def test_missing_fields_get_defaults(self) -> None:
        """A sparse manifest must not raise."""
        entry = ManifestEntry.from_dict({}, "a.mp3", "a.json")
        self.assertEqual(entry.md5, "")
        self.assertEqual(entry.file_size_bytes, 0)
        self.assertIsNone(entry.guid)

    def test_label_prefers_guid(self) -> None:
        self.assertEqual(make_entry(guid="N01_001").label, "N01_001")
        self.assertEqual(make_entry(sentence_id=7).label, "sentence_7")


class MatchTestCase(unittest.TestCase):
    """Shared in-memory database."""

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

        self.lemma = Lemma(
            lemma_text="hello",
            definition_text="a greeting",
            pos_type="noun",
            guid="N01_001",
        )
        self.session.add(self.lemma)

        self.sentence = Sentence()
        self.session.add(self.sentence)
        self.session.flush()

        self.session.add(
            SentenceTranslation(
                sentence_id=self.sentence.id,
                language_code="lt",
                translation_text="labas ten",
            )
        )
        self.session.flush()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()


class TestSentenceMatching(MatchTestCase):
    """Sentence audio is matched by sentence_id, then text."""

    def test_matches_on_id_and_text(self) -> None:
        entry = make_entry(sentence_id=self.sentence.id, expected_text="labas ten")
        result = match_manifest_to_database(self.session, entry)

        self.assertTrue(result.matched)
        self.assertEqual(result.match_type, "sentence_id")
        self.assertTrue(result.text_matches)
        self.assertEqual(result.warnings, [])

    def test_text_comparison_ignores_case_and_edge_space(self) -> None:
        entry = make_entry(sentence_id=self.sentence.id, expected_text="  LaBaS Ten  ")
        result = match_manifest_to_database(self.session, entry)

        self.assertTrue(result.matched)
        self.assertTrue(result.text_matches)

    def test_text_mismatch_blocks_match_by_default(self) -> None:
        entry = make_entry(sentence_id=self.sentence.id, expected_text="visai kas kita")
        result = match_manifest_to_database(self.session, entry)

        self.assertFalse(result.matched)
        self.assertEqual(result.match_type, "sentence_id_text_mismatch")
        self.assertTrue(any("Text mismatch" in w for w in result.warnings))

    def test_text_mismatch_allowed_when_not_required(self) -> None:
        """--no-require-text-match imports the row anyway, still warning."""
        entry = make_entry(sentence_id=self.sentence.id, expected_text="visai kas kita")
        result = match_manifest_to_database(self.session, entry, require_text_match=False)

        self.assertTrue(result.matched)
        self.assertEqual(result.match_type, "sentence_id_text_mismatch")
        self.assertTrue(any("Text mismatch" in w for w in result.warnings))

    def test_unknown_sentence_id(self) -> None:
        entry = make_entry(sentence_id=9999)
        result = match_manifest_to_database(self.session, entry)

        self.assertFalse(result.matched)
        self.assertEqual(result.match_type, "no_match")
        self.assertTrue(any("9999" in w for w in result.warnings))

    def test_missing_translation_warns(self) -> None:
        entry = make_entry(sentence_id=self.sentence.id, language_code="zh")
        result = match_manifest_to_database(self.session, entry)

        self.assertFalse(result.matched)
        self.assertTrue(any("No zh translation" in w for w in result.warnings))


class TestLemmaMatching(MatchTestCase):
    """Lemma audio is matched by GUID, then text."""

    def test_synthetic_sentence_guid_is_not_treated_as_a_lemma(self) -> None:
        """S_ GUIDs belong to sentences; looking them up as lemmas is wrong."""
        entry = make_entry(guid="S_00007", sentence_id=self.sentence.id, expected_text="labas ten")
        result = match_manifest_to_database(self.session, entry)

        self.assertIsNone(result.lemma)
        self.assertFalse(result.guid_matches)
        self.assertTrue(result.matched)
        self.assertEqual(result.match_type, "sentence_id")

    def test_unknown_guid(self) -> None:
        entry = make_entry(guid="N99_999")
        result = match_manifest_to_database(self.session, entry)

        self.assertFalse(result.matched)
        self.assertEqual(result.match_type, "no_match")
        self.assertTrue(any("N99_999" in w for w in result.warnings))


class TestNoIdentifier(MatchTestCase):
    """A manifest with neither identifier cannot be placed."""

    def test_no_identifier(self) -> None:
        result = match_manifest_to_database(self.session, make_entry())

        self.assertFalse(result.matched)
        self.assertEqual(result.match_type, "no_identifier")
        self.assertIn("Manifest has no guid or sentence_id", result.warnings)


if __name__ == "__main__":
    unittest.main()
