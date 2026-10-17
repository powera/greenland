"""Tests for storage.token_forms: the registry of tables that can claim a WordToken."""

from __future__ import annotations

from typing import Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Import the full model registry so every table is created.
import storage.models  # noqa: F401
from storage.crud.name_entity import create_name
from storage.elements.interfaces import ElementRef
from storage.models.name_entity import NameDerivativeForm
from storage.models.schema import Base, DerivativeForm, Lemma, WordToken
from storage.models.variant_form import VARIANT_KIND_SPELLING, VariantForm
from storage.token_forms import (
    TOKEN_FORM_SOURCES,
    WordTokenResolver,
    claimed_word_token_ids,
    link_unlinked_forms,
    source_for_form,
)

# SurfaceForm's members (storage.elements.interfaces). Protocols with
# properties are not runtime-checkable against ORM classes, so check names.
SURFACE_FORM_MEMBERS = (
    "id",
    "word_token_id",
    "language_code",
    "grammatical_form",
    "is_base_form",
    "surface_text",
    "owner",
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


def _add_lemma(session: Session, text: str) -> Lemma:
    lemma = Lemma(lemma_text=text, definition_text=f"definition of {text}", pos_type="noun")
    session.add(lemma)
    session.flush()
    return lemma


def test_every_source_model_has_the_surface_form_members() -> None:
    for source in TOKEN_FORM_SOURCES:
        missing = [name for name in SURFACE_FORM_MEMBERS if not hasattr(source.model, name)]
        assert missing == [], f"{source.table_name} lacks {missing}"


def test_sources_cover_the_three_form_tables() -> None:
    assert {source.table_name for source in TOKEN_FORM_SOURCES} == {
        "derivative_forms",
        "variant_forms",
        "name_derivative_forms",
    }


def test_owner_refs_name_the_owning_element(session: Session) -> None:
    lemma = _add_lemma(session, "gray")
    form = DerivativeForm(
        lemma_id=lemma.id,
        derivative_form_text="gray",
        language_code="en",
        grammatical_form="adjective/en_positive",
    )
    variant = VariantForm(
        lemma_id=lemma.id,
        variant_form_text="grey",
        language_code="en",
        grammatical_form="adjective/en_positive",
        variant_kind=VARIANT_KIND_SPELLING,
        variant_key="grey",
    )
    session.add_all([form, variant])
    session.flush()
    name = create_name(session, name_text="John", kind="given_name")

    assert form.owner == ElementRef("lemma", lemma.id)
    assert variant.owner == ElementRef("lemma", lemma.id)
    assert variant.surface_text == "grey"
    assert name.derivative_forms[0].owner == ElementRef("name", name.id)
    assert source_for_form(name.derivative_forms[0]).element_type == "name"


def test_claimed_ids_union_all_three_sources(session: Session) -> None:
    lemma_token = _add_token(session, "tops", 10)
    variant_token = _add_token(session, "grey", 20)
    name_token = _add_token(session, "John", 30)
    unclaimed = _add_token(session, "zebra", 40)
    lemma = _add_lemma(session, "top")
    session.add(
        DerivativeForm(
            lemma_id=lemma.id,
            derivative_form_text="tops",
            language_code="en",
            grammatical_form="noun/en_plural",
            word_token_id=lemma_token.id,
        )
    )
    session.add(
        VariantForm(
            lemma_id=lemma.id,
            variant_form_text="grey",
            language_code="en",
            grammatical_form="adjective/en_positive",
            variant_kind=VARIANT_KIND_SPELLING,
            variant_key="grey",
            word_token_id=variant_token.id,
        )
    )
    create_name(session, name_text="John", kind="given_name")

    claimed = {row[0] for row in claimed_word_token_ids(session).all()}

    assert {lemma_token.id, variant_token.id, name_token.id} <= claimed
    assert unclaimed.id not in claimed


def test_resolver_prefers_exact_case_then_best_ranked_case_variant(session: Session) -> None:
    exact = _add_token(session, "March", 900)
    lower = _add_token(session, "march", 100)
    resolver = WordTokenResolver.for_language(session, "en")

    assert resolver.resolve("March") == exact.id
    assert resolver.resolve("MARCH") == lower.id
    assert resolver.resolve("MARCH", exact_case_only=True) is None


def test_bulk_link_keeps_names_to_exact_case(session: Session) -> None:
    # A name created before its token existed: nothing to link at creation.
    name = create_name(session, name_text="Mark", kind="given_name")
    assert all(form.word_token_id is None for form in name.derivative_forms)

    _add_token(session, "mark", 500)
    counts = link_unlinked_forms(session, "en")
    assert counts["name_derivative_forms"] == 0

    capitalized = _add_token(session, "Mark", 800)
    counts = link_unlinked_forms(session, "en")
    assert counts["name_derivative_forms"] == 1
    base = next(form for form in name.derivative_forms if form.is_base_form)
    assert base.word_token_id == capitalized.id

    # Idempotent: a second pass touches nothing.
    assert link_unlinked_forms(session, "en")["name_derivative_forms"] == 0


def test_name_forms_are_a_table_of_their_own(session: Session) -> None:
    create_name(session, name_text="John", kind="given_name")
    assert session.query(DerivativeForm).count() == 0
    assert session.query(NameDerivativeForm).count() == 2
