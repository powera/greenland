#!/usr/bin/env python3
"""
Tests for agents.lemma_selection module.

Tests the standardized lemma selection and filtering utilities without
requiring a full database. Uses mocking to test query building logic.
"""

import sys
from pathlib import Path
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import unittest
from unittest.mock import Mock, MagicMock, patch, call
from src.agents.common.lemma_selection import (
    find_lemma_by_guid,
    LemmaQueryBuilder,
    apply_limit_and_sample_rate,
    count_for_confirmation,
    get_lemmas_for_processing,
    LemmaNotFoundError,
)


class MockLemma:
    """Mock Lemma object for testing."""

    def __init__(self, id=1, guid="A01_001", lemma_text="test", difficulty_level=None):
        self.id = id
        self.guid = guid
        self.lemma_text = lemma_text
        self.difficulty_level = difficulty_level
        self.french_translation = None
        self.chinese_translation = None
        self.korean_translation = None
        self.swahili_translation = None
        self.lithuanian_translation = None
        self.vietnamese_translation = None


class TestFindLemmaByGuid(unittest.TestCase):
    """Test the find_lemma_by_guid function."""

    def setUp(self):
        """Set up test fixtures."""
        self.session = Mock()
        self.mock_query = Mock()
        self.session.query.return_value = self.mock_query

    def test_find_existing_guid(self):
        """Test finding a lemma that exists."""
        mock_lemma = MockLemma(guid="A01_001", lemma_text="test")
        self.mock_query.filter.return_value.first.return_value = mock_lemma

        result = find_lemma_by_guid(self.session, "A01_001", error_on_missing=False)

        self.assertEqual(result, mock_lemma)
        self.assertEqual(result.lemma_text, "test")

    def test_find_missing_guid_no_error(self):
        """Test that missing GUID returns None when error_on_missing=False."""
        self.mock_query.filter.return_value.first.return_value = None

        result = find_lemma_by_guid(self.session, "NOTFOUND", error_on_missing=False)

        self.assertIsNone(result)

    @patch('sys.exit')
    @patch('builtins.print')
    def test_find_missing_guid_with_error(self, mock_print, mock_exit):
        """Test that missing GUID exits when error_on_missing=True."""
        self.mock_query.filter.return_value.first.return_value = None

        find_lemma_by_guid(self.session, "NOTFOUND", error_on_missing=True)

        # Should print error message
        self.assertTrue(mock_print.called)
        error_msg = mock_print.call_args_list[0][0][0]
        self.assertIn("NOTFOUND", error_msg)
        self.assertIn("No lemma found", error_msg)

        # Should exit with code 1
        mock_exit.assert_called_once_with(1)


class TestLemmaQueryBuilder(unittest.TestCase):
    """Test the LemmaQueryBuilder class."""

    def setUp(self):
        """Set up test fixtures."""
        self.session = Mock()
        self.mock_query = Mock()
        self.session.query.return_value = self.mock_query

        # Set up filter chaining
        self.mock_query.filter.return_value = self.mock_query
        self.mock_query.order_by.return_value = self.mock_query

    def test_basic_query_build(self):
        """Test building a basic query."""
        builder = LemmaQueryBuilder(self.session)
        query = builder.build()

        # Should call session.query with Lemma
        self.session.query.assert_called_once()
        self.assertEqual(query, self.mock_query)

    def test_curated_only_filter(self):
        """Test curated_only filter."""
        builder = LemmaQueryBuilder(self.session)
        builder.curated_only()

        # Should add filter for guid.isnot(None)
        self.assertTrue(self.mock_query.filter.called)

    def test_difficulty_level_filter(self):
        """Test by_difficulty_level filter."""
        builder = LemmaQueryBuilder(self.session)
        builder.by_difficulty_level(5)

        # Should add filter
        self.assertTrue(self.mock_query.filter.called)

    def test_difficulty_level_none_skips_filter(self):
        """Test that difficulty_level=None doesn't add a filter."""
        builder = LemmaQueryBuilder(self.session)
        builder.by_difficulty_level(None)

        # Should not add filter
        self.assertFalse(self.mock_query.filter.called)

    def test_order_by_id_ascending(self):
        """Test ordering by ID ascending."""
        builder = LemmaQueryBuilder(self.session)
        builder.order_by_id(ascending=True)

        # Should call order_by
        self.assertTrue(self.mock_query.order_by.called)

    def test_order_by_id_descending(self):
        """Test ordering by ID descending."""
        builder = LemmaQueryBuilder(self.session)
        builder.order_by_id(ascending=False)

        # Should call order_by
        self.assertTrue(self.mock_query.order_by.called)

    def test_method_chaining(self):
        """Test that methods can be chained."""
        builder = LemmaQueryBuilder(self.session)

        result = (
            builder
            .curated_only()
            .by_difficulty_level(3)
            .order_by_id()
            .build()
        )

        # All methods should have been called
        self.assertTrue(self.mock_query.filter.called)
        self.assertTrue(self.mock_query.order_by.called)
        self.assertEqual(result, self.mock_query)

    @patch('agents.lemma_selection.LANG_CODE_TO_LLM_FIELD', {'fr': 'french_translation'})
    def test_has_translation_in_valid_language(self):
        """Test has_translation_in with valid language code."""
        builder = LemmaQueryBuilder(self.session)
        builder.has_translation_in('fr')

        # Should add filter
        self.assertTrue(self.mock_query.filter.called)

    @patch('agents.lemma_selection.LANG_CODE_TO_LLM_FIELD', {'fr': 'french_translation'})
    def test_has_translation_in_invalid_language(self):
        """Test has_translation_in with invalid language code raises error."""
        builder = LemmaQueryBuilder(self.session)

        with self.assertRaises(ValueError) as context:
            builder.has_translation_in('invalid')

        self.assertIn("not recognized", str(context.exception))

    def test_filter_custom(self):
        """Test custom filter function."""
        builder = LemmaQueryBuilder(self.session)

        def custom_filter(query):
            return query.filter("custom condition")

        builder.filter_custom(custom_filter)

        # Should have called filter with custom condition
        self.assertTrue(self.mock_query.filter.called)


class TestApplyLimitAndSampleRate(unittest.TestCase):
    """Test apply_limit_and_sample_rate function."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_query = Mock()

    def test_no_limit_no_sample(self):
        """Test with no limit and no sampling."""
        lemmas = [MockLemma(id=i) for i in range(10)]
        self.mock_query.limit.return_value.all.return_value = lemmas
        self.mock_query.all.return_value = lemmas

        result = apply_limit_and_sample_rate(self.mock_query, limit=None, sample_rate=1.0)

        self.assertEqual(len(result), 10)
        self.assertFalse(self.mock_query.limit.called)

    def test_with_limit_no_sample(self):
        """Test with limit but no sampling."""
        lemmas = [MockLemma(id=i) for i in range(5)]
        limited_query = Mock()
        limited_query.all.return_value = lemmas
        self.mock_query.limit.return_value = limited_query

        result = apply_limit_and_sample_rate(self.mock_query, limit=5, sample_rate=1.0)

        self.mock_query.limit.assert_called_once_with(5)
        self.assertEqual(len(result), 5)

    @patch('random.sample')
    def test_with_sample_rate(self, mock_random_sample):
        """Test with sample rate."""
        lemmas = [MockLemma(id=i) for i in range(10)]
        self.mock_query.all.return_value = lemmas
        sampled_lemmas = lemmas[:3]
        mock_random_sample.return_value = sampled_lemmas

        result = apply_limit_and_sample_rate(self.mock_query, limit=None, sample_rate=0.3)

        # Should sample 30% of 10 = 3 items
        mock_random_sample.assert_called_once_with(lemmas, 3)
        self.assertEqual(len(result), 3)

    @patch('random.sample')
    def test_with_limit_and_sample_rate(self, mock_random_sample):
        """Test with both limit and sample rate."""
        lemmas = [MockLemma(id=i) for i in range(5)]
        limited_query = Mock()
        limited_query.all.return_value = lemmas
        self.mock_query.limit.return_value = limited_query
        sampled_lemmas = lemmas[:2]
        mock_random_sample.return_value = sampled_lemmas

        result = apply_limit_and_sample_rate(self.mock_query, limit=5, sample_rate=0.5)

        # Should limit to 5, then sample 50% = 2.5 -> 2 items
        self.mock_query.limit.assert_called_once_with(5)
        mock_random_sample.assert_called_once_with(lemmas, 2)
        self.assertEqual(len(result), 2)

    @patch('random.sample')
    def test_sample_rate_always_returns_at_least_one(self, mock_random_sample):
        """Test that sampling always returns at least 1 item."""
        lemmas = [MockLemma(id=1)]
        self.mock_query.all.return_value = lemmas
        mock_random_sample.return_value = lemmas

        result = apply_limit_and_sample_rate(self.mock_query, limit=None, sample_rate=0.01)

        # Should sample at least 1 item even with 1% of 1
        mock_random_sample.assert_called_once_with(lemmas, 1)
        self.assertEqual(len(result), 1)


class TestCountForConfirmation(unittest.TestCase):
    """Test count_for_confirmation function."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_query = Mock()

    def test_count_no_limit_no_sample(self):
        """Test counting with no limit and no sampling."""
        self.mock_query.count.return_value = 100

        result = count_for_confirmation(self.mock_query, limit=None, sample_rate=1.0)

        self.assertEqual(result, 100)
        self.assertFalse(self.mock_query.limit.called)

    def test_count_with_limit(self):
        """Test counting with limit."""
        limited_query = Mock()
        limited_query.count.return_value = 50
        self.mock_query.limit.return_value = limited_query

        result = count_for_confirmation(self.mock_query, limit=50, sample_rate=1.0)

        self.mock_query.limit.assert_called_once_with(50)
        self.assertEqual(result, 50)

    def test_count_with_sample_rate(self):
        """Test counting with sample rate."""
        self.mock_query.count.return_value = 100

        result = count_for_confirmation(self.mock_query, limit=None, sample_rate=0.3)

        # 30% of 100 = 30
        self.assertEqual(result, 30)

    def test_count_with_limit_and_sample_rate(self):
        """Test counting with both limit and sample rate."""
        limited_query = Mock()
        limited_query.count.return_value = 50
        self.mock_query.limit.return_value = limited_query

        result = count_for_confirmation(self.mock_query, limit=50, sample_rate=0.5)

        # 50% of 50 = 25
        self.assertEqual(result, 25)

    def test_count_always_returns_at_least_one(self):
        """Test that count always returns at least 1."""
        self.mock_query.count.return_value = 10

        result = count_for_confirmation(self.mock_query, limit=None, sample_rate=0.01)

        # 1% of 10 = 0.1, should round up to 1
        self.assertEqual(result, 1)


class TestGetLemmasForProcessing(unittest.TestCase):
    """Test the high-level get_lemmas_for_processing function."""

    @patch('agents.lemma_selection.find_lemma_by_guid')
    def test_single_lemma_by_guid(self, mock_find):
        """Test getting a single lemma by GUID."""
        session = Mock()
        mock_lemma = MockLemma(guid="A01_001", lemma_text="test")
        mock_find.return_value = mock_lemma

        result = get_lemmas_for_processing(session, guid="A01_001")

        mock_find.assert_called_once_with(session, "A01_001", error_on_missing=True)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], mock_lemma)

    def test_batch_mode_basic(self):
        """Test batch mode with basic filters."""
        session = Mock()
        mock_query = Mock()
        lemmas = [MockLemma(id=i) for i in range(5)]

        # Set up the query chain
        session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = lemmas

        result = get_lemmas_for_processing(
            session,
            curated_only=True,
            limit=None,
            sample_rate=1.0,
        )

        # Should build query with curated_only filter
        self.assertTrue(session.query.called)
        self.assertTrue(mock_query.filter.called)
        self.assertEqual(len(result), 5)

    def test_batch_mode_with_difficulty_level(self):
        """Test batch mode with difficulty level filter."""
        session = Mock()
        mock_query = Mock()
        lemmas = [MockLemma(id=1, difficulty_level=3)]

        session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = lemmas

        result = get_lemmas_for_processing(
            session,
            curated_only=True,
            difficulty_level=3,
        )

        # Should apply difficulty level filter
        self.assertTrue(mock_query.filter.called)
        self.assertEqual(len(result), 1)

    @patch('agents.lemma_selection.LANG_CODE_TO_LLM_FIELD', {'fr': 'french_translation'})
    def test_batch_mode_with_language_filter(self):
        """Test batch mode with language filter."""
        session = Mock()
        mock_query = Mock()
        lemmas = [MockLemma(id=1)]
        lemmas[0].french_translation = "bonjour"

        session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = lemmas

        result = get_lemmas_for_processing(
            session,
            curated_only=True,
            language_code='fr',
        )

        # Should apply language filter
        self.assertTrue(mock_query.filter.called)
        self.assertEqual(len(result), 1)

    @patch('random.sample')
    def test_batch_mode_with_limit_and_sample_rate(self, mock_random_sample):
        """Test batch mode with limit and sample rate."""
        session = Mock()
        mock_query = Mock()
        lemmas = [MockLemma(id=i) for i in range(10)]
        sampled = lemmas[:5]

        session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = lemmas
        mock_random_sample.return_value = sampled

        result = get_lemmas_for_processing(
            session,
            limit=10,
            sample_rate=0.5,
        )

        # Should apply limit and sample
        mock_query.limit.assert_called_once_with(10)
        mock_random_sample.assert_called_once()
        self.assertEqual(len(result), 5)


if __name__ == '__main__':
    unittest.main()
