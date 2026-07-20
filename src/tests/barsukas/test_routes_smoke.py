"""Smoke tests for Barsukas GET routes.

These tests use the Flask test client with a temporary SQLite database
to verify that key pages render without errors. They do NOT test
business logic — only that templates render and return 200.
"""

from dataclasses import dataclass

import pytest
from flask.testing import FlaskClient


@dataclass(frozen=True)
class RouteSmokeCase:
    """Single smoke-test case for a route."""

    name: str
    path: str
    expected_text: str


ROUTE_SMOKE_CASES: tuple[RouteSmokeCase, ...] = (
    RouteSmokeCase(name="lemmas", path="/lemmas/", expected_text="eat"),
    RouteSmokeCase(name="sentences", path="/sentences/", expected_text="I eat"),
    RouteSmokeCase(name="dictionary", path="/dictionary/?letter=E", expected_text="eat"),
    RouteSmokeCase(name="sync", path="/sync/", expected_text="sync"),
    RouteSmokeCase(name="exports", path="/exports/", expected_text="GYVATE"),
    RouteSmokeCase(name="worker-tasks", path="/barsukas-tasks/", expected_text="Worker Tasks"),
    RouteSmokeCase(name="batch-jobs", path="/batch-operations/", expected_text="Batch Jobs"),
    RouteSmokeCase(name="quality-hub", path="/quality/", expected_text="Quality Hub"),
    RouteSmokeCase(name="audio-hub", path="/audio/", expected_text="Audio Hub"),
    RouteSmokeCase(name="completeness", path="/completeness/", expected_text="Completeness"),
)


class TestQualityHubChecks:
    """Smoke checks for the Quality Hub's in-process integrity runner."""

    def test_run_check_duplicate_words(self, client: FlaskClient) -> None:
        response = client.post("/quality/run-check", data={"check_type": "duplicate-words"})
        assert response.status_code == 200
        assert b"duplicate-words" in response.data

    def test_run_check_unknown_type_redirects(self, client: FlaskClient) -> None:
        response = client.post("/quality/run-check", data={"check_type": "nonsense"})
        assert response.status_code == 302

    def test_rapid_review_hub_redirects_to_quality(self, client: FlaskClient) -> None:
        response = client.get("/rapid-review/")
        assert response.status_code == 302
        assert "/quality/" in response.headers["Location"]


class TestRouteSmoke:
    """Reusable smoke checks for top-level Barsukas sections."""

    @pytest.mark.parametrize("case", ROUTE_SMOKE_CASES, ids=lambda case: case.name)
    def test_section_page_returns_200(self, client: FlaskClient, case: RouteSmokeCase) -> None:
        response = client.get(case.path)
        assert response.status_code == 200

    @pytest.mark.parametrize("case", ROUTE_SMOKE_CASES, ids=lambda case: case.name)
    def test_section_page_contains_expected_text(
        self, client: FlaskClient, case: RouteSmokeCase
    ) -> None:
        response = client.get(case.path)
        assert response.status_code == 200
        html = response.data.decode().lower()
        assert case.expected_text.lower() in html

    @pytest.mark.parametrize("case", ROUTE_SMOKE_CASES, ids=lambda case: case.name)
    def test_section_page_does_not_render_builtin_method_text(
        self, client: FlaskClient, case: RouteSmokeCase
    ) -> None:
        response = client.get(case.path)
        assert response.status_code == 200
        html = response.data.decode()
        assert "built-in method" not in html


class TestLemmaRoutes:
    """Smoke tests for /lemmas routes."""

    def test_lemma_list_search(self, client: FlaskClient) -> None:
        response = client.get("/lemmas/?search=house")
        assert response.status_code == 200
        html = response.data.decode()
        assert "house" in html

    def test_lemma_list_filter_by_pos_type(self, client: FlaskClient) -> None:
        response = client.get("/lemmas/?pos_type=verb")
        assert response.status_code == 200

    def test_view_lemma_returns_200(self, client: FlaskClient) -> None:
        response = client.get("/lemmas/1")
        assert response.status_code == 200

    def test_view_lemma_contains_lemma_text(self, client: FlaskClient) -> None:
        response = client.get("/lemmas/1")
        html = response.data.decode()
        assert "eat" in html

    @pytest.mark.parametrize("subpage", ["forms", "audio", "related", "levels"])
    def test_view_lemma_subpages_return_200(self, client: FlaskClient, subpage: str) -> None:
        response = client.get(f"/lemmas/1/{subpage}")
        assert response.status_code == 200
        html = response.data.decode()
        assert "eat" in html

    def test_view_nonexistent_lemma_redirects(self, client: FlaskClient) -> None:
        response = client.get("/lemmas/9999")
        # Should redirect to the lemma list
        assert response.status_code == 302

    @pytest.mark.parametrize("subpage", ["forms", "audio", "related", "levels"])
    def test_view_nonexistent_lemma_subpages_redirect(
        self, client: FlaskClient, subpage: str
    ) -> None:
        response = client.get(f"/lemmas/9999/{subpage}")
        assert response.status_code == 302

    def test_view_second_lemma(self, client: FlaskClient) -> None:
        response = client.get("/lemmas/2")
        assert response.status_code == 200
        html = response.data.decode()
        assert "house" in html


@pytest.mark.smoke
class TestHomeRoute:
    """Smoke test for the home page."""

    def test_home_returns_200(self, client: FlaskClient) -> None:
        response = client.get("/")
        assert response.status_code == 200


@pytest.mark.smoke
class TestHealthRoute:
    """Smoke test for the health check endpoint."""

    def test_healthz_returns_ok(self, client: FlaskClient) -> None:
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.text == "ok\n"
        assert response.mimetype == "text/plain"
