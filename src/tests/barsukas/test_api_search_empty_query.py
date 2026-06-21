"""Tests for the /api/v1/search endpoint's empty-query behavior."""

from __future__ import annotations

from flask.testing import FlaskClient


def test_empty_query_returns_all_lemmas(client: FlaskClient) -> None:
    """An empty ``q`` should match all lemmas instead of erroring."""
    response = client.get("/api/v1/search?q=")
    assert response.status_code == 200
    payload = response.get_json()
    guids = {item["guid"] for item in payload["data"]}
    assert {"V01_001", "N01_001"} <= guids
    assert payload["metadata"]["total_results"] >= 2


def test_omitted_query_returns_all_lemmas(client: FlaskClient) -> None:
    """Omitting ``q`` entirely behaves the same as an empty query."""
    response = client.get("/api/v1/search")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["metadata"]["total_results"] >= 2


def test_empty_query_respects_pos_filter(client: FlaskClient) -> None:
    """Empty ``q`` still honors the other filters."""
    response = client.get("/api/v1/search?q=&pos_type=noun")
    assert response.status_code == 200
    payload = response.get_json()
    guids = {item["guid"] for item in payload["data"]}
    assert guids == {"N01_001"}
