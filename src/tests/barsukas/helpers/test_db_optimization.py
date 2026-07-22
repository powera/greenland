"""Tests for barsukas.helpers.db_optimization.

These are lightweight shape/smoke tests — they verify that the optimised
query helpers return dictionaries with the expected keys and reasonable
values, rather than testing exact business logic.
"""

import pytest
from sqlalchemy.orm import Session

from barsukas.helpers.db_optimization import (
    bulk_get_translations_for_lemmas,
    get_home_page_stats,
    get_lemma_list_filter_options,
    get_lemma_view_data,
)
from storage.models.schema import Lemma


class TestGetHomePageStats:
    """Tests for get_home_page_stats."""

    def test_returns_expected_keys(self, db_session: Session) -> None:
        result = get_home_page_stats(db_session)
        assert set(result.keys()) == {
            "total_lemmas",
            "verified_lemmas",
            "with_difficulty",
            "total_sentences",
        }

    def test_empty_database_returns_zeros(self, db_session: Session) -> None:
        result = get_home_page_stats(db_session)
        assert all(v == 0 for v in result.values())

    def test_counts_match_seed_data(self, seeded_session: Session) -> None:
        # Derived from the seed rather than hardcoded: adding a lemma to the
        # shared fixture should not require editing a literal here.
        expected_total = seeded_session.query(Lemma).count()
        expected_verified = seeded_session.query(Lemma).filter(Lemma.verified.is_(True)).count()
        expected_with_difficulty = (
            seeded_session.query(Lemma).filter(Lemma.difficulty_level.isnot(None)).count()
        )

        result = get_home_page_stats(seeded_session)

        assert result["total_lemmas"] == expected_total
        assert result["verified_lemmas"] == expected_verified
        assert result["with_difficulty"] == expected_with_difficulty
        # Guard the derivation itself: the seed must exercise both branches.
        assert 0 < expected_verified < expected_total


class TestGetLemmaListFilterOptions:
    """Tests for get_lemma_list_filter_options."""

    def test_returns_expected_keys(self, db_session: Session) -> None:
        result = get_lemma_list_filter_options(db_session)
        assert set(result.keys()) == {"pos_types", "pos_subtypes"}

    def test_empty_database(self, db_session: Session) -> None:
        result = get_lemma_list_filter_options(db_session)
        assert result["pos_types"] == []
        assert result["pos_subtypes"] == []

    def test_with_seed_data(self, seeded_session: Session) -> None:
        result = get_lemma_list_filter_options(seeded_session)
        assert "verb" in result["pos_types"]
        assert "noun" in result["pos_types"]

    def test_pos_type_filter(self, seeded_session: Session) -> None:
        result = get_lemma_list_filter_options(seeded_session, pos_type_filter="verb")
        # Should still include all pos_types for the dropdown
        assert "verb" in result["pos_types"]
        assert "noun" in result["pos_types"]
        # But subtypes should only be for verbs
        assert "transitive" in result["pos_subtypes"]
        assert "building" not in result["pos_subtypes"]


class TestGetLemmaViewData:
    """Tests for get_lemma_view_data."""

    def test_returns_none_lemma_for_missing_id(self, db_session: Session) -> None:
        result = get_lemma_view_data(db_session, 9999)
        assert result["lemma"] is None

    def test_returns_expected_keys(self, seeded_session: Session) -> None:
        result = get_lemma_view_data(seeded_session, 1)
        expected_keys = {
            "lemma",
            "translations",
            "definitions",
            "overrides",
            "effective_levels",
            "derivative_forms",
            "grammar_facts",
            "audio_files",
            "sentence_count",
            "needs_disambiguation_check",
            "related_lemmas",
        }
        assert expected_keys.issubset(set(result.keys()))

    def test_translations_include_seed_data(self, seeded_session: Session) -> None:
        result = get_lemma_view_data(seeded_session, 1)
        assert result["translations"]["en"] == "eat"
        assert result["translations"]["fr"] == "manger"
        assert result["translations"]["es"] == "comer"

    def test_effective_levels_include_override(self, seeded_session: Session) -> None:
        result = get_lemma_view_data(seeded_session, 1)
        # zh has an override of 5 (base level is 3)
        assert result["effective_levels"]["zh"] == 5
        # fr has no override so should use base level
        assert result["effective_levels"]["fr"] == 3


class TestBulkGetTranslationsForLemmas:
    """Tests for bulk_get_translations_for_lemmas."""

    def test_empty_list(self, db_session: Session) -> None:
        result = bulk_get_translations_for_lemmas(db_session, [])
        assert result == {}

    def test_returns_translations(self, seeded_session: Session) -> None:
        lemmas = seeded_session.query(Lemma).all()
        result = bulk_get_translations_for_lemmas(seeded_session, lemmas)

        # Each lemma should have an entry
        assert 1 in result
        assert 2 in result

        # Lemma 1 has en (from lemma_text) + fr + es
        assert result[1]["en"] == "eat"
        assert result[1]["fr"] == "manger"
        assert result[1]["es"] == "comer"

        # Lemma 2 has only en
        assert result[2]["en"] == "house"
