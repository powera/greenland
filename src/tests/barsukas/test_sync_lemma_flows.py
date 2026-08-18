"""Functional tests for the lemma sync apply routes, driven through HTTP.

The lemma blueprint had no POST coverage at all, which is how its three paths --
import, export, and per-field reconcile -- drifted apart: fields the changes
page could reconcile were silently dropped on import and on export, and a
DB->release edit could neither move a disambiguation nor clear a field.

Each test here POSTs a real route and then reads back both sides.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest
from flask.testing import FlaskClient
from sqlalchemy.orm import Session

from barsukas.routes.sync import sync_release
from storage.crud.concept import get_qid_for_lemma, link_lemma_to_concept
from storage.models.schema import Lemma


@pytest.fixture()
def lemma_release_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the lemma sync at a scratch release tree."""
    directory = tmp_path / "lemmas"
    directory.mkdir(parents=True)
    monkeypatch.setattr(sync_release, "DEFAULT_RELEASE_DIR", directory)
    yield directory


def _write_base(
    release_dir: Path, pos_dir: str, subtype: str, records: List[Dict[str, Any]]
) -> Path:
    target = release_dir / pos_dir / subtype
    target.mkdir(parents=True, exist_ok=True)
    path = target / "base.jsonl"
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    return path


def _read_base(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    return {
        record["guid"]: record
        for record in (
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }


def _lemma(db_session: Session, guid: str) -> Lemma:
    """Re-read a lemma, discarding whatever this session cached before the POST."""
    db_session.expire_all()
    return db_session.query(Lemma).filter(Lemma.guid == guid).one()


class TestAdditions:
    """Importing a release record the database does not have."""

    def test_import_carries_every_reconcilable_field(
        self, client: FlaskClient, lemma_release_dir: Path, db_session: Session
    ) -> None:
        """notes, emoji, lexical_gap_reason and qid used to be dropped here."""
        _write_base(
            lemma_release_dir,
            "nouns",
            "animal",
            [
                {
                    "guid": "N08_001",
                    "pos_type": "noun",
                    "pos_subtype": "animal",
                    "concept_label": "bat (animal)",
                    "concept_definition": "a flying mammal",
                    "translations": {"en": "bat", "lt": "šikšnosparnis"},
                    "difficulty_level": 4,
                    "notes": "not the cricket kind",
                    "emoji": [{"type": "unicode", "value": "🦇"}],
                    "lexical_gap_reason": "no single-word equivalent",
                    "qid": "Q28425",
                }
            ],
        )

        response = client.post(
            "/sync/lemmas/additions/apply",
            data={"selected_guids": "N08_001"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        imported = _lemma(db_session, "N08_001")
        assert imported.lemma_text == "bat"
        assert imported.disambiguation == "animal"
        assert imported.notes == "not the cricket kind"
        assert imported.lexical_gap_reason == "no single-word equivalent"
        assert json.loads(imported.emoji) == [{"type": "unicode", "value": "🦇"}]
        assert get_qid_for_lemma(db_session, imported.id) == "Q28425"
        assert {t.language_code: t.translation for t in imported.translations} == {
            "lt": "šikšnosparnis"
        }


class TestExportRemovals:
    """Writing a database-only lemma into the release tree."""

    def test_export_carries_notes_and_emoji(
        self, client: FlaskClient, lemma_release_dir: Path, db_session: Session
    ) -> None:
        """The export builder omitted both, so exporting lost them."""
        house = db_session.query(Lemma).filter(Lemma.guid == "N01_001").one()
        house.notes = "dwelling, not household"
        house.emoji = json.dumps([{"type": "unicode", "value": "🏠"}])
        db_session.commit()

        response = client.post(
            "/sync/lemmas/removals/export",
            data={"selected_ids": str(house.id)},
            follow_redirects=True,
        )
        assert response.status_code == 200

        records = _read_base(lemma_release_dir / "nouns" / "building" / "base.jsonl")
        assert records["N01_001"]["notes"] == "dwelling, not household"
        assert records["N01_001"]["emoji"] == [{"type": "unicode", "value": "🏠"}]


class TestChangesUseDb:
    """Pushing the database's version of a base field into the release file."""

    def test_disambiguation_change_rewrites_concept_label(
        self, client: FlaskClient, lemma_release_dir: Path, db_session: Session
    ) -> None:
        """concept_label was never written, so this row could never be resolved."""
        path = _write_base(
            lemma_release_dir,
            "nouns",
            "building",
            [
                {
                    "guid": "N01_001",
                    "pos_type": "noun",
                    "pos_subtype": "building",
                    "concept_label": "house",
                    "concept_definition": "a building for living in",
                    "translations": {"en": "house"},
                    "difficulty_level": 2,
                }
            ],
        )
        house = db_session.query(Lemma).filter(Lemma.guid == "N01_001").one()
        house.disambiguation = "dwelling"
        db_session.commit()

        response = client.post(
            "/sync/lemmas/changes/apply",
            data={f"action_{house.id}": "use_db"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        assert _read_base(path)["N01_001"]["concept_label"] == "house (dwelling)"

        # And the row is now reconciled: it must not still be a difference.
        page = client.get("/sync/lemmas/changes")
        assert "N01_001" not in page.get_data(as_text=True)

    def test_clearing_notes_removes_the_key(
        self, client: FlaskClient, lemma_release_dir: Path, db_session: Session
    ) -> None:
        """An empty DB value used to be skipped, leaving the stale value on disk."""
        path = _write_base(
            lemma_release_dir,
            "nouns",
            "building",
            [
                {
                    "guid": "N01_001",
                    "pos_type": "noun",
                    "pos_subtype": "building",
                    "concept_label": "house",
                    "concept_definition": "a building for living in",
                    "translations": {"en": "house"},
                    "difficulty_level": 2,
                    "notes": "stale note",
                }
            ],
        )
        house = db_session.query(Lemma).filter(Lemma.guid == "N01_001").one()
        house.notes = None
        db_session.commit()

        response = client.post(
            "/sync/lemmas/changes/apply",
            data={f"action_{house.id}": "use_db"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        assert "notes" not in _read_base(path)["N01_001"]

    def test_unpairing_removes_the_qid(
        self, client: FlaskClient, lemma_release_dir: Path, db_session: Session
    ) -> None:
        """The qid path already did this correctly; pin it so the rewrite kept it."""
        path = _write_base(
            lemma_release_dir,
            "nouns",
            "building",
            [
                {
                    "guid": "N01_001",
                    "pos_type": "noun",
                    "pos_subtype": "building",
                    "concept_label": "house",
                    "concept_definition": "a building for living in",
                    "translations": {"en": "house"},
                    "difficulty_level": 2,
                    "qid": "Q3947",
                }
            ],
        )
        house = db_session.query(Lemma).filter(Lemma.guid == "N01_001").one()

        response = client.post(
            "/sync/lemmas/changes/apply",
            data={f"action_{house.id}": "use_db"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        assert "qid" not in _read_base(path)["N01_001"]


class TestChangesUseRelease:
    """Pulling the release file's version into the database."""

    def test_release_values_land_on_the_lemma(
        self, client: FlaskClient, lemma_release_dir: Path, db_session: Session
    ) -> None:
        _write_base(
            lemma_release_dir,
            "nouns",
            "building",
            [
                {
                    "guid": "N01_001",
                    "pos_type": "noun",
                    "pos_subtype": "building",
                    "concept_label": "house (dwelling)",
                    "concept_definition": "a place someone lives",
                    "translations": {"en": "house"},
                    "difficulty_level": 2,
                    "notes": "from release",
                    "emoji": [{"type": "unicode", "value": "🏠"}],
                }
            ],
        )
        house = db_session.query(Lemma).filter(Lemma.guid == "N01_001").one()

        response = client.post(
            "/sync/lemmas/changes/apply",
            data={f"action_{house.id}": "use_release"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        updated = _lemma(db_session, "N01_001")
        assert updated.lemma_text == "house"
        assert updated.disambiguation == "dwelling"
        assert updated.definition_text == "a place someone lives"
        assert updated.notes == "from release"
        assert json.loads(updated.emoji) == [{"type": "unicode", "value": "🏠"}]

    def test_release_clears_a_field_the_database_has(
        self, client: FlaskClient, lemma_release_dir: Path, db_session: Session
    ) -> None:
        _write_base(
            lemma_release_dir,
            "nouns",
            "building",
            [
                {
                    "guid": "N01_001",
                    "pos_type": "noun",
                    "pos_subtype": "building",
                    "concept_label": "house",
                    "concept_definition": "a building for living in",
                    "translations": {"en": "house"},
                    "difficulty_level": 2,
                }
            ],
        )
        house = db_session.query(Lemma).filter(Lemma.guid == "N01_001").one()
        house.notes = "only in the database"
        db_session.commit()

        response = client.post(
            "/sync/lemmas/changes/apply",
            data={f"action_{house.id}": "use_release"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        assert _lemma(db_session, "N01_001").notes is None


class TestReadOnlyGuard:
    """Export routes write files and commit, so they need the guard too."""

    def test_export_removals_refuses_in_readonly_mode(
        self, client: FlaskClient, lemma_release_dir: Path, db_session: Session
    ) -> None:
        house = db_session.query(Lemma).filter(Lemma.guid == "N01_001").one()
        client.application.config["READONLY"] = True
        try:
            response = client.post(
                "/sync/lemmas/removals/export",
                data={"selected_ids": str(house.id)},
                follow_redirects=True,
            )
        finally:
            client.application.config["READONLY"] = False

        assert response.status_code == 200
        assert "read-only" in response.get_data(as_text=True)
        assert not (lemma_release_dir / "nouns" / "building" / "base.jsonl").exists()
