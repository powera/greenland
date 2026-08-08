"""Tests for idiom storage, CRUD, GUID routing, and Element interfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from storage.backend.config import BackendType, DataSourceConfig
from storage.crud.idiom import (
    add_idiom_equivalent,
    create_idiom,
    delete_idiom,
    delete_idiom_equivalent,
    get_idiom_by_guid,
    get_idiom_by_id,
    next_idiom_guid,
    update_idiom,
    update_idiom_equivalent,
)
from storage.elements.interfaces import (
    Element,
    GuidElement,
    LanguageValueElement,
    LeveledElement,
    MultiwordElement,
    VerifiableElement,
)
from storage.guid_router import guid_kind, resolve_guid
from storage.migrations.add_idioms import create_idiom_tables
from storage.models.guid_prefixes import IDIOM_GUID_PREFIX
from storage.models.idiom import Idiom, IdiomEquivalent
from storage.models.schema import Base


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


def _accept_element(element: Element) -> str:
    return element.display_text


def _accept_multiword(element: MultiwordElement) -> str:
    return element.expression_text


def _accept_guid(element: GuidElement) -> str | None:
    return element.guid


def _accept_verifiable(element: VerifiableElement) -> bool:
    return element.verified


def _accept_leveled(element: LeveledElement) -> int | None:
    return element.level


def _accept_language_values(element: LanguageValueElement) -> int:
    return len(element.language_values)


def test_create_idiom_assigns_guid_and_element_views(session: Session) -> None:
    idiom = create_idiom(
        session,
        source_language_code="en",
        expression="  kick   the bucket ",
        meaning=" to die ",
        difficulty_level=4,
        verified=True,
    )

    assert idiom.guid == "M01_001"
    assert idiom.source_language_code == "en"
    assert idiom.expression == "kick the bucket"
    assert idiom.meaning == "to die"
    assert idiom.element_type == "idiom"
    assert _accept_element(idiom) == "kick the bucket"
    assert _accept_multiword(idiom) == "kick the bucket"
    assert _accept_guid(idiom) == "M01_001"
    assert _accept_verifiable(idiom) is True
    assert _accept_leveled(idiom) == 4
    assert _accept_language_values(idiom) == 0


def test_idiom_is_not_declared_as_a_word_element() -> None:
    """Document the intended static boundary without runtime protocol tricks."""
    assert "word_text" not in Idiom.__dict__


def test_next_guid_increments_and_router_resolves_idiom(session: Session) -> None:
    first = create_idiom(
        session,
        source_language_code="en",
        expression="break the ice",
        meaning="make social interaction easier",
    )
    second = create_idiom(
        session,
        source_language_code="lt",
        expression="kabinti makaronus",
        meaning="tell someone implausible stories",
    )

    assert first.guid == "M01_001"
    assert second.guid == "M01_002"
    assert next_idiom_guid(session) == "M01_003"
    assert guid_kind("M01_002") == "idiom"
    assert resolve_guid(session, "M01_002") == ("idiom", second)
    assert resolve_guid(session, "M01_999") == ("idiom", None)


def test_guid_kind_routes_the_whole_idiom_prefix_family() -> None:
    """A future second idiom prefix must route without changing the classifier.

    Idioms are deliberately unsubtyped today, so only ``M01`` is allocated. The
    router matches ``M`` + digits so allocating ``M02`` later does not strand
    those GUIDs as lemmas.
    """
    assert guid_kind(f"{IDIOM_GUID_PREFIX}_001") == "idiom"
    assert guid_kind("M02_001") == "idiom"
    assert guid_kind("M99_123") == "idiom"


def test_guid_kind_does_not_over_match_the_idiom_family() -> None:
    """Non-idiom GUIDs that merely start with "M" stay in their own namespace."""
    # No digits after the family letter, so not an idiom prefix.
    assert guid_kind("MISC_001") == "lemma"
    # A bare family letter has no number at all.
    assert guid_kind("M_001") == "lemma"
    # No separator at all.
    assert guid_kind("M01001") == "lemma"
    # Other namespaces are unaffected by the family match.
    assert guid_kind("N02_001") == "lemma"
    assert guid_kind("F01_001") == "phrase"
    assert guid_kind("S_00001") == "sentence"


def test_multiple_equivalents_are_allowed_in_one_language(session: Session) -> None:
    idiom = create_idiom(
        session,
        source_language_code="en",
        expression="when pigs fly",
        meaning="something will never happen",
    )
    natural = add_idiom_equivalent(
        session,
        idiom,
        language_code="lt",
        expression="kai kiaulės pradės skraidyti",
        equivalence_kind="idiomatic",
        literal_gloss="when pigs begin to fly",
        register="informal",
        verified=True,
    )
    alternative = add_idiom_equivalent(
        session,
        idiom,
        language_code="lt",
        expression="kai vėžys ant kalno sušvilps",
        equivalence_kind="near_equivalent",
        usage_note="traditional expression",
    )

    assert natural.id != alternative.id
    assert len(idiom.equivalents) == 2
    values = idiom.language_values
    assert [value.language_code for value in values] == ["lt", "lt"]
    assert [value.value_kind for value in values] == ["idiomatic", "near_equivalent"]
    assert values[0].text == "kai kiaulės pradės skraidyti"
    assert values[0].status == "informal"
    assert values[1].status_note == "traditional expression"


def test_duplicate_equivalent_is_rejected(session: Session) -> None:
    idiom = create_idiom(
        session,
        source_language_code="en",
        expression="spill the beans",
        meaning="reveal a secret",
    )
    add_idiom_equivalent(
        session,
        idiom,
        language_code="lt",
        expression="išplepėti paslaptį",
        equivalence_kind="paraphrase",
    )

    with pytest.raises(IntegrityError):
        add_idiom_equivalent(
            session,
            idiom,
            language_code="lt",
            expression="išplepėti paslaptį",
            equivalence_kind="near_equivalent",
        )


def test_language_and_equivalence_kind_are_validated(session: Session) -> None:
    with pytest.raises(ValueError, match="Unsupported language code"):
        create_idiom(
            session,
            source_language_code="xx",
            expression="test idiom",
            meaning="test meaning",
        )

    idiom = create_idiom(
        session,
        source_language_code="en",
        expression="under the weather",
        meaning="feeling ill",
    )
    with pytest.raises(ValueError, match="Unknown idiom equivalence kind"):
        add_idiom_equivalent(
            session,
            idiom,
            language_code="lt",
            expression="prastai jaustis",
            equivalence_kind="literal_translation",
        )


def test_empty_expression_and_meaning_are_rejected(session: Session) -> None:
    with pytest.raises(ValueError, match="expression must be non-empty"):
        create_idiom(
            session,
            source_language_code="en",
            expression="  ",
            meaning="a meaning",
        )
    with pytest.raises(ValueError, match="meaning must be non-empty"):
        create_idiom(
            session,
            source_language_code="en",
            expression="an expression",
            meaning="  ",
        )


def test_lookup_eager_loads_equivalents(session: Session) -> None:
    idiom = create_idiom(
        session,
        source_language_code="en",
        expression="piece of cake",
        meaning="very easy",
    )
    add_idiom_equivalent(
        session,
        idiom,
        language_code="lt",
        expression="vienas juokas",
        equivalence_kind="idiomatic",
    )
    session.commit()
    session.expire_all()

    by_id = get_idiom_by_id(session, idiom.id)
    by_guid = get_idiom_by_guid(session, "M01_001")
    assert by_id is not None
    assert by_guid is not None
    assert by_id.equivalents[0].expression == "vienas juokas"
    assert by_guid.id == by_id.id


def test_update_helpers_change_fields_without_committing(session: Session) -> None:
    idiom = create_idiom(
        session,
        source_language_code="en",
        expression="pull someone's leg",
        meaning="joke with someone",
    )
    equivalent = add_idiom_equivalent(
        session,
        idiom,
        language_code="lt",
        expression="traukti per dantį",
        equivalence_kind="near_equivalent",
    )
    session.commit()

    update_idiom(
        session,
        idiom,
        meaning="tease or joke with someone",
        difficulty_level=3,
        verified=True,
    )
    update_idiom_equivalent(
        session,
        equivalent,
        equivalence_kind="idiomatic",
        usage_note="natural conversational equivalent",
        verified=True,
    )

    assert idiom.meaning == "tease or joke with someone"
    assert idiom.difficulty_level == 3
    assert idiom.verified is True
    assert equivalent.equivalence_kind == "idiomatic"
    assert equivalent.usage_note == "natural conversational equivalent"
    assert equivalent.verified is True
    assert session.in_transaction()


def test_delete_equivalent_and_idiom_are_transaction_neutral(session: Session) -> None:
    idiom = create_idiom(
        session,
        source_language_code="en",
        expression="cost an arm and a leg",
        meaning="be very expensive",
    )
    equivalent = add_idiom_equivalent(
        session,
        idiom,
        language_code="lt",
        expression="kainuoti velniškus pinigus",
        equivalence_kind="near_equivalent",
    )
    session.commit()

    delete_idiom_equivalent(session, equivalent)
    assert equivalent in session.deleted
    session.rollback()

    delete_idiom(session, idiom)
    assert idiom in session.deleted
    session.rollback()
    assert get_idiom_by_id(session, idiom.id) is not None


def test_deleting_idiom_cascades_to_equivalents(session: Session) -> None:
    idiom = create_idiom(
        session,
        source_language_code="en",
        expression="hit the nail on the head",
        meaning="identify something exactly",
    )
    add_idiom_equivalent(
        session,
        idiom,
        language_code="lt",
        expression="pataikyti tiesiai į dešimtuką",
        equivalence_kind="near_equivalent",
    )
    session.commit()

    delete_idiom(session, idiom)
    session.commit()

    assert session.query(Idiom).count() == 0
    assert session.query(IdiomEquivalent).count() == 0


def test_migration_is_idempotent_and_supports_dry_run(tmp_path: Path) -> None:
    database_path = tmp_path / "idioms.sqlite"
    config = DataSourceConfig(
        backend_type=BackendType.SQLITE,
        sqlite_path=str(database_path),
    )

    assert create_idiom_tables(config, dry_run=True) is True
    engine = create_engine(f"sqlite:///{database_path}")
    assert inspect(engine).has_table("idioms") is False

    assert create_idiom_tables(config) is True
    inspector = inspect(engine)
    assert inspector.has_table("idioms") is True
    assert inspector.has_table("idiom_equivalents") is True
    assert create_idiom_tables(config) is False
