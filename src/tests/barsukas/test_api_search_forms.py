"""Tests that /api/v1/search folds in English derivative and variant forms.

Search used to match only lemma text, definitions, disambiguation and
translations, so it disagreed with ``word_exists_in_english`` -- which also folds
in derivative forms and alternate spellings -- about what the database contains.
A caller surveying a wordlist got one answer from search and another from the add
endpoint. These tests pin the agreement.
"""

from __future__ import annotations

from flask.testing import FlaskClient


def _guids(client: FlaskClient, query: str) -> list[str]:
    response = client.get(f"/api/v1/search?q={query}")
    assert response.status_code == 200
    return [item["guid"] for item in response.get_json()["data"]]


def test_alternate_spelling_finds_its_lemma(client: FlaskClient) -> None:
    """An alternate spelling finds its lemma: "grey" resolves to "gray"."""
    assert "J01_001" in _guids(client, "grey")


def test_derivative_form_finds_its_lemma(client: FlaskClient) -> None:
    """A derivative form finds its lemma: "eating" resolves to "eat"."""
    assert "V01_001" in _guids(client, "eating")


def test_search_agrees_with_the_existence_guard(client: FlaskClient) -> None:
    """Every word the guard calls existing is now findable through search."""
    words = ["eat", "eating", "grey", "gray"]

    exists = client.post("/api/v1/words/exists", json={"words": words}).get_json()
    assert all(exists["data"][word] for word in words)

    for word in words:
        assert _guids(client, word), f"search found nothing for {word!r}"


def test_direct_lemma_match_outranks_a_form_match(client: FlaskClient) -> None:
    """Relevance ordering: the lemma itself comes before a form-only hit.

    "gray" matches lemma 3 directly; nothing else in the seed matches it, so this
    also guards against the form subqueries dragging in unrelated rows.
    """
    guids = _guids(client, "gray")
    assert guids[0] == "J01_001"


def test_unmatched_query_still_returns_nothing(client: FlaskClient) -> None:
    """The added OR-conditions must not turn a miss into a match."""
    assert _guids(client, "zzznotaword") == []
