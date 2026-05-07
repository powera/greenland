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

from typing import Any, Dict, List, Optional, TypedDict, cast

from api._http import get_json, post_json
from api._mirror import mirrored_route


class SuccessResponse(TypedDict):
    """Standard success envelope returned by LLM API routes."""

    success: bool


class AddMissingTranslationsLanguageStats(TypedDict):
    """Per-language statistics for generated translations."""

    language_name: str
    total_missing: int
    fixed: int
    failed: int


class AddMissingTranslationsData(TypedDict):
    """Payload returned by ``/api/llm/voras/add-missing-translations``."""

    guids: List[str]
    missing_guids: List[str]
    total_fixed: int
    total_failed: int
    by_language: Dict[str, AddMissingTranslationsLanguageStats]
    llm_cost_usd: float


class AddMissingTranslationsResponse(SuccessResponse):
    """Response envelope for add-missing-translations."""

    data: AddMissingTranslationsData


class GenerateAudioResult(TypedDict, total=False):
    status: str
    audio_url: str
    manifest_md5: str
    error: str


class GenerateAudioData(TypedDict):
    guids: List[str]
    missing_guids: List[str]
    language: str
    voice: Optional[str]
    agent: str
    include_forms: bool
    force: bool
    total: int
    generated: int
    skipped_existing: int
    failed: int
    by_guid: Dict[str, GenerateAudioResult]
    tts_cost_usd: float


class GenerateAudioResponse(SuccessResponse):
    data: GenerateAudioData


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
    guid: Optional[str] = None,
    *,
    guids: Optional[List[str]] = None,
    model: Optional[str] = None,
    languages: Optional[List[str]] = None,
) -> AddMissingTranslationsResponse:
    """Generate missing translations for one or more lemmas.

    When ``languages`` is omitted/None, Voras fills all configured generation
    languages. When provided, Voras fills only the requested language codes.

    Returns:
        A typed response envelope with aggregate counts, per-language stats,
        and ``llm_cost_usd`` for the request.
    """
    return cast(
        AddMissingTranslationsResponse,
        post_json(
            "/api/llm/voras/add-missing-translations",
            {"guid": guid, "guids": guids, "model": model, "languages": languages},
        ),
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


@mirrored_route("/api/llm/<agent>/generate-audio", "POST")
def generate_audio(
    agent: str,
    *,
    guids: List[str],
    language: str,
    voice: Optional[str] = None,
    include_forms: bool = False,
    force: bool = False,
) -> GenerateAudioResponse:
    """Generate audio for a list of GUIDs with a selected audio agent."""
    return cast(
        GenerateAudioResponse,
        post_json(
            f"/api/llm/{agent}/generate-audio",
            {
                "guids": guids,
                "language": language,
                "voice": voice,
                "include_forms": include_forms,
                "force": force,
            },
        ),
    )
