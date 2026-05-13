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


@mirrored_route("/api/v1/sentences/decompose-batch", "POST")
def decompose_sentence_batch(
    sentences: List[str],
    source: str,
    *,
    model: Optional[str] = None,
    language: Optional[str] = None,
) -> Any:
    """Add up to 15 sentences to the database and decompose each into translations and lemmas.

    Each sentence is stored with the supplied *source* identifier and translated
    into English, French, Chinese, Lithuanian, and Spanish via an LLM call.
    Per-word lemma associations are stored for each language.

    Sentences that already exist (matched by text and language) are returned
    with their existing translations without re-running decomposition.

    Args:
        sentences: List of sentence strings (max 15).
        source: Source identifier stored as ``source_filename`` on each Sentence row.
        model: LLM model to use (default: gpt-5.4-mini).
        language: Source language code of the input sentences (default: "en").

    Returns:
        API response dict with ``data`` (list of per-sentence results) and ``metadata``.
    """
    body: dict[str, Any] = {"sentences": sentences, "source": source}
    if model is not None:
        body["model"] = model
    if language is not None:
        body["language"] = language
    return post_json(f"{API_V1_PREFIX}/sentences/decompose-batch", body)
