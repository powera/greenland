"""The GUID lookup page, which explains retired GUIDs instead of 404ing on them.

Barsukas is navigated by database id everywhere else; a GUID is what release
files and external references carry. Before this page a retired GUID was
indistinguishable from one that never existed.
"""

from typing import Iterator

import pytest
from flask.testing import FlaskClient
from sqlalchemy.orm import sessionmaker

from storage.crud.guid_tombstone import create_tombstone
from storage.models.guid_tombstone import (
    TOMBSTONE_REASON_RELEASE_REMOVAL,
    TOMBSTONE_REASON_TYPE_AND_SUBTYPE_CHANGE,
)
from storage.models.schema import Lemma


@pytest.fixture()
def tombstoned(db_engine) -> Iterator[str]:  # type: ignore[type-arg]
    """Seed a live lemma plus tombstones, the way conftest seeds its own data.

    Written against ``db_engine`` rather than an app context because that is how
    the shared fixtures load the temporary database; the app opens its own
    session per request against the same file.
    """
    factory = sessionmaker(bind=db_engine)
    session = factory()
    lemma = Lemma(
        lemma_text="triangle",
        definition_text="a three-sided shape",
        pos_type="noun",
        pos_subtype="shape",
        guid="N08_001",
    )
    session.add(lemma)
    session.flush()
    create_tombstone(
        session=session,
        guid="A03_001",
        original_lemma_text="triangle",
        original_pos_type="adjective",
        original_pos_subtype="quality",
        replacement_guid="N08_001",
        lemma_id=lemma.id,
        reason=TOMBSTONE_REASON_TYPE_AND_SUBTYPE_CHANGE,
        notes="was miscategorised as an adjective",
        changed_by="tests",
    )
    create_tombstone(
        session=session,
        guid="N08_002",
        original_lemma_text="wyvern",
        original_pos_type="noun",
        original_pos_subtype="animal",
        replacement_guid=None,
        lemma_id=None,
        reason=TOMBSTONE_REASON_RELEASE_REMOVAL,
    )
    session.commit()
    session.close()
    yield "N08_001"


def test_the_search_page_renders(client: FlaskClient) -> None:
    response = client.get("/guids/")

    assert response.status_code == 200
    assert b"GUID Lookup" in response.data


def test_a_live_guid_redirects_to_its_record(client: FlaskClient, tombstoned: str) -> None:
    response = client.get(f"/guids/?guid={tombstoned}")

    assert response.status_code == 302
    assert "/lemmas/" in response.headers["Location"]


def test_a_retired_guid_reports_its_replacement(client: FlaskClient, tombstoned: str) -> None:
    response = client.get("/guids/?guid=A03_001")

    assert response.status_code == 200
    body = response.data.decode()
    assert "retired" in body
    assert "N08_001" in body
    assert "was miscategorised as an adjective" in body


def test_a_deleted_guid_says_there_is_no_replacement(client: FlaskClient, tombstoned: str) -> None:
    response = client.get("/guids/?guid=N08_002")

    assert response.status_code == 200
    body = response.data.decode()
    assert "retired" in body
    assert "No replacement was recorded" in body


def test_an_unissued_guid_is_distinguished_from_a_retired_one(client: FlaskClient) -> None:
    response = client.get("/guids/?guid=N08_404")

    assert response.status_code == 200
    body = response.data.decode()
    assert "never been retired" in body


def test_the_permalink_form_redirects_into_the_search(client: FlaskClient) -> None:
    response = client.get("/guids/A03_001")

    assert response.status_code == 302
    assert "guid=A03_001" in response.headers["Location"]


def test_the_lemma_page_lists_the_guids_that_lemma_used_to_have(
    client: FlaskClient, tombstoned: str
) -> None:
    """The detail page grew a "Previous GUIDs" panel fed by a new context key.

    get_lemma_view_data's documented query plan had promised this since before
    the query existed.
    """
    lookup = client.get(f"/guids/?guid={tombstoned}")
    response = client.get(lookup.headers["Location"])

    assert response.status_code == 200
    body = response.data.decode()
    assert "Previous GUIDs" in body
    assert "A03_001" in body


def test_a_lemma_with_no_history_shows_no_panel(client: FlaskClient) -> None:
    """The panel is hidden rather than rendered empty for the usual case."""
    response = client.get("/lemmas/1")

    assert response.status_code == 200
    assert "Previous GUIDs" not in response.data.decode()
