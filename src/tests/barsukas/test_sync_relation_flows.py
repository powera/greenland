"""Functional tests for the relation sync pages, driven through HTTP.

``test_sync_pages.py`` already asserts these routes return 200, and they did --
because no relation group in that fixture has members, so the loop bodies that
render a member never ran. Both of them read a ``Lemma`` attribute that does not
exist, which meant the first group with members was a 500. These tests seed
groups that actually have members.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest
from flask.testing import FlaskClient
from sqlalchemy.orm import Session

from barsukas.routes.sync import sync_relation_release
from storage.models.lemma_relation import LemmaRelationGroup, LemmaRelationMember


@pytest.fixture()
def relation_release_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the relation sync at a scratch release directory."""
    directory = tmp_path / "lemma_relations"
    (directory / "derivational").mkdir(parents=True)
    monkeypatch.setattr(sync_relation_release, "DEFAULT_RELATION_RELEASE_DIR", directory)
    yield directory


def _write_groups(
    release_dir: Path, relation_type: str, subtype: str, records: List[Dict[str, Any]]
) -> None:
    target = release_dir / relation_type
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{subtype}.jsonl").write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _seed_group(db_session: Session, concept: str, lemma_ids: List[int]) -> int:
    """Create a derivational group with real members, returning its id."""
    group = LemmaRelationGroup(relation_type="derivational", concept_label=concept)
    db_session.add(group)
    db_session.flush()
    for lemma_id in lemma_ids:
        db_session.add(LemmaRelationMember(group_id=group.id, lemma_id=lemma_id))
    db_session.commit()
    return int(group.id)


class TestRemovalsPage:
    """DB groups the release tree does not have."""

    def test_group_with_members_renders(
        self, client: FlaskClient, relation_release_dir: Path, db_session: Session
    ) -> None:
        """The regression: rendering a member read a Lemma attribute that does not exist."""
        _seed_group(db_session, "eating", [1, 2])

        response = client.get("/sync/relations/removals")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        # The member's headword must actually reach the page.
        assert "eat" in body
        assert "house" in body


class TestDifferencesPage:
    """Groups on both sides whose membership differs."""

    def test_members_only_in_db_are_listed(
        self, client: FlaskClient, relation_release_dir: Path, db_session: Session
    ) -> None:
        """`only_in_db` used to subtract a superset of itself and was always empty."""
        _seed_group(db_session, "eating", [1, 2])
        # Release knows about the "eat" GUID but not the "house" one.
        _write_groups(
            relation_release_dir,
            "derivational",
            "consumption",
            [{"concept": "eating", "members": ["V01_001"]}],
        )

        response = client.get("/sync/relations/differences")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        # N01_001 is the "house" lemma: in the database group, absent from
        # release. Assert on the badge, not just the GUID -- the GUID appears in
        # the member list either way, which is why the empty column went
        # unnoticed.
        assert "only in DB" in body
        assert body.index("N01_001") < body.index("only in DB")

    def test_members_only_in_release_are_listed(
        self, client: FlaskClient, relation_release_dir: Path, db_session: Session
    ) -> None:
        _seed_group(db_session, "eating", [1])
        _write_groups(
            relation_release_dir,
            "derivational",
            "consumption",
            [{"concept": "eating", "members": ["V01_001", "N01_001"]}],
        )

        response = client.get("/sync/relations/differences")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "N01_001" in body
        # The mirror-image column, which was always correct.
        assert "only in release" in body.lower()
        # ...and nothing is only in the DB here.
        assert "only in DB" not in body

    def test_matching_membership_is_not_a_difference(
        self, client: FlaskClient, relation_release_dir: Path, db_session: Session
    ) -> None:
        _seed_group(db_session, "eating", [1, 2])
        _write_groups(
            relation_release_dir,
            "derivational",
            "consumption",
            [{"concept": "eating", "members": ["N01_001", "V01_001"]}],
        )

        response = client.get("/sync/relations/differences")

        assert response.status_code == 200
        # Nothing differs, so the group must not be offered for reconciliation.
        assert "eating" not in response.get_data(as_text=True)
