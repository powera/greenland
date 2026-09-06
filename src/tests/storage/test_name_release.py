"""Tests for name release-file import/export and name GUID allocation."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.crud.name_entity import (
    assign_name_guid,
    create_name,
    get_name_by_guid,
    name_kind_guid_prefix,
    next_name_guid,
    set_name_translation,
)
from storage.guid_router import guid_kind, resolve_guid
from storage.models.guid_prefixes import NAME_KIND_GUID_PREFIXES
from storage.models.name_entity import NAME_KINDS, Name
from storage.models.schema import Base
from storage.release.name import (
    apply_release_record,
    export_names_to_release,
    import_names_from_release,
    name_to_release_record,
    read_release_records,
    read_release_records_by_guid,
)


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


def _seed_george(db_session: Session) -> Name:
    """Create the running example: a given name with three renderings."""
    name = create_name(
        db_session,
        name_text="George",
        kind="given_name",
        gender="masculine",
        notes="Recurring dialog speaker.",
    )
    name.guid = assign_name_guid(db_session, name)
    set_name_translation(
        db_session,
        name,
        language_code="lt",
        translation="Džordžas",
        ipa_pronunciation="ˈdʒɔrdʒɐs",
        verified=True,
    )
    set_name_translation(
        db_session,
        name,
        language_code="zh",
        translation="乔治",
        sort_key="qiaozhi",
    )
    set_name_translation(db_session, name, language_code="ja", translation="ジョージ")
    db_session.commit()
    return name


# --- GUID allocation -------------------------------------------------------


def test_every_name_kind_has_a_guid_prefix() -> None:
    """A kind without a prefix could not be exported, so none may be missing."""
    assert set(NAME_KIND_GUID_PREFIXES) == set(NAME_KINDS)


def test_name_guid_prefixes_are_unique() -> None:
    prefixes = list(NAME_KIND_GUID_PREFIXES.values())
    assert len(set(prefixes)) == len(prefixes)


def test_first_guid_in_a_kind_starts_at_one(session: Session) -> None:
    prefix = name_kind_guid_prefix("given_name")
    assert next_name_guid(session, "given_name") == f"{prefix}_001"


def test_guids_continue_from_the_highest_in_that_kind(session: Session) -> None:
    """Numbering counts up from MAX, so a gap in the middle stays a gap."""
    prefix = name_kind_guid_prefix("given_name")
    first = create_name(session, name_text="George", kind="given_name")
    first.guid = assign_name_guid(session, first)
    second = create_name(session, name_text="Maria", kind="given_name")
    second.guid = assign_name_guid(session, second)
    third = create_name(session, name_text="Jonas", kind="given_name")
    third.guid = assign_name_guid(session, third)
    session.delete(second)
    session.commit()

    assert (first.guid, third.guid) == (f"{prefix}_001", f"{prefix}_003")
    assert next_name_guid(session, "given_name") == f"{prefix}_004"


def test_kinds_have_independent_numbering(session: Session) -> None:
    given = create_name(session, name_text="George", kind="given_name")
    place = create_name(session, name_text="Maple Street", kind="place")
    assign_name_guid(session, given)
    assign_name_guid(session, place)
    session.commit()

    assert given.guid == f"{name_kind_guid_prefix('given_name')}_001"
    assert place.guid == f"{name_kind_guid_prefix('place')}_001"


def test_assign_name_guid_is_idempotent(session: Session) -> None:
    name = create_name(session, name_text="George", kind="given_name")
    first_guid = assign_name_guid(session, name)
    assert assign_name_guid(session, name) == first_guid


def test_unknown_kind_has_no_prefix() -> None:
    with pytest.raises(ValueError, match="No GUID prefix"):
        name_kind_guid_prefix("not_a_kind")


# --- GUID routing ----------------------------------------------------------


def test_name_guids_route_to_names(session: Session) -> None:
    name = _seed_george(session)
    assert name.guid is not None
    assert guid_kind(name.guid) == "name"

    kind, resolved = resolve_guid(session, name.guid)
    assert kind == "name"
    assert resolved is name


def test_name_guid_routing_does_not_capture_lemma_guids() -> None:
    """The name family must not swallow the lemma namespace."""
    assert guid_kind("N02_001") == "lemma"
    assert guid_kind("M01_001") == "idiom"
    assert guid_kind("S_00001") == "sentence"


def test_get_name_by_guid_returns_none_when_absent(session: Session) -> None:
    assert get_name_by_guid(session, "E01_999") is None


# --- Record shape ----------------------------------------------------------


def test_record_carries_renderings_and_their_metadata(session: Session) -> None:
    name = _seed_george(session)
    record = name_to_release_record(name)

    assert record["guid"] == name.guid
    assert record["kind"] == "given_name"
    assert record["name_text"] == "George"
    assert record["gender"] == "masculine"
    assert record["translations"] == {"lt": "Džordžas", "zh": "乔治", "ja": "ジョージ"}
    assert record["translation_metadata"]["lt"] == {
        "ipa_pronunciation": "ˈdʒɔrdʒɐs",
        "verified": True,
    }
    assert record["translation_metadata"]["zh"] == {"sort_key": "qiaozhi"}
    # A rendering with no extras contributes no metadata entry at all.
    assert "ja" not in record["translation_metadata"]


def test_record_omits_empty_optional_fields(session: Session) -> None:
    name = create_name(session, name_text="Fresh Mart", kind="organization")
    assign_name_guid(session, name)
    session.commit()

    record = name_to_release_record(name)
    for absent_key in ("disambiguation", "gender", "notes", "verified", "translation_metadata"):
        assert absent_key not in record


def test_languages_are_emitted_in_release_order(session: Session) -> None:
    """Byte-stability depends on a fixed language order, not insertion order."""
    name = create_name(session, name_text="George", kind="given_name")
    assign_name_guid(session, name)
    for language_code, rendering in (("ja", "ジョージ"), ("lt", "Džordžas"), ("zh", "乔治")):
        set_name_translation(session, name, language_code=language_code, translation=rendering)
    session.commit()

    record = name_to_release_record(name)
    assert list(record["translations"]) == ["lt", "zh", "ja"]


# --- Round trip ------------------------------------------------------------


def test_export_then_import_preserves_the_name(session: Session, tmp_path: Path) -> None:
    _seed_george(session)
    assert export_names_to_release(session, tmp_path) == 1

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as target:
        imported, skipped = import_names_from_release(target, tmp_path)
        target.commit()

        assert (imported, skipped) == (1, 0)
        name = target.query(Name).one()
        assert name.guid == f"{name_kind_guid_prefix('given_name')}_001"
        assert name.name_text == "George"
        assert name.kind == "given_name"
        assert name.gender == "masculine"
        assert name.notes == "Recurring dialog speaker."

        renderings = {t.language_code: t for t in name.translations}
        assert renderings["lt"].translation == "Džordžas"
        assert renderings["lt"].ipa_pronunciation == "ˈdʒɔrdʒɐs"
        assert renderings["lt"].verified is True
        assert renderings["zh"].sort_key == "qiaozhi"
        assert renderings["ja"].translation == "ジョージ"


def test_export_is_byte_stable(session: Session, tmp_path: Path) -> None:
    _seed_george(session)
    export_names_to_release(session, tmp_path)
    first = (tmp_path / "base.jsonl").read_bytes()
    export_names_to_release(session, tmp_path)
    assert (tmp_path / "base.jsonl").read_bytes() == first


def test_importing_twice_is_a_no_op(session: Session, tmp_path: Path) -> None:
    _seed_george(session)
    export_names_to_release(session, tmp_path)

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as target:
        import_names_from_release(target, tmp_path)
        target.commit()
        assert import_names_from_release(target, tmp_path) == (0, 1)
        assert target.query(Name).count() == 1


def test_names_without_a_guid_are_not_exported(session: Session, tmp_path: Path) -> None:
    """A row with no GUID has no place in the release namespace.

    create_name allocates a GUID now, so the GUID-less row is built directly
    here. Rows predating that change still exist in the database, and the
    export filter that skips them is what this guards.
    """
    _seed_george(session)
    session.add(Name(name_text="Draft Person", kind="given_name", guid=None))
    session.commit()

    assert export_names_to_release(session, tmp_path) == 1
    assert len(read_release_records(tmp_path)) == 1


def test_records_are_sorted_by_guid(session: Session, tmp_path: Path) -> None:
    for name_text in ("Zoe", "Anna", "Mark"):
        name = create_name(session, name_text=name_text, kind="given_name")
        assign_name_guid(session, name)
    session.commit()
    export_names_to_release(session, tmp_path)

    guids = [record["guid"] for record in read_release_records(tmp_path)]
    assert guids == sorted(guids)


def test_reading_an_absent_release_directory_yields_nothing(tmp_path: Path) -> None:
    assert read_release_records(tmp_path / "missing") == []
    assert read_release_records_by_guid(tmp_path / "missing") == {}


def test_unknown_kind_in_a_release_record_is_rejected(session: Session, tmp_path: Path) -> None:
    (tmp_path / "base.jsonl").write_text(
        '{"guid": "E01_001", "kind": "sidekick", "name_text": "George", "translations": {}}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Unknown name kind"):
        import_names_from_release(session, tmp_path)


# --- Reconciling an existing name ------------------------------------------


def test_apply_release_record_overwrites_fields_and_renderings(session: Session) -> None:
    name = _seed_george(session)
    record = {
        "guid": name.guid,
        "kind": "given_name",
        "name_text": "George",
        "gender": "masculine",
        "translations": {"lt": "Georgas", "fr": "Georges"},
        "translation_metadata": {"lt": {"ipa_pronunciation": "ˈɡʲɛɔrɡɐs"}},
    }

    apply_release_record(session, record, name)
    session.commit()

    renderings = {t.language_code: t.translation for t in name.translations}
    assert renderings == {"lt": "Georgas", "fr": "Georges"}
    # Renderings the record does not mention are dropped, not left stale.
    assert "zh" not in renderings
    assert "ja" not in renderings
    lithuanian = next(t for t in name.translations if t.language_code == "lt")
    assert lithuanian.ipa_pronunciation == "ˈɡʲɛɔrɡɐs"
    # The record had no notes, so the note is cleared rather than kept.
    assert name.notes is None


def test_apply_release_record_round_trips_an_unchanged_record(session: Session) -> None:
    """Applying a name's own record back to it must be a no-op."""
    name = _seed_george(session)
    before = name_to_release_record(name)

    apply_release_record(session, before, name)
    session.commit()

    assert name_to_release_record(name) == before


# ── localizations in the release record ──────────────────────────────────────


def test_a_name_without_localizations_emits_the_original_record(session: Session) -> None:
    """The format stays backward compatible: no localization, no new keys."""
    name = _seed_george(session)
    record = name_to_release_record(name)

    assert "localizations" not in record
    assert "localization_metadata" not in record


def test_localizations_emit_in_their_own_block(session: Session) -> None:
    """A localization must not displace the transliteration in ``translations``."""
    name = create_name(session, name_text="John", kind="given_name")
    set_name_translation(session, name, language_code="ru", translation="Джон")
    set_name_translation(
        session,
        name,
        language_code="ru",
        translation="Иван",
        rendering_kind="localization",
    )
    session.commit()

    record = name_to_release_record(name)

    assert record["translations"] == {"ru": "Джон"}
    assert record["localizations"] == {"ru": "Иван"}


def test_release_record_round_trips_both_rendering_kinds(session: Session) -> None:
    """Export -> import must preserve which kind each rendering is."""
    name = create_name(session, name_text="John", kind="given_name")
    set_name_translation(session, name, language_code="ru", translation="Джон")
    set_name_translation(session, name, language_code="lt", translation="Džonas")
    set_name_translation(
        session,
        name,
        language_code="ru",
        translation="Иван",
        rendering_kind="localization",
    )
    session.commit()
    before = name_to_release_record(name)

    apply_release_record(session, before, name)
    session.commit()

    assert name_to_release_record(name) == before
    by_kind = {(t.language_code, t.rendering_kind): t.translation for t in name.translations}
    assert by_kind == {
        ("ru", "transliteration"): "Джон",
        ("ru", "localization"): "Иван",
        ("lt", "transliteration"): "Džonas",
    }


def test_apply_release_record_prunes_per_kind(session: Session) -> None:
    """A record listing only transliterations drops the localization it omits."""
    name = create_name(session, name_text="John", kind="given_name")
    set_name_translation(session, name, language_code="ru", translation="Джон")
    set_name_translation(
        session,
        name,
        language_code="ru",
        translation="Иван",
        rendering_kind="localization",
    )
    session.commit()

    apply_release_record(
        session,
        {
            "guid": name.guid,
            "kind": "given_name",
            "name_text": "John",
            "translations": {"ru": "Джон"},
        },
        name,
    )
    session.commit()

    by_kind = {(t.language_code, t.rendering_kind): t.translation for t in name.translations}
    assert by_kind == {("ru", "transliteration"): "Джон"}
