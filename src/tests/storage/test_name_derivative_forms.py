"""Tests for a name's forms: creation, lookup by form, and the token views that see them."""

from __future__ import annotations

from typing import Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Import the full model registry so every table is created.
import storage.models  # noqa: F401
from storage.crud.name_entity import (
    NAME_EN_BASE_FORM,
    NAME_EN_POSSESSIVE_FORM,
    attach_name_forms,
    create_name,
    delete_name,
    find_name_by_form,
)
from storage.crud.operation_log import NAME_DERIVATIVE_FORM_CREATE
from storage.models.name_entity import NameDerivativeForm
from storage.models.operation_log import OperationLog
from storage.models.schema import Base, WordToken
from storage.word_token_view import (
    ATTACHMENT_NAME,
    get_word_token_view,
    unlinked_word_tokens,
)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _add_token(session: Session, token: str, frequency_rank: Optional[int] = None) -> WordToken:
    row = WordToken(token=token, language_code="en", frequency_rank=frequency_rank)
    session.add(row)
    session.flush()
    return row


def _forms(session: Session) -> dict[str, str]:
    return {
        form.grammatical_form: form.derivative_form_text
        for form in session.query(NameDerivativeForm).all()
    }


def test_create_name_writes_base_and_possessive(session: Session) -> None:
    name = create_name(session, name_text="John", kind="given_name")

    assert _forms(session) == {NAME_EN_BASE_FORM: "John", NAME_EN_POSSESSIVE_FORM: "John's"}
    base = [form for form in name.derivative_forms if form.is_base_form]
    assert [form.derivative_form_text for form in base] == ["John"]


def test_sibilant_name_takes_apostrophe_s(session: Session) -> None:
    create_name(session, name_text="James", kind="given_name")
    assert _forms(session)[NAME_EN_POSSESSIVE_FORM] == "James's"


def test_attach_name_forms_is_idempotent(session: Session) -> None:
    name = create_name(session, name_text="Mary", kind="given_name")
    attach_name_forms(session, name)
    attach_name_forms(session, name)
    assert session.query(NameDerivativeForm).count() == 2


def test_forms_link_to_existing_tokens_at_creation(session: Session) -> None:
    john = _add_token(session, "John", 1399)
    possessive = _add_token(session, "John's", 9000)
    _add_token(session, "john", 17784)

    create_name(session, name_text="John", kind="given_name")

    linked = {
        form.derivative_form_text: form.word_token_id
        for form in session.query(NameDerivativeForm).all()
    }
    assert linked == {"John": john.id, "John's": possessive.id}


def test_form_creation_is_logged_against_the_name_guid(session: Session) -> None:
    name = create_name(session, name_text="William", kind="given_name", source="test/create")

    entries = (
        session.query(OperationLog)
        .filter(OperationLog.operation_type == NAME_DERIVATIVE_FORM_CREATE)
        .all()
    )
    assert len(entries) == 2
    assert {entry.entity_guid for entry in entries} == {name.guid}


def test_find_name_by_form_matches_the_possessive_case_sensitively(session: Session) -> None:
    name = create_name(session, name_text="John", kind="given_name")

    assert find_name_by_form(session, "John") is name
    assert find_name_by_form(session, "John's") is name
    assert find_name_by_form(session, "john") is None
    assert find_name_by_form(session, "john's") is None
    assert find_name_by_form(session, "  ") is None


def test_deleting_a_name_removes_its_forms(session: Session) -> None:
    name = create_name(session, name_text="John", kind="given_name")
    delete_name(session, name)
    session.flush()
    assert session.query(NameDerivativeForm).count() == 0


def test_name_token_leaves_the_unlinked_list(session: Session) -> None:
    _add_token(session, "John", 1399)
    _add_token(session, "john", 17784)
    _add_token(session, "zebra", 2000)

    before = [row.token for row in unlinked_word_tokens(session, "en")]
    assert "John" in before

    create_name(session, name_text="John", kind="given_name")

    after = [row.token for row in unlinked_word_tokens(session, "en")]
    assert "John" not in after
    # The lowercase token is a different string, and the name does not claim it.
    assert "john" in after
    assert "zebra" in after


def test_token_view_lists_the_name_without_a_share(session: Session) -> None:
    token = _add_token(session, "John", 1399)
    name = create_name(session, name_text="John", kind="given_name")

    view = get_word_token_view(session, token.id)

    assert view is not None
    assert len(view.attachments) == 1
    attachment = view.attachments[0]
    assert attachment.attachment_kind == ATTACHMENT_NAME
    assert attachment.element_type == "name"
    assert attachment.name_id == name.id
    assert attachment.lemma_id is None
    assert attachment.guid == name.guid
    assert attachment.share is None
    assert view.lemma_ids == []
    assert not view.is_homograph
