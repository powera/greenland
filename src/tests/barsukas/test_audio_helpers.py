"""Tests for barsukas.helpers.audio_helpers."""

import pytest
from sqlalchemy.orm import Session

from barsukas.helpers.audio_helpers import (
    link_audio_to_lemma,
    validate_audio_translation,
)
from wordfreq.storage.models.schema import Lemma, LemmaTranslation


class TestLinkAudioToLemma:
    """Tests for link_audio_to_lemma."""

    def test_matches_by_guid(self, seeded_session: Session) -> None:
        result = link_audio_to_lemma(seeded_session, "V01_001", "anything", "en")
        assert result == 1

    def test_falls_back_to_column_translation_match(self, db_session: Session) -> None:
        """When GUID doesn't match, fall back to column-based text lookup."""
        lemma = Lemma(
            lemma_text="dog",
            definition_text="a pet",
            pos_type="noun",
            chinese_translation="狗",
            confidence=0.0,
        )
        db_session.add(lemma)
        db_session.flush()

        result = link_audio_to_lemma(db_session, "NONEXISTENT", "狗", "zh")
        assert result == lemma.id

    def test_falls_back_to_table_translation_match(self, db_session: Session) -> None:
        """Table-based languages (es, de, pt) use LemmaTranslation table."""
        lemma = Lemma(
            lemma_text="cat",
            definition_text="a pet",
            pos_type="noun",
            confidence=0.0,
        )
        db_session.add(lemma)
        db_session.flush()

        t = LemmaTranslation(lemma_id=lemma.id, language_code="es", translation="gato")
        db_session.add(t)
        db_session.flush()

        result = link_audio_to_lemma(db_session, "NONEXISTENT", "gato", "es")
        assert result == lemma.id

    def test_returns_none_when_no_match(self, db_session: Session) -> None:
        result = link_audio_to_lemma(db_session, "NOPE", "nope", "en")
        assert result is None

    def test_returns_none_for_unknown_language(self, db_session: Session) -> None:
        result = link_audio_to_lemma(db_session, "NOPE", "text", "xx")
        assert result is None


class TestValidateAudioTranslation:
    """Tests for validate_audio_translation."""

    def test_valid_column_translation(self, db_session: Session) -> None:
        lemma = Lemma(
            lemma_text="water",
            definition_text="H2O",
            pos_type="noun",
            guid="N99_001",
            french_translation="eau",
            confidence=0.0,
        )
        db_session.add(lemma)
        db_session.flush()

        result = validate_audio_translation(db_session, "N99_001", "eau", "fr")
        assert result["valid"] is True
        assert result["mismatch"] is False
        assert result["lemma_found"] is True
        assert result["current_translation"] == "eau"

    def test_mismatched_translation(self, db_session: Session) -> None:
        lemma = Lemma(
            lemma_text="water",
            definition_text="H2O",
            pos_type="noun",
            guid="N99_002",
            french_translation="eau",
            confidence=0.0,
        )
        db_session.add(lemma)
        db_session.flush()

        result = validate_audio_translation(db_session, "N99_002", "wrong", "fr")
        assert result["valid"] is False
        assert result["mismatch"] is True
        assert result["current_translation"] == "eau"

    def test_lemma_not_found(self, db_session: Session) -> None:
        result = validate_audio_translation(db_session, "MISSING", "text", "fr")
        assert result["valid"] is False
        assert result["lemma_found"] is False

    def test_no_translation_for_language(self, db_session: Session) -> None:
        lemma = Lemma(
            lemma_text="water",
            definition_text="H2O",
            pos_type="noun",
            guid="N99_003",
            confidence=0.0,
        )
        db_session.add(lemma)
        db_session.flush()

        result = validate_audio_translation(db_session, "N99_003", "eau", "fr")
        assert result["valid"] is False
        assert result["mismatch"] is False
        assert result["lemma_found"] is True
        assert result["current_translation"] is None

    def test_table_based_translation_valid(self, db_session: Session) -> None:
        lemma = Lemma(
            lemma_text="water",
            definition_text="H2O",
            pos_type="noun",
            guid="N99_004",
            confidence=0.0,
        )
        db_session.add(lemma)
        db_session.flush()

        t = LemmaTranslation(lemma_id=lemma.id, language_code="es", translation="agua")
        db_session.add(t)
        db_session.flush()

        result = validate_audio_translation(db_session, "N99_004", "agua", "es")
        assert result["valid"] is True
        assert result["current_translation"] == "agua"
