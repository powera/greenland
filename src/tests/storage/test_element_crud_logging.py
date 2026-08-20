"""Tests for operation logging in the phrase, idiom and name CRUD functions.

These are the same opt-in contract the sentence CRUD functions follow (see
:mod:`tests.storage.test_sentence_crud_logging`): passing ``source`` means "log
this", omitting it means "do not". What is specific here is that all three types
have child rows with no GUID of their own -- phrase translations, idiom
equivalents, name renderings -- which are logged against their *parent's* GUID
with ``language_code`` in the fact, so one GUID filter returns the whole story.
"""

from __future__ import annotations

import json
from typing import List

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Import the full model registry so every table the log touches is created.
import storage.models  # noqa: F401
from storage.crud.idiom import (
    add_idiom_equivalent,
    create_idiom,
    delete_idiom,
    delete_idiom_equivalent,
    update_idiom,
    update_idiom_equivalent,
)
from storage.crud.name_entity import (
    create_name,
    delete_name,
    get_or_create_name,
    set_name_translation,
    update_name,
)
from storage.crud.operation_log import (
    IDIOM_CREATE,
    IDIOM_DELETE,
    IDIOM_EQUIVALENT_CREATE,
    IDIOM_EQUIVALENT_DELETE,
    IDIOM_EQUIVALENT_UPDATE,
    IDIOM_UPDATE,
    NAME_CREATE,
    NAME_DELETE,
    NAME_TRANSLATION_CREATE,
    NAME_TRANSLATION_UPDATE,
    NAME_UPDATE,
    PHRASE_CREATE,
    PHRASE_TRANSLATION_CREATE,
    PHRASE_TRANSLATION_UPDATE,
)
from storage.crud.phrase import add_phrase, set_phrase_translation
from storage.models.idiom import Idiom
from storage.models.name_entity import Name
from storage.models.operation_log import OperationLog
from storage.models.schema import Base, Phrase

SOURCE = "test-suite"


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


def _logs(db: Session, operation_type: str) -> List[OperationLog]:
    return (
        db.query(OperationLog)
        .filter(OperationLog.operation_type == operation_type)
        .order_by(OperationLog.id)
        .all()
    )


def _fact(entry: OperationLog) -> dict:
    return json.loads(entry.fact)


def _log_count(db: Session) -> int:
    return db.query(OperationLog).count()


def _an_idiom(db: Session, **kwargs: object) -> Idiom:
    return create_idiom(
        db,
        source_language_code="en",
        expression="kick the bucket",
        meaning="to die",
        **kwargs,  # type: ignore[arg-type]
    )


# ── phrases ────────────────────────────────────────────────────────────────


def test_add_phrase_logs_against_its_guid(session: Session) -> None:
    phrase = add_phrase(session, "greetings", "See you later", source=SOURCE)

    (entry,) = _logs(session, PHRASE_CREATE)
    assert entry.entity_guid == phrase.guid
    assert entry.source == SOURCE
    assert _fact(entry)["entity_kind"] == "phrase"
    assert _fact(entry)["label"] == "See you later"


def test_phrase_translation_logs_against_the_phrase_guid(session: Session) -> None:
    """A translation row has no GUID, so the parent's is the handle."""
    phrase = add_phrase(session, "greetings", "See you later")

    set_phrase_translation(session, phrase, "lt", "Iki pasimatymo", source=SOURCE)

    (entry,) = _logs(session, PHRASE_TRANSLATION_CREATE)
    assert entry.entity_guid == phrase.guid
    assert _fact(entry)["language_code"] == "lt"
    assert _fact(entry)["new_value"] == "Iki pasimatymo"


def test_resetting_a_phrase_translation_logs_the_diff(session: Session) -> None:
    phrase = add_phrase(session, "greetings", "See you later")
    set_phrase_translation(session, phrase, "lt", "Iki")

    set_phrase_translation(session, phrase, "lt", "Iki pasimatymo", source=SOURCE)

    (entry,) = _logs(session, PHRASE_TRANSLATION_UPDATE)
    assert entry.entity_guid == phrase.guid
    (change,) = _fact(entry)["changes"]
    assert change == {
        "field": "translation",
        "old_value": "Iki",
        "new_value": "Iki pasimatymo",
    }


def test_rewriting_a_phrase_translation_unchanged_logs_nothing(session: Session) -> None:
    phrase = add_phrase(session, "greetings", "See you later")
    set_phrase_translation(session, phrase, "lt", "Iki")
    before = _log_count(session)

    set_phrase_translation(session, phrase, "lt", "Iki", source=SOURCE)

    assert _log_count(session) == before


# ── idioms ─────────────────────────────────────────────────────────────────


def test_create_idiom_logs_against_its_guid(session: Session) -> None:
    idiom = _an_idiom(session, source=SOURCE)

    (entry,) = _logs(session, IDIOM_CREATE)
    assert entry.entity_guid == idiom.guid
    assert _fact(entry)["entity_kind"] == "idiom"
    assert _fact(entry)["expression"] == "kick the bucket"


def test_update_idiom_records_only_what_changed(session: Session) -> None:
    idiom = _an_idiom(session, difficulty_level=2)

    update_idiom(session, idiom, meaning="to die", verified=True, source=SOURCE)

    (entry,) = _logs(session, IDIOM_UPDATE)
    # meaning was passed but is unchanged, so only verified is recorded.
    assert _fact(entry)["changed_fields"] == ["verified"]


def test_update_idiom_compares_normalized_text(session: Session) -> None:
    """Whitespace is collapsed on the way in, so this is not an edit."""
    idiom = _an_idiom(session)

    update_idiom(session, idiom, expression="kick  the   bucket", source=SOURCE)

    assert _logs(session, IDIOM_UPDATE) == []


def test_idiom_equivalent_logs_against_the_idiom_guid(session: Session) -> None:
    idiom = _an_idiom(session)

    add_idiom_equivalent(
        session,
        idiom,
        language_code="lt",
        expression="numirti",
        equivalence_kind="idiomatic",
        source=SOURCE,
    )

    (entry,) = _logs(session, IDIOM_EQUIVALENT_CREATE)
    assert entry.entity_guid == idiom.guid
    assert _fact(entry)["language_code"] == "lt"
    assert _fact(entry)["new_value"] == "numirti"


def test_updating_an_equivalent_logs_the_diff(session: Session) -> None:
    idiom = _an_idiom(session)
    equivalent = add_idiom_equivalent(
        session,
        idiom,
        language_code="lt",
        expression="numirti",
        equivalence_kind="idiomatic",
    )

    update_idiom_equivalent(session, equivalent, verified=True, source=SOURCE)

    (entry,) = _logs(session, IDIOM_EQUIVALENT_UPDATE)
    assert entry.entity_guid == idiom.guid
    assert _fact(entry)["language_code"] == "lt"
    assert _fact(entry)["changed_fields"] == ["verified"]


def test_deleting_an_equivalent_logs_before_the_row_goes(session: Session) -> None:
    idiom = _an_idiom(session)
    equivalent = add_idiom_equivalent(
        session,
        idiom,
        language_code="lt",
        expression="numirti",
        equivalence_kind="idiomatic",
    )

    delete_idiom_equivalent(session, equivalent, source=SOURCE)
    session.flush()

    (entry,) = _logs(session, IDIOM_EQUIVALENT_DELETE)
    assert entry.entity_guid == idiom.guid
    # Read while the row was still there; the entry outlives it.
    assert _fact(entry)["old_value"] == "numirti"


def test_delete_idiom_entry_survives_the_idiom(session: Session) -> None:
    idiom = _an_idiom(session)
    add_idiom_equivalent(
        session,
        idiom,
        language_code="lt",
        expression="numirti",
        equivalence_kind="idiomatic",
    )
    guid = idiom.guid

    delete_idiom(session, idiom, source=SOURCE)
    session.flush()

    assert session.query(Idiom).filter(Idiom.guid == guid).first() is None
    (entry,) = _logs(session, IDIOM_DELETE)
    assert entry.entity_guid == guid
    assert _fact(entry)["equivalent_count"] == 1


# ── names ──────────────────────────────────────────────────────────────────


def test_create_name_allocates_a_guid_in_its_kind_namespace(session: Session) -> None:
    """Names used to be created GUID-less, which left them unloggable."""
    given = create_name(session, name_text="George", kind="given_name")
    place = create_name(session, name_text="Vilnius", kind="place")

    assert given.guid.startswith("E01_")
    assert place.guid.startswith("E04_")


def test_create_name_honours_an_explicit_guid(session: Session) -> None:
    """Importers pass the release record's GUID rather than spending a new one."""
    name = create_name(session, name_text="George", kind="given_name", guid="E01_042")

    assert name.guid == "E01_042"
    # The next allocation continues from it rather than colliding.
    assert create_name(session, name_text="Anna", kind="given_name").guid == "E01_043"


def test_create_name_logs_against_its_guid(session: Session) -> None:
    name = create_name(session, name_text="George", kind="given_name", source=SOURCE)

    (entry,) = _logs(session, NAME_CREATE)
    assert entry.entity_guid == name.guid
    assert _fact(entry)["entity_kind"] == "name"
    assert _fact(entry)["name_text"] == "George"


def test_get_or_create_name_logs_only_when_it_creates(session: Session) -> None:
    _, created = get_or_create_name(session, name_text="George", kind="given_name", source=SOURCE)
    assert created
    assert len(_logs(session, NAME_CREATE)) == 1

    _, created_again = get_or_create_name(
        session, name_text="George", kind="given_name", source=SOURCE
    )
    assert not created_again
    # Reusing an existing name is not a write worth an entry.
    assert len(_logs(session, NAME_CREATE)) == 1


def test_update_name_logs_a_cleared_field(session: Session) -> None:
    """None is a real value here, not "leave alone" -- the sentinel is _UNSET."""
    name = create_name(session, name_text="George", kind="given_name", gender="masculine")

    update_name(session, name, gender=None, source=SOURCE)

    (entry,) = _logs(session, NAME_UPDATE)
    (change,) = _fact(entry)["changes"]
    assert change == {"field": "gender", "old_value": "masculine", "new_value": None}


def test_update_name_compares_normalized_values(session: Session) -> None:
    """An empty disambiguation stores as None, so this is not an edit."""
    name = create_name(session, name_text="George", kind="given_name")

    update_name(session, name, disambiguation="", source=SOURCE)

    assert _logs(session, NAME_UPDATE) == []


def test_name_translation_logs_against_the_name_guid(session: Session) -> None:
    name = create_name(session, name_text="George", kind="given_name")

    set_name_translation(session, name, language_code="lt", translation="Džordžas", source=SOURCE)

    (entry,) = _logs(session, NAME_TRANSLATION_CREATE)
    assert entry.entity_guid == name.guid
    assert _fact(entry)["language_code"] == "lt"
    assert _fact(entry)["new_value"] == "Džordžas"


def test_resetting_a_name_rendering_logs_the_diff(session: Session) -> None:
    name = create_name(session, name_text="George", kind="given_name")
    set_name_translation(session, name, language_code="lt", translation="Georgas")

    set_name_translation(session, name, language_code="lt", translation="Džordžas", source=SOURCE)

    (entry,) = _logs(session, NAME_TRANSLATION_UPDATE)
    (change,) = _fact(entry)["changes"]
    assert change == {
        "field": "translation",
        "old_value": "Georgas",
        "new_value": "Džordžas",
    }


def test_delete_name_entry_survives_the_name(session: Session) -> None:
    name = create_name(session, name_text="George", kind="given_name")
    set_name_translation(session, name, language_code="lt", translation="Džordžas")
    guid = name.guid

    delete_name(session, name, source=SOURCE)

    assert session.query(Name).filter(Name.guid == guid).first() is None
    (entry,) = _logs(session, NAME_DELETE)
    assert entry.entity_guid == guid
    assert _fact(entry)["translation_count"] == 1


# ── the opt-in contract ────────────────────────────────────────────────────


def test_nothing_is_logged_without_a_source(session: Session) -> None:
    """Every write below omits source, so the log stays empty."""
    phrase = add_phrase(session, "greetings", "See you later")
    set_phrase_translation(session, phrase, "lt", "Iki")
    set_phrase_translation(session, phrase, "lt", "Iki pasimatymo")

    idiom = _an_idiom(session)
    equivalent = add_idiom_equivalent(
        session,
        idiom,
        language_code="lt",
        expression="numirti",
        equivalence_kind="idiomatic",
    )
    update_idiom(session, idiom, verified=True)
    update_idiom_equivalent(session, equivalent, verified=True)
    delete_idiom_equivalent(session, equivalent)
    delete_idiom(session, idiom)

    name = create_name(session, name_text="George", kind="given_name")
    update_name(session, name, verified=True)
    set_name_translation(session, name, language_code="lt", translation="Džordžas")
    set_name_translation(session, name, language_code="lt", translation="Georgas")
    delete_name(session, name)

    assert _log_count(session) == 0
