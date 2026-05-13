"""HTTP facade for sentence-domain Barsukas endpoints.

Mirrors ``src/barsukas/routes/api/v1.py``. Any change to a route signature or
response shape there must be reflected here in the same commit.

Currently exposes only the per-language sentence metadata aggregate; example
sentences for a specific lemma live on :func:`api.lemmas.get_sentences` since
they are a lemma sub-resource in the Barsukas API.
"""

from __future__ import annotations

from typing import Any, List, Optional

from api._mirror import mirrored_route
from api._http import get_json, post_json
from api.constants import API_V1_PREFIX


@mirrored_route("/api/v1/metadata/sentences", "GET")
def get_sentence_metadata(
    *,
    language: Optional[str] = None,
    max_difficulty: Optional[int] = None,
) -> Any:
    """Per-language sentence counts and metadata coverage."""
    return get_json(
        f"{API_V1_PREFIX}/metadata/sentences",
        {"language": language, "max_difficulty": max_difficulty},
    )


@mirrored_route("/api/v1/sentences/add", "POST")
def add_sentences(
    sentences: List[str],
    source: str,
    *,
    language: Optional[str] = None,
) -> Any:
    """Add up to 15 sentences to the database, deduplicating by text.

    Makes no LLM calls. Sentences already present are returned with status
    ``already_exists`` so the caller still gets their IDs. Use the returned
    IDs with :func:`api.llm_agents.decompose_sentences` to queue translation
    and lemma decomposition.

    Args:
        sentences: List of sentence strings (max 15).
        source: Source identifier stored as ``source_filename`` on each Sentence row.
        language: Source language code of the input sentences (default: "en").

    Returns:
        API response dict with ``data`` (list of per-sentence results with
        sentence_id, guid, status) and ``metadata``.
    """
    body: dict[str, Any] = {"sentences": sentences, "source": source}
    if language is not None:
        body["language"] = language
    return post_json(f"{API_V1_PREFIX}/sentences/add", body)
