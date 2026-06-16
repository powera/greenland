"""Tests for the Lexeme facade over DerivativeForm."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.lexeme import (
    Lexeme,
    get_candidate_lexemes_for_form,
    get_lexeme,
    get_lexeme_for_synonym,
    list_lexemes_for_lemma,
)
from storage.models.schema import (
    SYNONYM_GRAMMATICAL_FORMS,
    Base,
    DerivativeForm,
    Lemma,
)


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _add_lemma(session: Session, text: str, guid: str, pos_type: str = "noun") -> Lemma:
    lemma = Lemma(lemma_text=text, definition_text=text, pos_type=pos_type, guid=guid)
    session.add(lemma)
    session.flush()
    return lemma


def _add_form(
    session: Session,
    lemma: Lemma,
    text: str,
    grammatical_form: str,
    language_code: str = "en",
    is_base_form: bool = False,
) -> DerivativeForm:
    form = DerivativeForm(
        lemma_id=lemma.id,
        derivative_form_text=text,
        language_code=language_code,
        grammatical_form=grammatical_form,
        is_base_form=is_base_form,
    )
    session.add(form)
    session.flush()
    return form


def test_synonym_can_attach_to_multiple_lemmas() -> None:
    """The same synonym surface string may own to more than one lemma."""
    session = _make_session()
    try:
        hat = _add_lemma(session, "hat", "N01_001")
        cap = _add_lemma(session, "cap", "N01_002")

        _add_form(session, hat, "beanie", "synonym")
        _add_form(session, cap, "beanie", "synonym")
        session.commit()

        rows = (
            session.query(DerivativeForm)
            .filter(
                DerivativeForm.derivative_form_text == "beanie",
                DerivativeForm.grammatical_form == "synonym",
            )
            .all()
        )
        assert len(rows) == 2
    finally:
        session.close()


def test_synonym_can_recur_across_synonym_subtypes() -> None:
    """A synonym string may repeat across synonym sub-types for one lemma."""
    session = _make_session()
    try:
        big = _add_lemma(session, "big", "A01_001")

        _add_form(session, big, "ample", "synonym")
        _add_form(session, big, "ample", "synonym_near")
        _add_form(session, big, "ample", "synonym_regional")
        session.commit()

        rows = (
            session.query(DerivativeForm)
            .filter(DerivativeForm.derivative_form_text == "ample")
            .all()
        )
        assert len(rows) == 3
    finally:
        session.close()


def test_homograph_base_forms_are_allowed() -> None:
    """Two distinct lemmas can share a base-form text in the same language."""
    session = _make_session()
    try:
        bank_river = _add_lemma(session, "bank", "N02_001")
        bank_finance = _add_lemma(session, "bank", "N03_001")

        _add_form(session, bank_river, "bank", "singular", is_base_form=True)
        _add_form(session, bank_finance, "bank", "singular", is_base_form=True)
        session.commit()

        rows = (
            session.query(DerivativeForm)
            .filter(DerivativeForm.derivative_form_text == "bank")
            .all()
        )
        assert len(rows) == 2
    finally:
        session.close()


def test_get_lexeme_for_synonym_returns_unique_owner() -> None:
    session = _make_session()
    try:
        hat = _add_lemma(session, "hat", "N01_001")
        _add_form(session, hat, "hat", "singular", is_base_form=True)
        _add_form(session, hat, "beanie", "synonym")
        session.commit()

        lexeme = get_lexeme_for_synonym(session, "beanie", "en")
        assert lexeme is not None
        assert lexeme.lemma.id == hat.id
        assert any(f.derivative_form_text == "beanie" for f in lexeme.synonyms)
        assert lexeme.base_form is not None
        assert lexeme.base_form.derivative_form_text == "hat"
    finally:
        session.close()


def test_get_lexeme_for_synonym_returns_none_when_missing() -> None:
    session = _make_session()
    try:
        assert get_lexeme_for_synonym(session, "nope", "en") is None
    finally:
        session.close()


def test_get_candidate_lexemes_for_homograph_returns_both() -> None:
    session = _make_session()
    try:
        bank_river = _add_lemma(session, "bank", "N02_001")
        bank_finance = _add_lemma(session, "bank", "N03_001")
        _add_form(session, bank_river, "bank", "singular", is_base_form=True)
        _add_form(session, bank_finance, "bank", "singular", is_base_form=True)
        session.commit()

        lexemes = get_candidate_lexemes_for_form(session, "bank", "en")
        lemma_ids = sorted(lex.lemma.id for lex in lexemes)
        assert lemma_ids == sorted([bank_river.id, bank_finance.id])
    finally:
        session.close()


def test_list_lexemes_for_lemma_groups_by_language() -> None:
    session = _make_session()
    try:
        cat = _add_lemma(session, "cat", "N00_010")
        _add_form(session, cat, "cat", "singular", language_code="en", is_base_form=True)
        _add_form(session, cat, "cats", "plural", language_code="en")
        _add_form(session, cat, "katė", "singular", language_code="lt", is_base_form=True)
        session.commit()

        lexemes = list_lexemes_for_lemma(session, cat.id)
        by_lang = {lex.language_code: lex for lex in lexemes}
        assert set(by_lang.keys()) == {"en", "lt"}
        assert len(by_lang["en"].forms) == 2
        assert len(by_lang["lt"].forms) == 1
    finally:
        session.close()


def test_lexeme_inflections_excludes_synonyms_and_abbreviations() -> None:
    session = _make_session()
    try:
        run = _add_lemma(session, "run", "V01_001", pos_type="verb")
        _add_form(session, run, "run", "infinitive", is_base_form=True)
        _add_form(session, run, "ran", "past_tense")
        _add_form(session, run, "jog", "synonym")
        _add_form(session, run, "rn", "abbreviation")
        session.commit()

        lexeme = get_lexeme(session, run.id, "en")
        assert lexeme is not None
        inflection_texts = {f.derivative_form_text for f in lexeme.inflections}
        assert inflection_texts == {"run", "ran"}
        assert {f.derivative_form_text for f in lexeme.synonyms} == {"jog"}
    finally:
        session.close()


def test_synonym_grammatical_forms_constant_is_complete() -> None:
    """The constant must list every synonym subtype the index covers."""
    expected = {
        "synonym",
        "synonym_near",
        "synonym_regional",
        "synonym_register",
        "synonym_synecdoche",
        "synonym_related",
        "synonym_spelling",
    }
    assert set(SYNONYM_GRAMMATICAL_FORMS) == expected
