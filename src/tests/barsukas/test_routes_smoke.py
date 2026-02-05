"""Smoke tests for Barsukas GET routes.

These tests use the Flask test client with a temporary SQLite database
to verify that key pages render without errors.  They do NOT test
business logic — only that templates render and return 200.
"""

import pytest
from flask.testing import FlaskClient


class TestLemmaRoutes:
    """Smoke tests for /lemmas routes."""

    def test_lemma_list_returns_200(self, client: FlaskClient) -> None:
        response = client.get("/lemmas/")
        assert response.status_code == 200

    def test_lemma_list_contains_seed_lemma(self, client: FlaskClient) -> None:
        response = client.get("/lemmas/")
        html = response.data.decode()
        assert "eat" in html

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

    def test_view_nonexistent_lemma_redirects(self, client: FlaskClient) -> None:
        response = client.get("/lemmas/9999")
        # Should redirect to the lemma list
        assert response.status_code == 302

    def test_view_second_lemma(self, client: FlaskClient) -> None:
        response = client.get("/lemmas/2")
        assert response.status_code == 200
        html = response.data.decode()
        assert "house" in html


class TestHomeRoute:
    """Smoke test for the home page."""

    def test_home_returns_200(self, client: FlaskClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
