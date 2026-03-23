"""Tests for storage-level rhyme-key synchronization."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models.schema import Base, DerivativeForm, Lemma
from storage.rhyme_keys import compute_rhyme_key_from_ipa


def test_compute_rhyme_key_from_ipa_only_applies_to_english() -> None:
    """Only English IPA should produce a stored rhyme key."""
    assert compute_rhyme_key_from_ipa("/kæt/", "en") == "æt"
    assert compute_rhyme_key_from_ipa("/kæt/", "fr") is None
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

        derivative_form.ipa_pronunciation = "/dɔɡ/"
        session.commit()

        assert derivative_form.rhyme_key == "ɔɡ"

        derivative_form.language_code = "fr"
        session.commit()

        assert derivative_form.rhyme_key is None
    finally:
        session.close()
        engine.dispose()
