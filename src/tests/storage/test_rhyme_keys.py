"""Tests for storage-level rhyme-key synchronization."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models.schema import Base, DerivativeForm, Lemma
from storage.rhyme_keys import compute_rhyme_key_from_ipa


def test_compute_rhyme_key_from_ipa_supports_enabled_languages() -> None:
    """Enabled languages should map IPA to stored rhyme keys."""
    assert compute_rhyme_key_from_ipa("/kæt/", "en") == "æt"
    assert compute_rhyme_key_from_ipa("/kanˈsjon/", "es") == "on"
    assert compute_rhyme_key_from_ipa("/ʃɑ̃te/", "fr") == "e"
    assert compute_rhyme_key_from_ipa("/kɐlˈba/", "lt") == "a"


def test_compute_rhyme_key_from_ipa_returns_none_for_unsupported_languages() -> None:
    """Unsupported languages or empty IPA should not produce rhyme keys."""
    assert compute_rhyme_key_from_ipa("/kæt/", "de") is None
    assert compute_rhyme_key_from_ipa(None, "en") is None


def test_derivative_form_rhyme_key_is_set_on_insert_and_update() -> None:
    """ORM saves should keep rhyme_key synchronized with IPA changes."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    try:
        lemma = Lemma(
            lemma_text="cat",
            definition_text="a feline",
            pos_type="noun",
            guid="N00_010",
        )
        session.add(lemma)
        session.flush()

        derivative_form = DerivativeForm(
            lemma_id=lemma.id,
            derivative_form_text="cat",
            language_code="en",
            grammatical_form="singular",
            is_base_form=True,
            ipa_pronunciation="/kæt/",
        )
        session.add(derivative_form)
        session.commit()

        assert derivative_form.rhyme_key == "æt"

        derivative_form.language_code = "es"
        derivative_form.ipa_pronunciation = "/kanˈsjon/"
        session.commit()

        assert derivative_form.rhyme_key == "on"

        derivative_form.language_code = "de"
        session.commit()

        assert derivative_form.rhyme_key is None
    finally:
        session.close()
        engine.dispose()


def test_derivative_form_single_word_future_still_gets_rhyme_key() -> None:
    """Single-token future forms should still be rhyme-indexed."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    try:
        lemma = Lemma(
            lemma_text="read",
            definition_text="to interpret written text",
            pos_type="verb",
            guid="V00_010",
        )
        session.add(lemma)
        session.flush()

        derivative_form = DerivativeForm(
            lemma_id=lemma.id,
            derivative_form_text="shallread",
            language_code="en",
            grammatical_form="verb/en_1s_future",
            is_base_form=False,
            ipa_pronunciation="/ʃælɹiːd/",
        )
        session.add(derivative_form)
        session.commit()

        assert derivative_form.rhyme_key is not None
    finally:
        session.close()
        engine.dispose()


def test_derivative_form_multi_word_future_keeps_ipa_but_skips_rhyme_key() -> None:
    """Periphrastic future forms should preserve IPA while leaving rhyme_key empty."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    try:
        lemma = Lemma(
            lemma_text="read",
            definition_text="to interpret written text",
            pos_type="verb",
            guid="V00_011",
        )
        session.add(lemma)
        session.flush()

        derivative_form = DerivativeForm(
            lemma_id=lemma.id,
            derivative_form_text="will read",
            language_code="en",
            grammatical_form="verb/en_1s_future",
            is_base_form=False,
            ipa_pronunciation="/wɪl ɹiːd/",
        )
        session.add(derivative_form)
        session.commit()

        assert derivative_form.ipa_pronunciation == "/wɪl ɹiːd/"
        assert derivative_form.rhyme_key is None
    finally:
        session.close()
        engine.dispose()
