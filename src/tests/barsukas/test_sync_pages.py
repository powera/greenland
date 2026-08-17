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
    SyncPage("sentences", "/sync/sentences/", "Sync"),
)


class TestSyncPagesRender:
    """Every sync page renders."""

    @pytest.mark.parametrize("page", SYNC_PAGES, ids=lambda page: page.name)
    def test_page_returns_200(self, client: FlaskClient, page: SyncPage) -> None:
        response = client.get(page.path)
        assert response.status_code == 200

    @pytest.mark.parametrize("page", SYNC_PAGES, ids=lambda page: page.name)
    def test_page_contains_expected_text(self, client: FlaskClient, page: SyncPage) -> None:
        response = client.get(page.path)
        assert page.expected_text.lower() in response.data.decode().lower()

    @pytest.mark.parametrize("page", SYNC_PAGES, ids=lambda page: page.name)
    def test_page_does_not_leak_a_bound_method(self, client: FlaskClient, page: SyncPage) -> None:
        """A macro called without parentheses renders as "<bound method ...>"."""
        html = client.get(page.path).data.decode()
        assert "built-in method" not in html
        assert "bound method" not in html


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
