#!/usr/bin/env python3
"""
Tests for agents.common_args module.

Tests the standardized command-line argument patterns and utilities
used across all agents.
"""

import sys
from pathlib import Path

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import unittest
import argparse
from unittest.mock import Mock, patch, MagicMock
from io import StringIO

from src.agents.common.common_args import (
    add_common_args,
    add_llm_args,
    add_output_args,
    add_processing_args,
    add_guid_arg,
    add_backend_args,
    add_language_args,
    validate_cache_args,
    confirm_operation,
    count_items_for_confirmation,
    get_standard_db_path,
    get_data_source_config,
)


class TestAddCommonArgs(unittest.TestCase):
    """Test add_common_args function."""

    def test_adds_db_path_arg(self):
        """Test that --db-path argument is added."""
        parser = argparse.ArgumentParser()
        add_common_args(parser)
        args = parser.parse_args(["--db-path", "/path/to/db.sqlite"])
        self.assertEqual(args.db_path, "/path/to/db.sqlite")

    def test_adds_debug_flag(self):
        """Test that --debug flag is added."""
        parser = argparse.ArgumentParser()
        add_common_args(parser)
        args = parser.parse_args(["--debug"])
        self.assertTrue(args.debug)

    def test_adds_yes_flag(self):
        """Test that --yes/-y flag is added."""
        parser = argparse.ArgumentParser()
        add_common_args(parser)

        # Test --yes
        args = parser.parse_args(["--yes"])
        self.assertTrue(args.yes)

        # Test -y
        args = parser.parse_args(["-y"])
        self.assertTrue(args.yes)

    def test_adds_dry_run_flag(self):
        """Test that --dry-run flag is added."""
        parser = argparse.ArgumentParser()
        add_common_args(parser)
        args = parser.parse_args(["--dry-run"])
        self.assertTrue(args.dry_run)

    def test_default_values(self):
        """Test default values when no args provided."""
        parser = argparse.ArgumentParser()
        add_common_args(parser)
        args = parser.parse_args([])

        self.assertIsNone(args.db_path)
        self.assertFalse(args.debug)
        self.assertFalse(args.yes)
        self.assertFalse(args.dry_run)


class TestAddLlmArgs(unittest.TestCase):
    """Test add_llm_args function."""

    def test_adds_model_arg(self):
        """Test that --model argument is added."""
        parser = argparse.ArgumentParser()
        add_llm_args(parser)
        args = parser.parse_args(["--model", "gpt-4"])
        self.assertEqual(args.model, "gpt-4")

    def test_model_default_value(self):
        """Test that model has correct default value."""
        parser = argparse.ArgumentParser()
        add_llm_args(parser, default_model="custom-model")
        args = parser.parse_args([])
        self.assertEqual(args.model, "custom-model")

    def test_adds_throttle_arg(self):
        """Test that --throttle argument is added."""
        parser = argparse.ArgumentParser()
        add_llm_args(parser)
        args = parser.parse_args(["--throttle", "2.5"])
        self.assertEqual(args.throttle, 2.5)

    def test_adds_barsukas_url_arg(self):
        """Test that --barsukas-url argument is added."""
        parser = argparse.ArgumentParser()
        add_llm_args(parser)
        args = parser.parse_args(["--barsukas-url", "http://localhost:5000"])
        self.assertEqual(args.barsukas_url, "http://localhost:5000")

    def test_adds_cache_only_flag(self):
        """Test that --cache-only flag is added."""
        parser = argparse.ArgumentParser()
        add_llm_args(parser)
        args = parser.parse_args(["--cache-only"])
        self.assertTrue(args.cache_only)


class TestAddOutputArgs(unittest.TestCase):
    """Test add_output_args function."""

    def test_adds_output_arg(self):
        """Test that --output argument is added."""
        parser = argparse.ArgumentParser()
        add_output_args(parser)
        args = parser.parse_args(["--output", "/path/to/output.json"])
        self.assertEqual(args.output, "/path/to/output.json")


class TestAddProcessingArgs(unittest.TestCase):
    """Test add_processing_args function."""

    def test_adds_limit_arg(self):
        """Test that --limit argument is added."""
        parser = argparse.ArgumentParser()
        add_processing_args(parser)
        args = parser.parse_args(["--limit", "100"])
        self.assertEqual(args.limit, 100)

    def test_adds_sample_rate_arg(self):
        """Test that --sample-rate argument is added."""
        parser = argparse.ArgumentParser()
        add_processing_args(parser)
        args = parser.parse_args(["--sample-rate", "0.5"])
        self.assertEqual(args.sample_rate, 0.5)

    def test_sample_rate_default(self):
        """Test that sample-rate defaults to 1.0."""
        parser = argparse.ArgumentParser()
        add_processing_args(parser)
        args = parser.parse_args([])
        self.assertEqual(args.sample_rate, 1.0)


class TestAddGuidArg(unittest.TestCase):
    """Test add_guid_arg function."""

    def test_adds_guid_arg(self):
        """Test that --guid argument is added."""
        parser = argparse.ArgumentParser()
        add_guid_arg(parser)
        args = parser.parse_args(["--guid", "A01_001"])
        self.assertEqual(args.guid, "A01_001")

    def test_custom_help_text(self):
        """Test that custom help text is used."""
        parser = argparse.ArgumentParser()
        add_guid_arg(parser, help_text="Custom help text")

        # Check that the help text is set correctly
        # (We can't easily test the actual help output, but we can verify it doesn't error)
        args = parser.parse_args([])
        self.assertIsNone(args.guid)


class TestAddBackendArgs(unittest.TestCase):
    """Test add_backend_args function."""

    def test_adds_backend_arg(self):
        """Test that --backend argument is added."""
        parser = argparse.ArgumentParser()
        add_backend_args(parser)
        args = parser.parse_args(["--backend", "sqlite"])
        self.assertEqual(args.backend, "sqlite")

    def test_backend_choices(self):
        """Test that --backend only accepts valid choices."""
        parser = argparse.ArgumentParser()
        add_backend_args(parser)

        # Valid choice
        args = parser.parse_args(["--backend", "jsonl"])
        self.assertEqual(args.backend, "jsonl")

        # Invalid choice should raise error
        with self.assertRaises(SystemExit):
            parser.parse_args(["--backend", "invalid"])

    def test_adds_data_dir_arg(self):
        """Test that --data-dir argument is added."""
        parser = argparse.ArgumentParser()
        add_backend_args(parser)
        args = parser.parse_args(["--data-dir", "/path/to/data"])
        self.assertEqual(args.data_dir, "/path/to/data")


class TestAddLanguageArgs(unittest.TestCase):
    """Test add_language_args function."""

    def test_single_language_mode(self):
        """Test single language argument mode."""
        parser = argparse.ArgumentParser()
        add_language_args(parser, multiple=False)
        args = parser.parse_args(["--language", "fr"])
        self.assertEqual(args.language, "fr")

    def test_multiple_languages_mode(self):
        """Test multiple languages argument mode."""
        parser = argparse.ArgumentParser()
        add_language_args(parser, multiple=True)
        args = parser.parse_args(["--languages", "fr", "es", "de"])
        self.assertEqual(args.languages, ["fr", "es", "de"])

    def test_language_alias(self):
        """Test that --language alias works in multiple mode."""
        parser = argparse.ArgumentParser()
        add_language_args(parser, multiple=True)
        args = parser.parse_args(["--language", "en"])
        self.assertEqual(args.languages, ["en"])


class TestValidateCacheArgs(unittest.TestCase):
    """Test validate_cache_args function."""

    @patch("sys.exit")
    @patch("builtins.print")
    def test_cache_only_without_barsukas_url_fails(self, mock_print, mock_exit):
        """Test that --cache-only without --barsukas-url fails validation."""
        args = argparse.Namespace(cache_only=True, barsukas_url=None)
        validate_cache_args(args)

        mock_print.assert_called_once()
        self.assertIn("--cache-only requires --barsukas-url", mock_print.call_args[0][0])
        mock_exit.assert_called_once_with(1)

    def test_cache_only_with_barsukas_url_passes(self):
        """Test that --cache-only with --barsukas-url passes validation."""
        args = argparse.Namespace(cache_only=True, barsukas_url="http://localhost:5000")
        # Should not raise or exit
        validate_cache_args(args)

    def test_no_cache_only_passes(self):
        """Test that no --cache-only passes validation."""
        args = argparse.Namespace(cache_only=False)
        # Should not raise or exit
        validate_cache_args(args)

    def test_missing_cache_only_attribute_passes(self):
        """Test that missing cache_only attribute passes validation."""
        args = argparse.Namespace()
        # Should not raise or exit
        validate_cache_args(args)


class TestConfirmOperation(unittest.TestCase):
    """Test confirm_operation function."""

    def test_skip_confirmation_returns_true(self):
        """Test that skip_confirmation=True returns True without prompting."""
        result = confirm_operation(
            message="Test message",
            skip_confirmation=True,
        )
        self.assertTrue(result)

    @patch("builtins.print")
    def test_dry_run_returns_true(self, mock_print):
        """Test that dry_run=True returns True and prints message."""
        result = confirm_operation(
            message="Test message",
            dry_run=True,
        )
        self.assertTrue(result)
        # Should print dry run message
        self.assertTrue(any("DRY RUN" in str(call) for call in mock_print.call_args_list))

    @patch("builtins.input", return_value="y")
    @patch("builtins.print")
    def test_user_confirms_with_y(self, mock_print, mock_input):
        """Test that user entering 'y' confirms operation."""
        result = confirm_operation(
            message="Proceed?",
            estimated_calls=10,
        )
        self.assertTrue(result)
        mock_input.assert_called_once()

    @patch("builtins.input", return_value="yes")
    @patch("builtins.print")
    def test_user_confirms_with_yes(self, mock_print, mock_input):
        """Test that user entering 'yes' confirms operation."""
        result = confirm_operation(message="Proceed?")
        self.assertTrue(result)

    @patch("builtins.input", return_value="n")
    @patch("builtins.print")
    def test_user_declines_with_n(self, mock_print, mock_input):
        """Test that user entering 'n' declines operation."""
        result = confirm_operation(message="Proceed?")
        self.assertFalse(result)
        # Should print "Aborted."
        self.assertTrue(any("Aborted" in str(call) for call in mock_print.call_args_list))

    @patch("builtins.input", return_value="")
    @patch("builtins.print")
    def test_user_declines_with_empty(self, mock_print, mock_input):
        """Test that empty input declines operation."""
        result = confirm_operation(message="Proceed?")
        self.assertFalse(result)

    @patch("builtins.input", return_value="invalid")
    @patch("builtins.print")
    def test_user_declines_with_invalid(self, mock_print, mock_input):
        """Test that invalid input declines operation."""
        result = confirm_operation(message="Proceed?")
        self.assertFalse(result)

    @patch("builtins.input", return_value="y")
    @patch("builtins.print")
    def test_estimated_calls_displayed(self, mock_print, mock_input):
        """Test that estimated calls are displayed in prompt."""
        confirm_operation(
            message="Custom message",
            estimated_calls=42,
        )

        # Check that estimated calls were printed
        printed_text = " ".join(str(call) for call in mock_print.call_args_list)
        self.assertIn("42", printed_text)
        self.assertIn("LLM API calls", printed_text)


class TestCountItemsForConfirmation(unittest.TestCase):
    """Test count_items_for_confirmation function."""

    def test_basic_count(self):
        """Test basic item counting."""
        mock_session = Mock()
        mock_query = Mock()
        mock_query.count.return_value = 10

        def query_builder(session, args):
            return mock_query

        args = argparse.Namespace(limit=None, sample_rate=1.0)

        count = count_items_for_confirmation(
            lambda: mock_session,
            query_builder,
            args,
        )

        self.assertEqual(count, 10)

    def test_count_with_limit(self):
        """Test counting with limit applied."""
        mock_session = Mock()
        mock_query = Mock()
        limited_query = Mock()
        limited_query.count.return_value = 5
        mock_query.limit.return_value = limited_query

        def query_builder(session, args):
            return mock_query

        args = argparse.Namespace(limit=5, sample_rate=1.0)

        count = count_items_for_confirmation(
            lambda: mock_session,
            query_builder,
            args,
        )

        self.assertEqual(count, 5)
        mock_query.limit.assert_called_once_with(5)

    def test_count_with_sample_rate(self):
        """Test counting with sample rate."""
        mock_session = Mock()
        mock_query = Mock()
        mock_query.count.return_value = 100

        def query_builder(session, args):
            return mock_query

        args = argparse.Namespace(limit=None, sample_rate=0.3)

        count = count_items_for_confirmation(
            lambda: mock_session,
            query_builder,
            args,
        )

        # 30% of 100 = 30
        self.assertEqual(count, 30)

    def test_count_with_multiplier(self):
        """Test counting with multiplier (e.g., for multiple API calls per item)."""
        mock_session = Mock()
        mock_query = Mock()
        mock_query.count.return_value = 10

        def query_builder(session, args):
            return mock_query

        args = argparse.Namespace(limit=None, sample_rate=1.0)

        count = count_items_for_confirmation(
            lambda: mock_session,
            query_builder,
            args,
            multiplier=3,
        )

        # 10 items * 3 = 30
        self.assertEqual(count, 30)

    def test_session_closed_after_count(self):
        """Test that session is closed after counting."""
        mock_session = Mock()
        mock_query = Mock()
        mock_query.count.return_value = 5

        def query_builder(session, args):
            return mock_query

        args = argparse.Namespace(limit=None, sample_rate=1.0)

        count_items_for_confirmation(
            lambda: mock_session,
            query_builder,
            args,
        )

        mock_session.close.assert_called_once()


class TestGetStandardDbPath(unittest.TestCase):
    """Test get_standard_db_path function."""

    def test_returns_provided_path(self):
        """Test that provided path is returned."""
        path = get_standard_db_path("/custom/path/db.sqlite")
        self.assertEqual(path, "/custom/path/db.sqlite")

    @patch.dict("os.environ", {"GREENLAND_DB": "/env/path/db.sqlite"})
    def test_returns_env_var_when_no_arg(self):
        """Test that environment variable is used when no arg provided."""
        path = get_standard_db_path(None)
        self.assertEqual(path, "/env/path/db.sqlite")

    @patch.dict("os.environ", {}, clear=True)
    def test_returns_default_when_no_arg_or_env(self):
        """Test that default path is returned when no arg or env var."""
        path = get_standard_db_path(None)
        # Should return default path
        self.assertIn("greenland.db", path)


class TestGetDataSourceConfig(unittest.TestCase):
    """Test get_data_source_config function."""

    @patch("agents.common_args.DEFAULT_MODEL", "default-model")
    @patch("agents.common_args.constants.WORDFREQ_DB_PATH", "/default/db.sqlite")
    def test_default_sqlite_config(self):
        """Test default SQLite configuration."""
        args = argparse.Namespace()
        config = get_data_source_config(args)

        from wordfreq.storage.backend.config import BackendType

        self.assertEqual(config.backend_type, BackendType.SQLITE)
        self.assertEqual(config.sqlite_path, "/default/db.sqlite")
        self.assertEqual(config.model, "default-model")

    @patch("agents.common_args.constants.WORDFREQ_DB_PATH", "/default/db.sqlite")
    def test_explicit_sqlite_backend(self):
        """Test explicit SQLite backend selection."""
        args = argparse.Namespace(
            backend="sqlite",
            db_path="/custom/db.sqlite",
        )
        config = get_data_source_config(args)

        from wordfreq.storage.backend.config import BackendType

        self.assertEqual(config.backend_type, BackendType.SQLITE)
        self.assertEqual(config.sqlite_path, "/custom/db.sqlite")

    def test_jsonl_backend(self):
        """Test JSONL backend configuration."""
        args = argparse.Namespace(
            backend="jsonl",
            data_dir="/path/to/jsonl/data",
        )
        config = get_data_source_config(args)

        from wordfreq.storage.backend.config import BackendType

        self.assertEqual(config.backend_type, BackendType.JSONL)
        self.assertEqual(config.jsonl_data_dir, "/path/to/jsonl/data")

    @patch("sys.exit")
    @patch("builtins.print")
    def test_jsonl_backend_without_data_dir_fails(self, mock_print, mock_exit):
        """Test that JSONL backend without data_dir fails."""
        args = argparse.Namespace(
            backend="jsonl",
        )
        get_data_source_config(args)

        mock_print.assert_called_once()
        self.assertIn("--data-dir is required", mock_print.call_args[0][0])
        mock_exit.assert_called_once_with(1)

    def test_cache_configuration(self):
        """Test cache URL and cache_only configuration."""
        args = argparse.Namespace(
            barsukas_url="http://localhost:5000",
            cache_only=True,
        )
        config = get_data_source_config(args)

        self.assertEqual(config.barsukas_url, "http://localhost:5000")
        self.assertTrue(config.cache_only)

    def test_custom_model(self):
        """Test custom model configuration."""
        args = argparse.Namespace(
            model="custom-model",
        )
        config = get_data_source_config(args)

        self.assertEqual(config.model, "custom-model")

    def test_debug_flag(self):
        """Test debug flag configuration."""
        args = argparse.Namespace(
            debug=True,
        )
        config = get_data_source_config(args)

        self.assertTrue(config.debug)

    @patch("agents.common_args.constants.WORDFREQ_DB_PATH", "/default/db.sqlite")
    def test_db_path_implies_sqlite(self):
        """Test that providing db_path without backend implies SQLite."""
        args = argparse.Namespace(
            db_path="/custom/db.sqlite",
        )
        config = get_data_source_config(args)

        from wordfreq.storage.backend.config import BackendType

        self.assertEqual(config.backend_type, BackendType.SQLITE)
        self.assertEqual(config.sqlite_path, "/custom/db.sqlite")


if __name__ == "__main__":
    unittest.main()
