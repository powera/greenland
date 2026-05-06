"""HTTP facade for bulk/aggregate Barsukas endpoints.

Covers per-language word-metadata aggregates, the LLM model registry, and the
pending-imports listing/duplicate-detection endpoints. Mirrors
``src/barsukas/routes/api.py`` and ``src/barsukas/routes/pending_imports.py``.
Any change to a route signature or response shape there must be reflected
here in the same commit.
"""

from __future__ import annotations

from typing import Any, Optional

from api._mirror import mirrored_route
from api._http import get_json
from api.constants import API_V1_PREFIX

_PENDING_IMPORTS_PREFIX = "/pending-imports"


@mirrored_route("/api/v1/metadata/words", "GET")
def get_word_metadata(
    *,
    language: Optional[str] = None,
    max_difficulty: Optional[int] = None,
    difficulty: Optional[int] = None,
) -> Any:
    """Per-language lemma counts and metadata coverage."""
    return get_json(
        f"{API_V1_PREFIX}/metadata/words",
        {"language": language, "max_difficulty": max_difficulty, "difficulty": difficulty},
    )


@mirrored_route("/api/v1/models", "GET")
def list_models(*, q: Optional[str] = None) -> Any:
    """List LLM models registered in the benchmarks database."""
    return get_json(f"{API_V1_PREFIX}/models", {"q": q})


@mirrored_route("/pending-imports/api/duplicates", "GET")
def find_pending_import_duplicates() -> Any:
    """Find pending imports that duplicate existing lemmas (direct/form match)."""
    return get_json(f"{_PENDING_IMPORTS_PREFIX}/api/duplicates")


@mirrored_route("/pending-imports/api/list", "GET")
def list_pending_imports(
    *,
    search: Optional[str] = None,
    pos_type: Optional[str] = None,
    pos_subtype: Optional[str] = None,
    source: Optional[str] = None,
    language: Optional[str] = None,
    page: Optional[int] = None,
) -> Any:
    """List pending imports as JSON (same filters as the HTML list view)."""
    return get_json(
        f"{_PENDING_IMPORTS_PREFIX}/api/list",
        {
            "search": search,
            "pos_type": pos_type,
            "pos_subtype": pos_subtype,
            "source": source,
            "language": language,
            "page": page,
        },
    )
