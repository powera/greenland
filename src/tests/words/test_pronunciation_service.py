"""Tests for pronunciation coverage selection."""

from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.backend.config import BackendType, DataSourceConfig
from storage.models.schema import Base, DerivativeForm, Lemma, LemmaTranslation
from words.pronunciation import PronunciationService


def _build_config() -> DataSourceConfig:
    """Create a minimal pronunciation-service config for tests."""
    return DataSourceConfig(
        backend_type=BackendType.SQLITE,
        sqlite_path=":memory:",
        model="gpt-5-mini",
    )


def test_check_missing_pronunciations_counts_partially_missing_forms() -> None:
    """Coverage mode should include forms missing either IPA or phonetic data."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    try:
        lemma = Lemma(
            lemma_text="eat",
            definition_text="to consume food",
            pos_type="verb",
            guid="V00_001",
        )
        session.add(lemma)
        session.flush()

        session.add_all(
            [
                DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text="eat",
                    language_code="en",
                    grammatical_form="infinitive",
                    is_base_form=True,
                    ipa_pronunciation="/iːt/",
                    phonetic_pronunciation=None,
                ),
                DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text="eats",
                    language_code="en",
                    grammatical_form="third_person_singular_present",
                    is_base_form=False,
                    ipa_pronunciation=None,
                    phonetic_pronunciation="EETS",
                ),
                DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text="ate",
                    language_code="en",
                    grammatical_form="past_tense",
                    is_base_form=False,
                    ipa_pronunciation="/eɪt/",
                    phonetic_pronunciation="AYT",
                ),
            ]
        )
        session.commit()

        agent = PronunciationService(config=_build_config())
        with patch.object(agent, "get_session", return_value=session):
            result = agent.check_missing_pronunciations(lemma_id=lemma.id)

        assert result["total_missing"] == 2
        assert {item["word"] for item in result["missing_forms"]} == {"eat", "eats"}
    finally:
        session.close()
        engine.dispose()


def test_check_missing_pronunciations_includes_lemma_translation_targets() -> None:
    """Coverage mode should include lemma translations with missing pronunciation data."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    try:
        lemma = Lemma(
            lemma_text="dog",
            definition_text="a domesticated canine",
            pos_type="noun",
            guid="N00_003",
        )
        session.add(lemma)
        session.flush()
        session.add(
            LemmaTranslation(
                lemma_id=lemma.id,
                language_code="es",
                translation="perro",
                ipa_pronunciation=None,
                phonetic_pronunciation=None,
            )
        )
        session.commit()

        agent = PronunciationService(config=_build_config())
        with patch.object(agent, "get_session", return_value=session):
            result = agent.check_missing_pronunciations(lemma_id=lemma.id, only_english=False)

        assert result["total_missing"] == 1
        assert result["missing_forms"][0]["target_type"] == "lemma_translation"
        assert result["missing_forms"][0]["word"] == "perro"
    finally:
        session.close()
        engine.dispose()
