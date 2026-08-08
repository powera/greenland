"""Tests for idiom release-file import/export."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.crud.idiom import add_idiom_equivalent, create_idiom
from storage.models.idiom import Idiom
from storage.models.schema import Base
from storage.release.idiom import (
    export_idioms_to_release,
    import_idioms_from_release,
    read_release_records,
)


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


def _seed(session: Session) -> None:
    idiom = create_idiom(
        session,
        source_language_code="en",
        expression="throw in the towel",
        meaning="to admit defeat and stop trying",
        register="informal",
    )
    add_idiom_equivalent(
        session,
        idiom,
        language_code="fr",
        expression="jeter l'éponge",
        equivalence_kind="idiomatic",
        literal_gloss="to throw the sponge",
    )
    add_idiom_equivalent(
        session,
        idiom,
        language_code="lt",
        expression="pasiduoti",
        equivalence_kind="paraphrase",
    )
    session.commit()


def test_export_then_import_preserves_the_idiom(session: Session, tmp_path: Path) -> None:
    _seed(session)
    assert export_idioms_to_release(session, tmp_path) == 1

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as target:
        imported, skipped = import_idioms_from_release(target, tmp_path)
        target.commit()

        assert (imported, skipped) == (1, 0)
        idiom = target.query(Idiom).one()
        assert idiom.guid == "M01_001"
        assert idiom.source_language_code == "en"
        assert idiom.expression == "throw in the towel"
        assert idiom.register == "informal"
        assert {
            (equivalent.language_code, equivalent.expression, equivalent.equivalence_kind)
            for equivalent in idiom.equivalents
        } == {
            ("fr", "jeter l'éponge", "idiomatic"),
            ("lt", "pasiduoti", "paraphrase"),
        }


def test_export_is_byte_stable_across_a_roundtrip(session: Session, tmp_path: Path) -> None:
    """Re-exporting reimported data must not churn the release file."""
    _seed(session)
    first_dir = tmp_path / "first"
    export_idioms_to_release(session, first_dir)
    original = (first_dir / "base.jsonl").read_text(encoding="utf-8")

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as target:
        import_idioms_from_release(target, first_dir)
        target.commit()
        second_dir = tmp_path / "second"
        export_idioms_to_release(target, second_dir)

    assert (second_dir / "base.jsonl").read_text(encoding="utf-8") == original


def test_equivalents_are_arrays_even_for_a_single_value(session: Session, tmp_path: Path) -> None:
    """Consumers must never have to branch on cardinality."""
    _seed(session)
    export_idioms_to_release(session, tmp_path)

    record = read_release_records(tmp_path)[0]

    assert isinstance(record["equivalents"]["fr"], list)
    assert len(record["equivalents"]["fr"]) == 1


def test_unassessed_language_is_absent_rather_than_empty(session: Session, tmp_path: Path) -> None:
    """A missing key means "not assessed"; an empty array would claim otherwise."""
    _seed(session)
    export_idioms_to_release(session, tmp_path)

    record = read_release_records(tmp_path)[0]

    assert "de" not in record["equivalents"]


def test_importing_the_same_file_twice_skips_existing_guids(
    session: Session, tmp_path: Path
) -> None:
    _seed(session)
    export_idioms_to_release(session, tmp_path)

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as target:
        import_idioms_from_release(target, tmp_path)
        target.commit()
        imported, skipped = import_idioms_from_release(target, tmp_path)
        target.commit()

        assert (imported, skipped) == (0, 1)
        assert target.query(Idiom).count() == 1


def test_importing_a_missing_release_dir_is_a_no_op(session: Session, tmp_path: Path) -> None:
    assert import_idioms_from_release(session, tmp_path / "absent") == (0, 0)
