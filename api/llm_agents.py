"""HTTP facade for LLM-driven agent endpoints under ``/api/llm/``.

Mirrors ``src/barsukas/routes/llm_api.py``. Any change to a route signature
or response shape there must be reflected here in the same commit.

The Barsukas routes accept optional API keys in the JSON body so callers can
inject credentials per-request. These facades intentionally do **not**
expose those parameters: the wrapper is meant for trusted internal use
where Barsukas' own configured/system keys are used. If a future endpoint
genuinely requires a per-call key, do not add it here.
"""

from __future__ import annotations

from typing import Any, List, Optional

from api._http import get_json, post_json
from api._mirror import mirrored_route


@mirrored_route("/api/llm/info", "GET")
def get_llm_info() -> Any:
    """List the LLM agent endpoints exposed by Barsukas."""
    return get_json("/api/llm/info")


@mirrored_route("/api/llm/voras/check-translations", "POST")
def check_translations(guid: str, *, model: Optional[str] = None) -> Any:
    """Trigger Voras translation validation for one lemma."""
    return post_json(
        "/api/llm/voras/check-translations",
        {"guid": guid, "model": model},
    )


@mirrored_route("/api/llm/voras/add-missing-translations", "POST")
def add_missing_translations(
    guid: str,
    *,
    model: Optional[str] = None,
    languages: Optional[List[str]] = None,
) -> Any:
    """Generate missing translations for a lemma.

    When ``languages`` is omitted/None, Voras fills all configured generation
    languages. When provided, Voras fills only the requested language codes.
    """
    return post_json(
        "/api/llm/voras/add-missing-translations",
        {"guid": guid, "model": model, "languages": languages},
    )


@mirrored_route("/api/llm/papuga/generate-pronunciations", "POST")
def generate_pronunciations(
    guid: str,
    *,
    lang_code: str = "en",
    model: Optional[str] = None,
) -> Any:
    """Generate pronunciations for a lemma's forms in ``lang_code``."""
    return post_json(
        "/api/llm/papuga/generate-pronunciations",
        {"guid": guid, "lang_code": lang_code, "model": model},
    )


@mirrored_route("/api/llm/lokys/check-definition", "POST")
def check_definition(guid: str, *, model: Optional[str] = None) -> Any:
    """Check / improve the definition of a lemma."""
    return post_json(
        "/api/llm/lokys/check-definition",
        {"guid": guid, "model": model},
    )


@mirrored_route("/api/llm/lokys/check-disambiguation", "POST")
def check_disambiguation(guid: str, *, model: Optional[str] = None) -> Any:
    """Check / improve the disambiguation of a lemma."""
    return post_json(
        "/api/llm/lokys/check-disambiguation",
        {"guid": guid, "model": model},
    )
