"""Functional tests for the whole-record sync engine, driven through HTTP.

These POST to the real routes and then read the release file (or the database)
back, so they cover the part a smoke test cannot: that choosing a side actually
moves the data, in the direction chosen, and without disturbing its neighbours.

Names are used as the worked example; idioms share every line of this engine.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest
from flask.testing import FlaskClient
from sqlalchemy.orm import Session

from barsukas.routes.sync import sync_name_release
from storage.crud.name_entity import assign_name_guid, create_name, set_name_translation
from storage.models.name_entity import Name


@pytest.fixture()
def release_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the name sync at a scratch release directory for the test."""
    directory = tmp_path / "names"
    directory.mkdir(parents=True)
    monkeypatch.setattr(sync_name_release, "DEFAULT_NAME_RELEASE_DIR", directory)
    yield directory


def _write_records(release_dir: Path, records: List[Dict[str, Any]]) -> None:
    (release_dir / "base.jsonl").write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _read_records(release_dir: Path) -> Dict[str, Dict[str, Any]]:
    release_file = release_dir / "base.jsonl"
    if not release_file.exists():
        return {}
    return {
        record["guid"]: record
        for record in (
            json.loads(line)
            for line in release_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }


def _seed_george(db_session: Session) -> int:
    """Add George to the database and return his row id."""
    name = create_name(db_session, name_text="George", kind="given_name", gender="masculine")
    assign_name_guid(db_session, name)
    set_name_translation(db_session, name, language_code="lt", translation="Džordžas")
    db_session.commit()
    return int(name.id)


def _names(db_session: Session) -> List[Name]:
    """Re-read every name, discarding anything this session already cached.

    The route wrote through its own session, so this one has to be expired
    before it will see the change rather than replay its identity map.
    """
    db_session.expire_all()
    return list(db_session.query(Name).order_by(Name.id).all())


def _renderings(name: Name) -> Dict[str, str]:
    return {row.language_code: row.translation for row in name.translations}


class TestAdditions:
    """Release records the database does not have."""

    def test_import_creates_the_name(
        self, client: FlaskClient, release_dir: Path, db_session: Session
    ) -> None:
        _write_records(
            release_dir,
            [
                {
                    "guid": "P01_001",
                    "kind": "given_name",
                    "name_text": "Maria",
                    "translations": {"lt": "Marija"},
                }
            ],
        )

        response = client.post(
            "/sync/names/additions/apply",
            data={"selected_guids": "P01_001"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        (name,) = _names(db_session)
        assert name.name_text == "Maria"
        assert _renderings(name) == {"lt": "Marija"}

    def test_import_all_covers_rows_beyond_the_page(
        self, client: FlaskClient, release_dir: Path, db_session: Session
    ) -> None:
        _write_records(
            release_dir,
            [
                {
                    "guid": f"P01_{index:03d}",
                    "kind": "given_name",
                    "name_text": f"Person {index}",
                    "translations": {},
                }
                for index in range(1, 6)
            ],
        )

        client.post(
            "/sync/names/additions/apply",
            data={"select_scope": "all"},
            follow_redirects=True,
        )

        assert len(_names(db_session)) == 5

    def test_importing_an_already_present_guid_is_skipped(
        self, client: FlaskClient, release_dir: Path, db_session: Session
    ) -> None:
        """A stale list is not an error; it just has nothing left to do."""
        _seed_george(db_session)
        _write_records(
            release_dir,
            [
                {
                    "guid": "P01_001",
                    "kind": "given_name",
                    "name_text": "George",
                    "translations": {},
                }
            ],
        )

        client.post(
            "/sync/names/additions/apply",
            data={"selected_guids": "P01_001"},
            follow_redirects=True,
        )

        assert len(_names(db_session)) == 1


class TestRemovals:
    """Database rows the release file does not have."""

    def test_export_writes_the_name_into_the_release_file(
        self, client: FlaskClient, release_dir: Path, db_session: Session
    ) -> None:
        row_id = _seed_george(db_session)

        client.post(
            "/sync/names/removals/export",
            data={"selected_ids": str(row_id)},
            follow_redirects=True,
        )

        records = _read_records(release_dir)
        assert records["P01_001"]["name_text"] == "George"
        assert records["P01_001"]["translations"] == {"lt": "Džordžas"}

    def test_export_keeps_unrelated_release_records(
        self, client: FlaskClient, release_dir: Path, db_session: Session
    ) -> None:
        """A partial export must not drop the records it was not asked about."""
        _write_records(
            release_dir,
            [
                {
                    "guid": "P04_001",
                    "kind": "place",
                    "name_text": "Maple Street",
                    "translations": {},
                }
            ],
        )
        row_id = _seed_george(db_session)

        client.post(
            "/sync/names/removals/export",
            data={"selected_ids": str(row_id)},
            follow_redirects=True,
        )

        assert set(_read_records(release_dir)) == {"P01_001", "P04_001"}

    def test_export_all_covers_rows_beyond_the_page(
        self, client: FlaskClient, release_dir: Path, db_session: Session
    ) -> None:
        for name_text in ("George", "Maria", "Jonas"):
            name = create_name(db_session, name_text=name_text, kind="given_name")
            assign_name_guid(db_session, name)
        db_session.commit()

        client.post(
            "/sync/names/removals/export",
            data={"select_scope": "all"},
            follow_redirects=True,
        )

        assert len(_read_records(release_dir)) == 3

    def test_delete_removes_the_row(
        self, client: FlaskClient, release_dir: Path, db_session: Session
    ) -> None:
        row_id = _seed_george(db_session)

        client.post(
            "/sync/names/removals/delete",
            data={"selected_ids": str(row_id)},
            follow_redirects=True,
        )

        assert _names(db_session) == []

    def test_delete_offers_no_whole_list_scope(
        self, client: FlaskClient, release_dir: Path, db_session: Session
    ) -> None:
        """A select_scope=all on the delete route must not widen the deletion."""
        _seed_george(db_session)

        client.post(
            "/sync/names/removals/delete",
            data={"select_scope": "all"},
            follow_redirects=True,
        )

        assert len(_names(db_session)) == 1


class TestChanges:
    """GUIDs on both sides whose records differ."""

    def test_use_release_overwrites_the_database(
        self, client: FlaskClient, release_dir: Path, db_session: Session
    ) -> None:
        row_id = _seed_george(db_session)
        _write_records(
            release_dir,
            [
                {
                    "guid": "P01_001",
                    "kind": "given_name",
                    "name_text": "George",
                    "gender": "masculine",
                    "translations": {"lt": "Georgas", "zh": "乔治"},
                }
            ],
        )

        client.post(
            "/sync/names/changes/apply",
            data={f"action_{row_id}": "use_release"},
            follow_redirects=True,
        )

        (name,) = _names(db_session)
        assert _renderings(name) == {"lt": "Georgas", "zh": "乔治"}

    def test_use_db_overwrites_the_release_file(
        self, client: FlaskClient, release_dir: Path, db_session: Session
    ) -> None:
        row_id = _seed_george(db_session)
        _write_records(
            release_dir,
            [
                {
                    "guid": "P01_001",
                    "kind": "given_name",
                    "name_text": "George",
                    "translations": {"lt": "STALE"},
                }
            ],
        )

        client.post(
            "/sync/names/changes/apply",
            data={f"action_{row_id}": "use_db"},
            follow_redirects=True,
        )

        assert _read_records(release_dir)["P01_001"]["translations"] == {"lt": "Džordžas"}

    def test_skip_changes_neither_side(
        self, client: FlaskClient, release_dir: Path, db_session: Session
    ) -> None:
        row_id = _seed_george(db_session)
        _write_records(
            release_dir,
            [
                {
                    "guid": "P01_001",
                    "kind": "given_name",
                    "name_text": "George",
                    "translations": {"lt": "STALE"},
                }
            ],
        )

        client.post(
            "/sync/names/changes/apply",
            data={f"action_{row_id}": "skip"},
            follow_redirects=True,
        )

        assert _read_records(release_dir)["P01_001"]["translations"] == {"lt": "STALE"}
        (name,) = _names(db_session)
        assert _renderings(name) == {"lt": "Džordžas"}

    def test_bulk_apply_with_a_matching_count_is_accepted(
        self, client: FlaskClient, release_dir: Path, db_session: Session
    ) -> None:
        _seed_george(db_session)
        _write_records(
            release_dir,
            [
                {
                    "guid": "P01_001",
                    "kind": "given_name",
                    "name_text": "George",
                    "translations": {"lt": "STALE"},
                }
            ],
        )

        client.post(
            "/sync/names/changes/apply",
            data={"bulk_action": "use_db", "bulk_expected_count": "1"},
            follow_redirects=True,
        )

        assert _read_records(release_dir)["P01_001"]["translations"] == {"lt": "Džordžas"}

    def test_bulk_apply_with_a_stale_count_changes_nothing(
        self, client: FlaskClient, release_dir: Path, db_session: Session
    ) -> None:
        _seed_george(db_session)
        _write_records(
            release_dir,
            [
                {
                    "guid": "P01_001",
                    "kind": "given_name",
                    "name_text": "George",
                    "translations": {"lt": "STALE"},
                }
            ],
        )

        client.post(
            "/sync/names/changes/apply",
            data={"bulk_action": "use_db", "bulk_expected_count": "42"},
            follow_redirects=True,
        )

        assert _read_records(release_dir)["P01_001"]["translations"] == {"lt": "STALE"}


class TestExportAll:
    """The index page's whole-file export."""

    def test_export_all_rewrites_the_file_from_the_database(
        self, client: FlaskClient, release_dir: Path, db_session: Session
    ) -> None:
        _write_records(
            release_dir,
            [{"guid": "P08_001", "kind": "other", "name_text": "Gone", "translations": {}}],
        )
        _seed_george(db_session)

        client.post("/sync/names/export", follow_redirects=True)

        records = _read_records(release_dir)
        assert set(records) == {"P01_001"}
        assert records["P01_001"]["name_text"] == "George"
