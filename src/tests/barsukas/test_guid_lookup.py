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


def test_the_permalink_goes_straight_to_a_live_record(
    client: FlaskClient, tombstoned: str
) -> None:
    """A live GUID redirects to its detail page, not back into the search box."""
    response = client.get(f"/guids/{tombstoned}")

    assert response.status_code == 302
    assert "/lemmas/" in response.headers["Location"]


def test_the_permalink_404s_for_a_guid_that_names_nothing(client: FlaskClient) -> None:
    """The permalink and the search box deliberately differ here.

    The search box is a form reporting on what was typed, so an unissued GUID
    renders the "never issued" panel at 200. A permalink is an address claiming
    a record exists at it, so anything following links or hunting dead
    references needs that claim to fail properly.
    """
    assert client.get("/guids/N08_404").status_code == 404
    assert client.get("/guids/?guid=N08_404").status_code == 200


def test_the_permalink_still_explains_a_retired_guid(
    client: FlaskClient, tombstoned: str
) -> None:
    """A tombstoned GUID is not a 404: the number was issued, and what replaced
    it is the answer the caller came for.

    ``A03_001`` is the retired GUID the fixture creates; the ``tombstoned``
    fixture itself yields the live lemma that replaced it.
    """
    response = client.get("/guids/A03_001")

    assert response.status_code == 200
    body = response.data.decode()
    assert "retired" in body
    assert tombstoned in body


def test_a_string_that_is_not_a_guid_is_reported_as_such(client: FlaskClient) -> None:
    """"banana" is a typo, not a lemma GUID that was never issued.

    guid_kind() falls back to "lemma" for any unrecognized string, so without a
    separate well-formedness check the search box told users their typo "would
    be a lemma".
    """
    response = client.get("/guids/?guid=banana")

    assert response.status_code == 200
    assert "That is not a GUID" in response.data.decode()

    # As an address, though, it is simply not found.
    assert client.get("/guids/banana").status_code == 404


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
