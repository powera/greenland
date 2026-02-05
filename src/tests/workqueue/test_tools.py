#!/usr/bin/env python3
"""Tests for workqueue.tools module.

Tests the common utilities used by workqueue handler implementations.
"""

import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from wordfreq.storage.backend.config import BackendType
from wordfreq.storage.models.schema import Base, Lemma
from workqueue.tools import (
    build_default_config,
    commit_or_raise,
    extract_payload_param,
    get_lemma_or_raise,
)


class TestExtractPayloadParam(unittest.TestCase):
    """Test extract_payload_param utility (pure function, no DB)."""

    def test_extracts_existing_key(self) -> None:
        payload = {"lemma_id": 42, "lang_code": "fr"}
        self.assertEqual(extract_payload_param(payload, "lemma_id"), 42)
        self.assertEqual(extract_payload_param(payload, "lang_code"), "fr")

    def test_returns_default_for_missing_key(self) -> None:
        payload = {"lemma_id": 42}
        self.assertEqual(extract_payload_param(payload, "lang_code", default="en"), "en")

    def test_returns_none_default_when_no_default(self) -> None:
        payload = {"lemma_id": 42}
        self.assertIsNone(extract_payload_param(payload, "lang_code"))

    def test_required_raises_on_missing(self) -> None:
        payload = {"lemma_id": 42}
        with self.assertRaises(ValueError) as ctx:
            extract_payload_param(payload, "lang_code", required=True)
        self.assertIn("lang_code", str(ctx.exception))

    def test_required_returns_value_when_present(self) -> None:
        payload = {"lemma_id": 42}
        self.assertEqual(extract_payload_param(payload, "lemma_id", required=True), 42)

    def test_default_ignored_when_required(self) -> None:
        """Default is not used when required=True and key is missing."""
        payload: dict = {}
        with self.assertRaises(ValueError):
            extract_payload_param(payload, "key", default="fallback", required=True)

    def test_empty_payload(self) -> None:
        self.assertIsNone(extract_payload_param({}, "anything"))

    def test_none_value_is_returned(self) -> None:
        """A key with None value should return None, not the default."""
        payload: dict = {"key": None}
        self.assertIsNone(extract_payload_param(payload, "key", default="fallback"))

    def test_falsy_values_returned(self) -> None:
        """Falsy values (0, empty string, False) are valid payload values."""
        payload = {"count": 0, "name": "", "flag": False}
        self.assertEqual(extract_payload_param(payload, "count", default=99), 0)
        self.assertEqual(extract_payload_param(payload, "name", default="x"), "")
        self.assertFalse(extract_payload_param(payload, "flag", default=True))


class TestGetLemmaOrRaise(unittest.TestCase):
    """Test get_lemma_or_raise with in-memory SQLite."""

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
        self.session.flush()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def test_returns_existing_lemma(self) -> None:
        result = get_lemma_or_raise(self.session, self.lemma.id)
        self.assertEqual(result.lemma_text, "hello")
        self.assertEqual(result.id, self.lemma.id)

    def test_raises_for_nonexistent(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            get_lemma_or_raise(self.session, 99999)
        self.assertIn("99999", str(ctx.exception))
        self.assertIn("not found", str(ctx.exception))


class TestCommitOrRaise(unittest.TestCase):
    """Test commit_or_raise utility."""

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def test_successful_commit(self) -> None:
        """Successful commit does not raise."""
        lemma = Lemma(
            lemma_text="test",
            definition_text="a test",
            pos_type="noun",
            guid="N01_002",
        )
        self.session.add(lemma)
        commit_or_raise(self.session, "Failed to save")
        # Verify data persisted
        self.assertIsNotNone(lemma.id)

    def test_failed_commit_raises_runtime_error(self) -> None:
        """Commit failure raises RuntimeError with prefix."""
        # Force a commit failure by adding a duplicate primary key
        lemma1 = Lemma(
            lemma_text="test",
            definition_text="a test",
            pos_type="noun",
            guid="N01_003",
        )
        self.session.add(lemma1)
        self.session.commit()

        # Create a conflicting object with same primary key
        lemma2 = Lemma(
            lemma_text="test2",
            definition_text="another test",
            pos_type="noun",
            guid="N01_003",
        )
        lemma2.id = lemma1.id
        self.session.add(lemma2)

        with self.assertRaises(RuntimeError) as ctx:
            commit_or_raise(self.session, "Failed to save lemma")
        self.assertIn("Failed to save lemma", str(ctx.exception))


class TestBuildDefaultConfig(unittest.TestCase):
    """Test build_default_config utility."""

    @patch("workqueue.tools.Config")
    @patch("workqueue.tools.constants")
    def test_returns_data_source_config(self, mock_constants, mock_config) -> None:
        mock_config.DB_PATH = "/tmp/test.db"
        mock_config.DEBUG = True
        mock_constants.DEFAULT_MODEL = "gpt-4"

        config = build_default_config()
        self.assertEqual(config.backend_type, BackendType.SQLITE)
        self.assertEqual(config.sqlite_path, "/tmp/test.db")
        self.assertEqual(config.model, "gpt-4")
        self.assertTrue(config.debug)


if __name__ == "__main__":
    unittest.main()
