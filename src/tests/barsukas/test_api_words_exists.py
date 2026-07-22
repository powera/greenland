"""Tests for POST /api/v1/words/exists.

The endpoint is the bulk, exact-accounting counterpart to /api/v1/search: it must
agree with ``word_exists_in_english``, which counts a word as present when it is a
lemma, a disambiguated lemma, an English derivative form, or an alternate
spelling. The seed data supplies one of each shape ("eat"/"eating", "gray"/"grey").
"""

from __future__ import annotations

from flask.testing import FlaskClient


def _post(client: FlaskClient, payload: dict) -> tuple[int, dict]:
    response = client.post("/api/v1/words/exists", json=payload)
    return response.status_code, response.get_json()


def test_reports_lemma_derivative_and_variant_as_existing(client: FlaskClient) -> None:
    """All three ways a word can be accounted for count as existing."""
    status, payload = _post(client, {"words": ["eat", "eating", "grey", "zzznotaword"]})

    assert status == 200
    assert payload["data"] == {
        "eat": True,  # lemma
        "eating": True,  # English derivative form
        "grey": True,  # alternate spelling of "gray" in variant_forms
        "zzznotaword": False,
    }


def test_metadata_counts_checked_and_existing(client: FlaskClient) -> None:
    status, payload = _post(client, {"words": ["eat", "house", "zzznotaword"]})

    assert status == 200
    assert payload["metadata"]["checked"] == 3
    assert payload["metadata"]["existing"] == 2
    assert payload["metadata"]["include_exclusions"] is True


def test_words_are_normalized_and_deduplicated(client: FlaskClient) -> None:
    """Keys come back lowercased and stripped; duplicates collapse to one entry."""
    status, payload = _post(client, {"words": ["  EAT  ", "eat", "Eat"]})

    assert status == 200
    assert payload["data"] == {"eat": True}
    assert payload["metadata"]["checked"] == 1


def test_include_exclusions_is_accepted(client: FlaskClient) -> None:
    """Passing the flag explicitly is echoed back in metadata."""
    status, payload = _post(client, {"words": ["zzznotaword"], "include_exclusions": False})

    assert status == 200
    assert payload["metadata"]["include_exclusions"] is False


def test_missing_words_list_is_rejected(client: FlaskClient) -> None:
    status, payload = _post(client, {})

    assert status == 400
    assert "words" in payload["error"]


def test_empty_words_list_is_rejected(client: FlaskClient) -> None:
    status, _ = _post(client, {"words": []})

    assert status == 400


def test_non_string_entries_are_rejected(client: FlaskClient) -> None:
    status, _ = _post(client, {"words": ["eat", 7]})

    assert status == 400


def test_oversized_words_list_is_rejected(client: FlaskClient) -> None:
    """The cap keeps a single request from building an unbounded IN-list."""
    from barsukas.routes.api.lemma_routes import MAX_EXISTS_WORDS

    status, payload = _post(client, {"words": [f"word{n}" for n in range(MAX_EXISTS_WORDS + 1)]})

    assert status == 400
    assert str(MAX_EXISTS_WORDS) in payload["error"]


def test_at_the_cap_is_accepted(client: FlaskClient) -> None:
    """Exactly at the limit still works -- the check is strictly greater-than."""
    from barsukas.routes.api.lemma_routes import MAX_EXISTS_WORDS

    words = [f"word{n}" for n in range(MAX_EXISTS_WORDS - 1)] + ["eat"]
    status, payload = _post(client, {"words": words})

    assert status == 200
    assert payload["data"]["eat"] is True


def test_bad_include_exclusions_type_is_rejected(client: FlaskClient) -> None:
    status, _ = _post(client, {"words": ["eat"], "include_exclusions": "yes"})

    assert status == 400
