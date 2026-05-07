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
def check_translations(
    guid: str, *, model: Optional[str] = None, timeout: Optional[float] = None
) -> Any:
    """Trigger Voras translation validation for one lemma.

    ``timeout`` overrides the default HTTP read timeout; pass a longer value
    for slow LLM calls.
    """
    kwargs: Dict[str, Any] = {} if timeout is None else {"timeout": timeout}
    return post_json(
        "/api/llm/voras/check-translations",
        {"guid": guid, "model": model},
        **kwargs,
    )


@mirrored_route("/api/llm/voras/add-missing-translations", "POST")
def add_missing_translations(
    guid: Optional[str] = None,
    *,
    guids: Optional[List[str]] = None,
    model: Optional[str] = None,
    languages: Optional[List[str]] = None,
    timeout: Optional[float] = None,
) -> AddMissingTranslationsResponse:
    """Generate missing translations for one or more lemmas.

    When ``languages`` is omitted/None, Voras fills all configured generation
    languages. When provided, Voras fills only the requested language codes.

    ``timeout`` overrides the default HTTP read timeout; pass a longer value
    for bulk requests.

    Returns:
        A typed response envelope with aggregate counts, per-language stats,
        and ``llm_cost_usd`` for the request.
    """
    kwargs: Dict[str, Any] = {} if timeout is None else {"timeout": timeout}
    return cast(
        AddMissingTranslationsResponse,
        post_json(
            "/api/llm/voras/add-missing-translations",
            {"guid": guid, "guids": guids, "model": model, "languages": languages},
            **kwargs,
        ),
    )


@mirrored_route("/api/llm/papuga/generate-pronunciations", "POST")
def generate_pronunciations(
    guid: str,
    *,
    lang_code: str = "en",
    model: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Any:
    """Generate pronunciations for a lemma's forms in ``lang_code``.

    ``timeout`` overrides the default HTTP read timeout.
    """
    kwargs: Dict[str, Any] = {} if timeout is None else {"timeout": timeout}
    return post_json(
        "/api/llm/papuga/generate-pronunciations",
        {"guid": guid, "lang_code": lang_code, "model": model},
        **kwargs,
    )


@mirrored_route("/api/llm/lokys/check-definition", "POST")
def check_definition(
    guid: str, *, model: Optional[str] = None, timeout: Optional[float] = None
) -> Any:
    """Check / improve the definition of a lemma.

    ``timeout`` overrides the default HTTP read timeout.
    """
    kwargs: Dict[str, Any] = {} if timeout is None else {"timeout": timeout}
    return post_json(
        "/api/llm/lokys/check-definition",
        {"guid": guid, "model": model},
        **kwargs,
    )


@mirrored_route("/api/llm/lokys/check-disambiguation", "POST")
def check_disambiguation(
    guid: str, *, model: Optional[str] = None, timeout: Optional[float] = None
) -> Any:
    """Check / improve the disambiguation of a lemma.

    ``timeout`` overrides the default HTTP read timeout.
    """
    kwargs: Dict[str, Any] = {} if timeout is None else {"timeout": timeout}
    return post_json(
        "/api/llm/lokys/check-disambiguation",
        {"guid": guid, "model": model},
        **kwargs,
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
    upload_s3: bool = True,
    auto_approve: bool = False,
    timeout: Optional[float] = None,
) -> GenerateAudioResponse:
    """Generate audio for a list of GUIDs with a selected audio agent.

    Known audio agents (see src/agents/README.md):
      - "vieversys" — OpenAI TTS (gpt-4o-mini-tts). Use this for cloud-quality
        audio. Also supports polly/azure/google via server-side config.
      - "strazdas" — eSpeak-NG (offline, robotic).

    ``voice`` selects a single voice (use the ``voice_name`` returned by
    :func:`api.audio.list_voices`, e.g. ``"amina"``). Omit it to generate
    every default voice configured for the language — for vieversys/OpenAI
    that is the primary male and female voice (gpt-<lang>-m1, gpt-<lang>-f1).

    ``upload_s3`` defaults to True: API callers almost always want generated
    audio uploaded to S3 staging so it is reachable by the rest of the
    pipeline. Pass ``False`` only for one-off local debug runs.

    ``auto_approve`` requires ``upload_s3=True`` (vieversys only); when set,
    generated audio is approved immediately rather than queued for review.

    ``timeout`` overrides the default HTTP read timeout; bulk audio requests
    typically need several minutes.
    """
    kwargs: Dict[str, Any] = {} if timeout is None else {"timeout": timeout}
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
                "upload_s3": upload_s3,
                "auto_approve": auto_approve,
            },
            **kwargs,
        ),
    )
