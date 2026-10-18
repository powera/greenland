"""Tests for the form/word-token integrity check across every form table."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# Import the full model registry so every table is created.
import storage.models  # noqa: F401
from storage.crud.name_entity import create_name
from storage.integrity.derivative_forms import check_derivative_form_word_tokens
from storage.models.name_entity import NameDerivativeForm
from storage.models.schema import Base, DerivativeForm, Lemma, WordToken


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _add_token(session: Session, token: str) -> WordToken:
    row = WordToken(token=token, language_code="en")
    session.add(row)
    session.flush()
    return row


def _add_form(session: Session, text: str, token: WordToken) -> DerivativeForm:
    lemma = Lemma(lemma_text=text, definition_text=text, pos_type="noun", guid=f"N01_{text}")
    session.add(lemma)
    session.flush()
    form = DerivativeForm(
        lemma_id=lemma.id,
        derivative_form_text=text,
        word_token_id=token.id,
        language_code="en",
        grammatical_form="noun/en_singular",
        is_base_form=True,
    )
    session.add(form)
    session.flush()
    return form


def test_name_form_on_the_wrong_token_is_reported(session: Session) -> None:
    forsaken = _add_token(session, "forsaken")
    create_name(session, name_text="John", kind="given_name")
    base = session.query(NameDerivativeForm).filter_by(derivative_form_text="John").one()
    base.word_token_id = forsaken.id
    session.flush()

    result = check_derivative_form_word_tokens(session)

    assert result["issue_count"] == 1
    issue = result["issues"][0]
    assert issue["table"] == "name_derivative_forms"
    assert issue["element_type"] == "name"
    assert issue["issues"][0].startswith("text_mismatch")


def test_name_form_on_a_differently_cased_token_is_reported(session: Session) -> None:
    lower = _add_token(session, "mark")
    create_name(session, name_text="Mark", kind="given_name")
    base = session.query(NameDerivativeForm).filter_by(derivative_form_text="Mark").one()
    base.word_token_id = lower.id
    session.flush()

    assert check_derivative_form_word_tokens(session)["issue_count"] == 1


def test_lemma_form_lowercase_fallback_is_not_reported(session: Session) -> None:
    capitalized = _add_token(session, "Journalist")
    _add_form(session, "journalist", capitalized)

    assert check_derivative_form_word_tokens(session)["issue_count"] == 0


def test_lemma_form_on_a_missing_token_is_reported(session: Session) -> None:
    gone = _add_token(session, "cat")
    _add_form(session, "cat", gone)
    # A bulk delete, as the old hard clear did: the ORM would null the link itself.
    # Foreign keys off explicitly, since another test module turns them on globally.
    session.commit()
    session.execute(text("PRAGMA foreign_keys=OFF"))
    session.query(WordToken).filter(WordToken.id == gone.id).delete(synchronize_session=False)
    session.expire_all()

    result = check_derivative_form_word_tokens(session)
    assert result["issue_count"] == 1
    assert result["issues"][0]["issues"][0].startswith("invalid_word_token_id")
