"""HTTP facade for sentence-domain Barsukas endpoints.

Mirrors ``src/barsukas/routes/api.py``. Any change to a route signature or
response shape there must be reflected here in the same commit.

Currently exposes only the per-language sentence metadata aggregate; example
sentences for a specific lemma live on :func:`api.lemmas.get_sentences` since
they are a lemma sub-resource in the Barsukas API.
"""

from __future__ import annotations

from typing import Any, Optional

from api._mirror import mirrored_route
from api._http import get_json
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
