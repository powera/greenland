"""The /sync/variants flows: import, export, and reconcile a variant paradigm.

Variants were the one per-language array with no sync page, so the only way to
move one into ``data/release`` was a whole-tree re-export. These tests drive the
page against a temporary release tree and check what lands on both sides.

The nesting is what makes this its own engine: a diff is keyed on
``(kind, key, grammatical_form)``, so two variants of one lemma reconcile
independently.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy.orm import sessionmaker

from storage.models.schema import Lemma
from storage.models.variant_form import VariantForm

GUID = "J01_001"  # "gray", from the shared conftest seed


def _write_release(release_dir: Path, variants: List[Dict[str, Any]]) -> Path:
    """Write a minimal release tree holding one lemma's variants array."""
    category = release_dir / "adjectives" / "color"
    category.mkdir(parents=True, exist_ok=True)
    (category / "base.jsonl").write_text(
        json.dumps({"guid": GUID, "concept_label": "gray"}) + "\n", encoding="utf-8"
    )
    line: Dict[str, Any] = {"guid": GUID}
    if variants:
        line["variants"] = variants
    (category / "en.jsonl").write_text(
        json.dumps(line, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return category / "en.jsonl"


@pytest.fixture()
def release_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the blueprint at a scratch release tree instead of the repository."""
    from barsukas.routes.sync import sync_variant_release

    target = tmp_path / "release_lemmas"
    target.mkdir()
    monkeypatch.setattr(sync_variant_release, "DEFAULT_RELEASE_DIR", target)
    yield target


def _read_variants(lang_file: Path) -> List[Dict[str, Any]]:
    for line in lang_file.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            if record.get("guid") == GUID:
                return list(record.get("variants") or [])
    return []


def _db_variant_texts(db_engine: Any) -> Dict[str, str]:
    session = sessionmaker(bind=db_engine)()
    try:
        rows = (
            session.query(VariantForm)
            .join(Lemma, VariantForm.lemma_id == Lemma.id)
            .filter(Lemma.guid == GUID)
            .all()
        )
        return {row.grammatical_form: row.variant_form_text for row in rows}
    finally:
        session.close()


class TestVariantSyncPages:
    def test_the_index_lists_languages(self, client: FlaskClient, release_dir: Path) -> None:
        _write_release(release_dir, [])

        response = client.get("/sync/variants/")

        assert response.status_code == 200
        assert "Spelling Variants" in response.data.decode()

    def test_the_hub_offers_the_page(self, client: FlaskClient) -> None:
        html = client.get("/sync/").data.decode()

        assert "/sync/variants/" in html


class TestVariantChanges:
    """The seeded database has "grey" with only its positive form."""

    def test_a_missing_form_shows_as_a_difference(
        self, client: FlaskClient, release_dir: Path
    ) -> None:
        _write_release(
            release_dir,
            [
                {
                    "kind": "spelling",
                    "key": "grey",
                    "forms": [
                        {
                            "grammatical_form": "adjective/en_positive",
                            "text": "grey",
                            "is_base_form": True,
                        },
                        {
                            "grammatical_form": "adjective/en_comparative",
                            "text": "greyer",
                            "is_base_form": False,
                        },
                    ],
                }
            ],
        )

        html = client.get("/sync/variants/en").data.decode()

        assert "greyer" in html
        # The diff table names the variant, not just the grammatical slot.
        assert "grey (spelling)" in html

    def test_use_release_imports_the_missing_form(
        self, client: FlaskClient, release_dir: Path, db_engine: Any
    ) -> None:
        _write_release(
            release_dir,
            [
                {
                    "kind": "spelling",
                    "key": "grey",
                    "forms": [
                        {
                            "grammatical_form": "adjective/en_positive",
                            "text": "grey",
                            "is_base_form": True,
                        },
                        {
                            "grammatical_form": "adjective/en_comparative",
                            "text": "greyer",
                            "is_base_form": False,
                        },
                    ],
                }
            ],
        )

        response = client.post(
            "/sync/variants/en/changes/apply", data={f"action_{GUID}": "use_release"}
        )

        assert response.status_code == 302
        assert _db_variant_texts(db_engine) == {
            "adjective/en_positive": "grey",
            "adjective/en_comparative": "greyer",
        }

    def test_use_db_writes_the_database_paradigm_to_release(
        self, client: FlaskClient, release_dir: Path
    ) -> None:
        lang_file = _write_release(
            release_dir,
            [
                {
                    "kind": "spelling",
                    "key": "grey",
                    "forms": [
                        {
                            "grammatical_form": "adjective/en_positive",
                            "text": "WRONG",
                            "is_base_form": True,
                        }
                    ],
                }
            ],
        )

        client.post("/sync/variants/en/changes/apply", data={f"action_{GUID}": "use_db"})

        variants = _read_variants(lang_file)
        assert len(variants) == 1
        assert variants[0]["key"] == "grey"
        assert [form["text"] for form in variants[0]["forms"]] == ["grey"]

    def test_export_preserves_the_other_arrays_on_the_line(
        self, client: FlaskClient, release_dir: Path
    ) -> None:
        """Writing variants must not drop the lemma's own forms or synonyms."""
        category = release_dir / "adjectives" / "color"
        category.mkdir(parents=True, exist_ok=True)
        (category / "base.jsonl").write_text(
            json.dumps({"guid": GUID, "concept_label": "gray"}) + "\n", encoding="utf-8"
        )
        (category / "en.jsonl").write_text(
            json.dumps(
                {
                    "guid": GUID,
                    "forms": [{"grammatical_form": "adjective/en_positive", "text": "gray"}],
                    "synonyms": [{"grammatical_form": "synonym", "text": "ashen"}],
                }
            )
            + "\n",
            encoding="utf-8",
        )

        client.post("/sync/variants/en/export_all", data={})

        record = json.loads((category / "en.jsonl").read_text(encoding="utf-8").strip())
        assert record["forms"][0]["text"] == "gray"
        assert record["synonyms"][0]["text"] == "ashen"
        assert record["variants"][0]["key"] == "grey"


class TestVariantRemovals:
    def test_a_db_only_variant_can_be_exported(
        self, client: FlaskClient, release_dir: Path
    ) -> None:
        lang_file = _write_release(release_dir, [])

        client.post("/sync/variants/en/removals/apply", data={f"action_{GUID}": "export"})

        variants = _read_variants(lang_file)
        assert [entry["key"] for entry in variants] == ["grey"]

    def test_a_db_only_variant_can_be_deleted(
        self, client: FlaskClient, release_dir: Path, db_engine: Any
    ) -> None:
        _write_release(release_dir, [])

        client.post("/sync/variants/en/removals/apply", data={f"action_{GUID}": "delete"})

        assert _db_variant_texts(db_engine) == {}

    def test_skip_leaves_both_sides_alone(
        self, client: FlaskClient, release_dir: Path, db_engine: Any
    ) -> None:
        lang_file = _write_release(release_dir, [])

        client.post("/sync/variants/en/removals/apply", data={f"action_{GUID}": "skip"})

        assert _read_variants(lang_file) == []
        assert _db_variant_texts(db_engine) != {}
