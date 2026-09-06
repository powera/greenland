"""Smoke tests for the /sync pages.

These render every sync page against the seeded test database. They are not
business-logic tests: what they catch is the failure this area is actually
prone to - a template moved, a macro renamed, or an ``url_for`` naming an
endpoint that no longer exists - which otherwise only shows up in a browser.

The record-sync pages (idioms, names) are covered by their real blueprints, so
the spec-driven templates are exercised for both element types.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import pytest
from flask.testing import FlaskClient


@dataclass(frozen=True)
class SyncPage:
    """One sync page and a string that must appear once it renders."""

    name: str
    path: str
    expected_text: str


SYNC_PAGES: Tuple[SyncPage, ...] = (
    SyncPage("hub", "/sync/", "Sync Hub"),
    SyncPage("lemmas", "/sync/lemmas/", "Sync"),
    SyncPage("lemma-additions", "/sync/lemmas/additions", "Release"),
    SyncPage("lemma-removals", "/sync/lemmas/removals", "Release"),
    SyncPage("lemma-changes", "/sync/lemmas/changes", "Release"),
    SyncPage("lemma-difficulty", "/sync/lemmas/difficulty", "Release"),
    SyncPage("lemma-translations", "/sync/lemmas/translations", "Release"),
    SyncPage("secondary-select", "/sync/lemmas/secondary-translations", "Secondary"),
    SyncPage("idioms", "/sync/idioms/", "Idioms"),
    SyncPage("idiom-additions", "/sync/idioms/additions", "Idioms"),
    SyncPage("idiom-removals", "/sync/idioms/removals", "Idioms"),
    SyncPage("idiom-changes", "/sync/idioms/changes", "Idioms"),
    SyncPage("names", "/sync/names/", "Names"),
    SyncPage("name-additions", "/sync/names/additions", "Names"),
    SyncPage("name-removals", "/sync/names/removals", "Names"),
    SyncPage("name-changes", "/sync/names/changes", "Names"),
    SyncPage("phrases", "/sync/phrases/", "Sync"),
    SyncPage("phrase-additions", "/sync/phrases/additions", "Phrase"),
    SyncPage("phrase-removals", "/sync/phrases/removals", "Phrase"),
    SyncPage("phrase-changes", "/sync/phrases/changes", "Phrase"),
    SyncPage("phrase-level", "/sync/phrases/level", "Phrase"),
    SyncPage("phrase-translations", "/sync/phrases/translations", "Phrase"),
    SyncPage("phrase-export", "/sync/phrases/export", "Phrase"),
    SyncPage("sentences", "/sync/sentences/", "Sync"),
    SyncPage("sentence-additions", "/sync/sentences/additions", "Sentence"),
    SyncPage("sentence-removals", "/sync/sentences/removals", "Sentence"),
    SyncPage("sentence-changes", "/sync/sentences/changes", "Sentence"),
    SyncPage("sentence-level", "/sync/sentences/level", "Sentence"),
    SyncPage("sentence-translations", "/sync/sentences/translations", "Sentence"),
    SyncPage("sentence-export", "/sync/sentences/export", "Sentence"),
    SyncPage("derivatives", "/sync/derivatives/", "Derivative"),
    SyncPage("derivatives-lang", "/sync/derivatives/lt", "lt"),
    SyncPage("synonyms", "/sync/synonyms/", "Synonym"),
    SyncPage("synonyms-lang", "/sync/synonyms/lt", "lt"),
    SyncPage("variants", "/sync/variants/", "Variant"),
    SyncPage("variants-lang", "/sync/variants/en", "en"),
    SyncPage("lemma-audio", "/sync/lemma-audio/", "Audio"),
    SyncPage("relations", "/sync/relations/", "Relation"),
    SyncPage("relation-additions", "/sync/relations/additions", "Relation"),
    SyncPage("relation-removals", "/sync/relations/removals", "Relation"),
    SyncPage("relation-differences", "/sync/relations/differences", "Relation"),
    SyncPage("tombstones", "/sync/tombstones/", "Tombstone"),
    SyncPage("tombstone-additions", "/sync/tombstones/additions", "Tombstone"),
    SyncPage("tombstone-removals", "/sync/tombstones/removals", "Tombstone"),
    SyncPage("tombstone-changes", "/sync/tombstones/changes", "Tombstone"),
)


class TestSyncPagesRender:
    """Every sync page renders.

    One test rather than a parametrized case per page: each case would rebuild
    the app and reseed the database for a single GET, which cost far more than
    the request itself.  Every page is still checked -- the loop collects all
    the failures so one broken page names itself instead of hiding the rest.
    """

    def test_every_sync_page_renders(self, client: FlaskClient) -> None:
        failures: list[str] = []

        for page in SYNC_PAGES:
            response = client.get(page.path)
            if response.status_code != 200:
                failures.append(f"{page.name} ({page.path}): HTTP {response.status_code}")
                continue

            html = response.data.decode()
            if page.expected_text.lower() not in html.lower():
                failures.append(f"{page.name} ({page.path}): missing {page.expected_text!r}")
            # A macro called without parentheses renders as "<bound method ...>".
            for leak in ("built-in method", "bound method"):
                if leak in html:
                    failures.append(f"{page.name} ({page.path}): leaked a {leak}")

        assert not failures, "sync pages failed to render:\n  " + "\n  ".join(failures)


class TestSyncHub:
    """The hub lists every category it knows about."""

    def test_hub_links_to_every_category(self, client: FlaskClient) -> None:
        from barsukas.routes.sync.sync_hub import SYNC_CATEGORIES

        html = client.get("/sync/").data.decode()
        for category in SYNC_CATEGORIES:
            assert category.title in html

    def test_hub_lists_names_and_idioms(self, client: FlaskClient) -> None:
        html = client.get("/sync/").data.decode()
        assert "/sync/names/" in html
        assert "/sync/idioms/" in html

    def test_hub_explains_why_concepts_are_absent(self, client: FlaskClient) -> None:
        """Their absence is a decision, so the page should say so."""
        assert "Concepts are intentionally absent" in client.get("/sync/").data.decode()


class TestPagingControls:
    """Paging is driven by query arguments and degrades to a full list."""

    def test_per_page_argument_is_accepted(self, client: FlaskClient) -> None:
        assert client.get("/sync/lemmas/changes?per_page=50").status_code == 200

    def test_unlimited_per_page_is_accepted(self, client: FlaskClient) -> None:
        assert client.get("/sync/lemmas/changes?per_page=0").status_code == 200

    def test_a_nonsense_page_argument_does_not_500(self, client: FlaskClient) -> None:
        assert client.get("/sync/lemmas/changes?page=banana").status_code == 200

    def test_an_out_of_range_page_does_not_500(self, client: FlaskClient) -> None:
        assert client.get("/sync/lemmas/changes?page=9999").status_code == 200


class TestBulkApplyGuards:
    """The whole-list apply refuses a submit whose count no longer matches."""

    def test_stale_expected_count_is_refused(self, client: FlaskClient) -> None:
        response = client.post(
            "/sync/idioms/changes/apply",
            data={"bulk_action": "use_release", "bulk_expected_count": "999"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "list changed since the page was loaded" in response.data.decode()

    def test_a_submit_with_no_selection_is_refused(self, client: FlaskClient) -> None:
        response = client.post("/sync/idioms/changes/apply", data={}, follow_redirects=True)
        assert response.status_code == 200
        assert "No changes selected" in response.data.decode()

    def test_import_with_no_selection_is_refused(self, client: FlaskClient) -> None:
        response = client.post("/sync/names/additions/apply", data={}, follow_redirects=True)
        assert response.status_code == 200
        assert "No names selected" in response.data.decode()


@pytest.fixture()
def removable_rows(db_engine) -> None:  # type: ignore[type-arg]
    """A tombstone and a name that exist in the database but not in release.

    Both removals pages render "all in sync" against the bare seed, which would
    make the delete-button assertions below pass for the wrong reason.
    """
    from sqlalchemy.orm import sessionmaker

    from storage.crud.guid_tombstone import create_tombstone
    from storage.models.guid_tombstone import TOMBSTONE_REASON_RELEASE_REMOVAL
    from storage.models.name_entity import Name

    session = sessionmaker(bind=db_engine)()
    create_tombstone(
        session=session,
        guid="N02_997",
        original_lemma_text="aurochs",
        original_pos_type="noun",
        original_pos_subtype="animal",
        replacement_guid=None,
        lemma_id=None,
        reason=TOMBSTONE_REASON_RELEASE_REMOVAL,
    )
    session.add(Name(guid="E01_997", name_text="Testina", kind="given_name"))
    session.commit()
    session.close()


class TestTombstoneSyncIsExportOnly:
    """A tombstone is a permanent record, so its removals page cannot delete.

    Every other whole-record type offers export-or-delete there. Deleting a
    tombstone would un-retire its GUID and free it to be issued to a different
    word, which is the outcome the whole mechanism exists to prevent.
    """

    def test_the_removals_page_lists_the_unreleased_tombstone(
        self, client: FlaskClient, removable_rows: None
    ) -> None:
        """Guards the two assertions below against a vacuous empty page."""
        html = client.get("/sync/tombstones/removals").data.decode()

        assert "N02_997" in html

    def test_the_removals_page_offers_no_delete_button(
        self, client: FlaskClient, removable_rows: None
    ) -> None:
        html = client.get("/sync/tombstones/removals").data.decode()

        assert "Delete Selected" not in html

    def test_other_types_still_offer_delete(
        self, client: FlaskClient, removable_rows: None
    ) -> None:
        """The knob is opt-out, so the shared engine keeps its usual behaviour."""
        html = client.get("/sync/names/removals").data.decode()

        assert "E01_997" in html
        assert "Delete Selected" in html

    def test_the_delete_route_refuses_even_when_posted_directly(
        self, client: FlaskClient, removable_rows: None
    ) -> None:
        """Hiding the button is not enough; the route itself declines."""
        response = client.post("/sync/tombstones/removals/delete", data={"selected_ids": ["1"]})

        assert response.status_code == 302
        assert "/sync/tombstones/removals" in response.headers["Location"]
        assert "N02_997" in client.get("/sync/tombstones/removals").data.decode()
