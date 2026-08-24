"""Tests for pronunciation generation and persistence behavior."""

from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from langtools.form_registry import FORM_SPECS
from storage.backend.config import BackendType, DataSourceConfig
from storage.models.schema import Base, DerivativeForm, Lemma, LemmaTranslation
from words.pronunciation_generation import generate_pronunciations_for_lemma


def _build_config() -> DataSourceConfig:
    """Create a minimal pronunciation-service config for tests."""
    return DataSourceConfig(
        backend_type=BackendType.SQLITE,
        sqlite_path=":memory:",
        model="gpt-5-mini",
    )


def test_generate_pronunciations_for_lemma_updates_lemma_translation() -> None:
    """Generating pronunciation data should also fill lemma translation pronunciation fields."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    try:
        lemma = Lemma(
            lemma_text="dog",
            definition_text="a domesticated canine",
            pos_type="noun",
            guid="N00_004",
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

        with patch(
            "words.pronunciation_generation.generate_pronunciation_for_form",
            return_value=(True, "/ˈpero/", "PEH-roh"),
        ):
            generated_count, errors = generate_pronunciations_for_lemma(
                session=session,
                lemma=lemma,
                lang_code="es",
                config=_build_config(),
            )

        translation_row = (
            session.query(LemmaTranslation)
            .filter(LemmaTranslation.lemma_id == lemma.id, LemmaTranslation.language_code == "es")
            .first()
        )
        assert generated_count == 1
        assert errors == []
        assert translation_row is not None
        assert translation_row.ipa_pronunciation == "/ˈpero/"
        assert translation_row.phonetic_pronunciation == "PEH-roh"
    finally:
        session.close()
        engine.dispose()


def test_generate_pronunciations_for_lemma_reuses_existing_base_form_pronunciations() -> None:
    """Translation pronunciation backfill should reuse an already-populated base form."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    try:
        lemma = Lemma(
            lemma_text="eat",
            definition_text="to consume food",
            pos_type="verb",
            guid="V00_005",
        )
        session.add(lemma)
        session.flush()
        session.add(
            LemmaTranslation(
                lemma_id=lemma.id,
                language_code="es",
                translation="comer",
                ipa_pronunciation=None,
                phonetic_pronunciation=None,
            )
        )
        session.add(
            DerivativeForm(
                lemma_id=lemma.id,
                derivative_form_text="comer",
                language_code="es",
                grammatical_form="infinitive",
                is_base_form=True,
                ipa_pronunciation="/koˈmeɾ/",
                phonetic_pronunciation="koh-MEHR",
            )
        )
        session.commit()

        with patch(
            "words.pronunciation_generation.generate_pronunciation_for_form"
        ) as mocked_generate:
            generated_count, errors = generate_pronunciations_for_lemma(
                session=session,
                lemma=lemma,
                lang_code="es",
                config=_build_config(),
            )

        translation_row = (
            session.query(LemmaTranslation)
            .filter(LemmaTranslation.lemma_id == lemma.id, LemmaTranslation.language_code == "es")
            .first()
        )
        assert generated_count == 1
        assert errors == []
        assert translation_row is not None
        assert translation_row.ipa_pronunciation == "/koˈmeɾ/"
        assert translation_row.phonetic_pronunciation == "koh-MEHR"
        mocked_generate.assert_not_called()
    finally:
        session.close()
        engine.dispose()


def test_generate_pronunciations_for_lemma_updates_rhyme_key_for_english_forms() -> None:
    """English pronunciation generation should keep the derivative rhyme key in sync."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    try:
        lemma = Lemma(
            lemma_text="cat",
            definition_text="a feline",
            pos_type="noun",
            guid="N00_006",
        )
        session.add(lemma)
        session.flush()
        session.add(
            DerivativeForm(
                lemma_id=lemma.id,
                derivative_form_text="cat",
                language_code="en",
                grammatical_form="singular",
                is_base_form=True,
                ipa_pronunciation=None,
                phonetic_pronunciation=None,
            )
        )
        session.commit()

        with patch(
            "words.pronunciation_generation.generate_pronunciation_for_form",
            return_value=(True, "/kæt/", "KAT"),
        ):
            generated_count, errors = generate_pronunciations_for_lemma(
                session=session,
                lemma=lemma,
                lang_code="en",
                config=_build_config(),
            )
            session.commit()

        refreshed_form = (
            session.query(DerivativeForm).filter(DerivativeForm.lemma_id == lemma.id).one()
        )
        assert generated_count == 1
        assert errors == []
        assert refreshed_form.ipa_pronunciation == "/kæt/"
        assert refreshed_form.rhyme_key == "æt"
    finally:
        session.close()
        engine.dispose()


def test_generate_pronunciations_for_lemma_creates_english_base_form_when_missing() -> None:
    """Lemma-only English entries should still get a stored base-form pronunciation."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    try:
        lemma = Lemma(
            lemma_text="quickly",
            definition_text="at a fast speed",
            pos_type="adverb",
            guid="D00_007",
        )
        session.add(lemma)
        session.commit()

        with patch(
            "words.pronunciation_generation.generate_pronunciation_for_form",
            return_value=(True, "/ˈkwɪkli/", "KWIK-lee"),
        ):
            generated_count, errors = generate_pronunciations_for_lemma(
                session=session,
                lemma=lemma,
                lang_code="en",
                config=_build_config(),
            )
            session.commit()

        generated_form = (
            session.query(DerivativeForm)
            .filter(DerivativeForm.lemma_id == lemma.id, DerivativeForm.language_code == "en")
            .one()
        )
        assert generated_count == 1
        assert errors == []
        assert generated_form.derivative_form_text == "quickly"
        assert (
            generated_form.grammatical_form
            == FORM_SPECS[("en", "adverb")].form_mapping["positive"].value
        )
        assert generated_form.is_base_form is True
        assert generated_form.ipa_pronunciation == "/ˈkwɪkli/"
        assert generated_form.phonetic_pronunciation == "KWIK-lee"
    finally:
        session.close()
        engine.dispose()


def test_generate_pronunciations_for_lemma_skips_english_future_by_default() -> None:
    """Default pronunciation generation should skip optional English *_future forms."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    try:
        lemma = Lemma(
            lemma_text="walk",
            definition_text="to move on foot",
            pos_type="verb",
            guid="V00_008",
        )
        session.add(lemma)
        session.flush()
        session.add_all(
            [
                DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text="walk",
                    language_code="en",
                    grammatical_form="infinitive",
                    is_base_form=True,
                    ipa_pronunciation=None,
                    phonetic_pronunciation=None,
                ),
                DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text="will walk",
                    language_code="en",
                    grammatical_form="1s_future",
                    is_base_form=False,
                    ipa_pronunciation=None,
                    phonetic_pronunciation=None,
                ),
            ]
        )
        session.commit()

        with patch(
            "words.pronunciation_generation.generate_pronunciation_for_form",
            return_value=(True, "/wɔk/", "WAWK"),
        ) as mocked_generate:
            generated_count, errors = generate_pronunciations_for_lemma(
                session=session,
                lemma=lemma,
                lang_code="en",
                config=_build_config(),
            )
            session.commit()

        refreshed_forms = (
            session.query(DerivativeForm)
            .filter(DerivativeForm.lemma_id == lemma.id)
            .order_by(DerivativeForm.id)
            .all()
        )
        assert generated_count == 1
        assert errors == []
        assert mocked_generate.call_count == 1
        assert refreshed_forms[0].ipa_pronunciation == "/wɔk/"
        assert refreshed_forms[1].ipa_pronunciation is None
    finally:
        session.close()
        engine.dispose()


def test_generate_pronunciations_for_lemma_includes_english_future_with_override() -> None:
    """Override mode should include optional English *_future forms."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    try:
        lemma = Lemma(
            lemma_text="walk",
            definition_text="to move on foot",
            pos_type="verb",
            guid="V00_009",
        )
        session.add(lemma)
        session.flush()
        session.add_all(
            [
                DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text="walk",
                    language_code="en",
                    grammatical_form="infinitive",
                    is_base_form=True,
                    ipa_pronunciation=None,
                    phonetic_pronunciation=None,
                ),
                DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text="will walk",
                    language_code="en",
                    grammatical_form="1s_future",
                    is_base_form=False,
                    ipa_pronunciation=None,
                    phonetic_pronunciation=None,
                ),
            ]
        )
        session.commit()

        with patch(
            "words.pronunciation_generation.generate_pronunciation_for_form",
            return_value=(True, "/wɔk/", "WAWK"),
        ) as mocked_generate:
            generated_count, errors = generate_pronunciations_for_lemma(
                session=session,
                lemma=lemma,
                lang_code="en",
                config=_build_config(),
                all_forms_pronunciation=True,
            )
            session.commit()

        refreshed_forms = (
            session.query(DerivativeForm)
            .filter(DerivativeForm.lemma_id == lemma.id)
            .order_by(DerivativeForm.id)
            .all()
        )
        assert generated_count == 2
        assert errors == []
        assert mocked_generate.call_count == 2
        assert refreshed_forms[0].ipa_pronunciation == "/wɔk/"
        assert refreshed_forms[1].ipa_pronunciation == "/wɔk/"
    finally:
        session.close()
        engine.dispose()


def test_generate_pronunciations_base_forms_only_skips_other_forms() -> None:
    """Base-form-only generation should leave non-base forms untouched."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    try:
        lemma = Lemma(
            lemma_text="run",
            definition_text="to move quickly",
            pos_type="verb",
            guid="V00_011",
        )
        session.add(lemma)
        session.flush()
        base_form = DerivativeForm(
            lemma_id=lemma.id,
            derivative_form_text="run",
            language_code="en",
            grammatical_form="infinitive",
            is_base_form=True,
        )
        other_form = DerivativeForm(
            lemma_id=lemma.id,
            derivative_form_text="runs",
            language_code="en",
            grammatical_form="third_person_singular_present",
            is_base_form=False,
        )
        session.add_all([base_form, other_form])
        session.commit()

        with patch(
            "words.pronunciation_generation.generate_pronunciation_for_form",
            return_value=(True, "/rʌn/", "RUN"),
        ) as mocked_generate:
            generated_count, errors = generate_pronunciations_for_lemma(
                session,
                lemma,
                language_code="en",
                base_forms_only=True,
            )

        assert generated_count == 1
        assert errors == []
        mocked_generate.assert_called_once()
        assert base_form.ipa_pronunciation == "/rʌn/"
        assert other_form.ipa_pronunciation is None
    finally:
        session.close()
        engine.dispose()
