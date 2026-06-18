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
    language: Optional[str] = None,
    languages: Optional[List[str]] = None,
    timeout: Optional[float] = None,
) -> AddMissingTranslationsResponse:
    """Generate missing translations for one or more lemmas.

    Pass either ``language`` for one target language or ``languages`` for several target language codes.

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
            {
                "guid": guid,
                "guids": guids,
                "model": model,
                "language": language,
                "languages": languages,
            },
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


@mirrored_route("/api/llm/sentences/decompose", "POST")
def decompose_sentences(
    sentence_ids: List[int],
    *,
    model: Optional[str] = None,
    batch: bool = False,
    batch_window_minutes: int = 10,
) -> Any:
    """Queue sentence decomposition (translation + lemma linking) for a list of sentence IDs.

    Sentences must already exist in the database — create them first with
    :func:`api.sentences.add_sentences` and use the returned IDs here.

    The queued task translates each sentence into French, Chinese, Lithuanian,
    and Spanish and builds per-word lemma associations. English word breakdown
    is also produced when no English words exist yet.

    With ``batch=False`` (default) each sentence gets its own task queued
    immediately.

    With ``batch=True`` the IDs are added to a shared time-windowed task.
    Multiple callers within the same window contribute their IDs to the same
    task, which is processed once the worker picks it up. The response is
    immediate; there is no synchronous LLM call.

    Args:
        sentence_ids: List of sentence database IDs (max 15).
        model: LLM model to use (default: system default).
        batch: Whether to accumulate IDs in a time-windowed batch task.
        batch_window_minutes: Window size in minutes 1-10 (default: 10).

    Returns:
        API response dict. Non-batch: ``data.queued_count`` and ``data.task_ids``.
        Batch: ``data.batched``, ``data.batch_task_id``, ``data.sentence_ids_added``.
    """
    body: Dict[str, Any] = {
        "sentence_ids": sentence_ids,
        "batch": batch,
        "batch_window_minutes": batch_window_minutes,
    }
    if model is not None:
        body["model"] = model
    return post_json("/api/llm/sentences/decompose", body)


@mirrored_route("/api/llm/sentences/batch_translate", "POST")
def batch_translate_sentences(
    sentence_ids: List[int],
    *,
    target_languages: Optional[List[str]] = None,
    model: Optional[str] = None,
    batch_window_minutes: int = 10,
) -> Any:
    """Queue Phase-1 sentence translations as a shared OpenAI Batch job.

    Produces sentence-level translations only — no per-word breakdown. Call
    :func:`batch_decompose_sentences` afterwards (once the batch poller has
    applied results) to produce ``SentenceWord`` rows.

    Args:
        sentence_ids: Sentence IDs (max 15).
        target_languages: Required languages to translate into.
        model: LLM model id (default: system default).
        batch_window_minutes: Shared-batch window 1-10 (default: 10).

    Returns:
        API response dict with ``data.batch_task_id`` / ``data.sentence_ids_added``.
    """
    body: Dict[str, Any] = {
        "sentence_ids": sentence_ids,
        "batch_window_minutes": batch_window_minutes,
    }
    if target_languages is not None:
        body["target_languages"] = target_languages
    if model is not None:
        body["model"] = model
    return post_json("/api/llm/sentences/batch_translate", body)


@mirrored_route("/api/llm/sentences/batch_decompose", "POST")
def batch_decompose_sentences(
    sentence_ids: List[int],
    *,
    decompose_languages: Optional[List[str]] = None,
    model: Optional[str] = None,
    batch_window_minutes: int = 10,
) -> Any:
    """Queue Phase-3 per-word decomposition as a shared OpenAI Batch job.

    Every sentence must already have ``SentenceTranslation`` rows for the
    requested ``decompose_languages`` and for the full candidate-lookup pool
    (en/fr/lt/zh/es/bn/uk/kn). Missing translations cause an HTTP 400 with
    ``data.missing`` describing what's absent; in that case run
    :func:`batch_translate_sentences` first.

    Args:
        sentence_ids: Sentence IDs (max 15).
        decompose_languages: Languages whose words to break down. Defaults to
            ``["en","fr","zh","lt","es"]``.
        model: LLM model id (default: system default).
        batch_window_minutes: Shared-batch window 1-10 (default: 10).
    """
    body: Dict[str, Any] = {
        "sentence_ids": sentence_ids,
        "batch_window_minutes": batch_window_minutes,
    }
    if decompose_languages is not None:
        body["decompose_languages"] = decompose_languages
    if model is not None:
        body["model"] = model
    return post_json("/api/llm/sentences/batch_decompose", body)
