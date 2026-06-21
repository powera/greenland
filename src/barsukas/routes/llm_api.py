#!/usr/bin/python3

"""API routes for triggering LLM-based agent operations.

This module provides REST API endpoints for triggering LLM agent operations
programmatically, with API keys passed via JSON request parameters rather
than loaded from files. This allows external systems to trigger agent
operations without needing file-based key configuration.

Example request:
    POST /api/llm/papuga/generate-pronunciations
    {
        "guid": "N03_003",
        "lang_code": "en",
        "model": "gpt-5.4-mini",
        "openai_api_key": "sk-..."
    }

MIRRORED: routes annotated with ``@mirrored_facade`` have a typed Python
wrapper in the root-level ``api/`` package (``api/llm_agents.py``). Edits
to a mirrored route's path, request body, or response shape MUST be made in
the matching facade in the same commit. See ``api/AGENTS.md``.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

from barsukas.config import Config
from barsukas.routes._mirror import mirrored_facade
from flask import Blueprint, g, jsonify, request
from flask.typing import ResponseReturnValue

import constants
from agents.lokys import LokysAgent
from agents.papuga import PapugaAgent
from agents.strazdas import StrazdasAgent
from agents.vieversys import VieversysAgent
from agents.voras.agent import VorasAgent
from storage.backend.config import BackendType, DataSourceConfig
from storage.models.schema import BarsukasTask, Lemma
from workqueue.task_queue import TaskStatus, TaskType, enqueue_task

from clients.audio.gpt_voices import GptVoice
from clients.keys import load_key

bp = Blueprint("llm_api", __name__, url_prefix="/api/llm")
logger = logging.getLogger(__name__)


@bp.route("/system-key/<provider>", methods=["GET"])
def get_system_api_key(provider: str) -> ResponseReturnValue:
    """Get the system API key for a provider (if available).

    This endpoint allows the API client UI to use locally-configured API keys
    instead of requiring manual entry. Only returns keys that exist in the
    local keys/ directory.

    SECURITY NOTE: This endpoint returns actual API keys. It should only be
    used in trusted environments where both the client and server are under
    the same administrative control.

    Args:
        provider: One of 'openai', 'anthropic', or 'google'

    Returns:
        JSON with the API key if found, or error if not available
    """
    valid_providers = {"openai", "anthropic", "google"}
    if provider not in valid_providers:
        return _build_error_response(
            f"Invalid provider. Must be one of: {', '.join(valid_providers)}", 400
        )

    try:
        api_key = load_key(provider, required=False)
        if api_key:
            return jsonify({"success": True, "provider": provider, "api_key": api_key})
        else:
            return _build_error_response(f"No {provider} API key configured on this server", 404)
    except Exception as e:
        logger.exception("Error loading system API key for %s", provider)
        return _build_error_response(str(e), 500)


def _build_error_response(message: str, status_code: int = 400) -> ResponseReturnValue:
    """Build a standardized error response."""
    return jsonify({"success": False, "error": message}), status_code


def _build_success_response(
    data: Dict[str, Any], message: Optional[str] = None
) -> ResponseReturnValue:
    """Build a standardized success response."""
    response: Dict[str, Any] = {"success": True, "data": data}
    if message:
        response["message"] = message
    return jsonify(response)


def _get_required_language_list(
    data: Dict[str, Any], *, plural_field: str = "languages"
) -> Union[List[str], ResponseReturnValue]:
    """Read a required list of language codes from the JSON payload.

    The server API accepts only the plural list field (``plural_field``); there
    is no singular alias. Single-language callers pass a one-element list. The
    typed Python facade in ``api/llm_agents.py`` may still offer a singular
    ``language`` convenience, but it collapses it to a one-element list before
    sending the request.
    """
    raw_value = data.get(plural_field)
    if raw_value is None:
        return _build_error_response(f"{plural_field} is required")
    if not isinstance(raw_value, list):
        return _build_error_response(f"{plural_field} must be a list of language code strings")
    languages = []
    for item in raw_value:
        if not isinstance(item, str) or not item.strip():
            return _build_error_response(
                f"{plural_field} must contain non-empty language code strings"
            )
        languages.append(item.strip())
    if not languages:
        return _build_error_response(f"{plural_field} is required")
    return languages


def _get_config_from_request(data: Dict[str, Any]) -> DataSourceConfig:
    """Build a DataSourceConfig from request data, including optional API keys.

    Args:
        data: JSON request data containing optional model, API keys, etc.

    Returns:
        DataSourceConfig with API keys injected if provided
    """
    return DataSourceConfig(
        backend_type=BackendType.SQLITE,
        sqlite_path=Config.DB_PATH,
        model=data.get("model", constants.DEFAULT_MODEL),
        debug=data.get("debug", Config.DEBUG),
        openai_api_key=data.get("openai_api_key"),
        anthropic_api_key=data.get("anthropic_api_key"),
        google_api_key=data.get("google_api_key"),
    )


def _get_lemma_or_error(
    guid: str,
) -> Union[Tuple[Lemma, None], Tuple[None, ResponseReturnValue]]:
    """Get a lemma by GUID or return an error response.

    Args:
        guid: The lemma GUID (e.g., "N03_003")

    Returns:
        Tuple of (lemma, None) if found, or (None, error_response) if not found
    """
    lemma = g.db.query(Lemma).filter(Lemma.guid == guid).first()
    if not lemma:
        return None, _build_error_response(f"Lemma with GUID '{guid}' not found", 404)
    return lemma, None


@bp.route("/info", methods=["GET"])
@mirrored_facade("/api/llm/info", "GET")
def api_info() -> ResponseReturnValue:
    """Get information about available LLM API endpoints."""
    endpoints = [
        {
            "path": "/api/llm/voras/check-translations",
            "method": "POST",
            "description": "Check translations for a lemma using LLM validation",
            "parameters": {
                "guid": "Required. GUID of the lemma (e.g., 'N03_003')",
                "model": "Optional. LLM model to use (default: gpt-5.4-mini)",
                "openai_api_key": "Optional. OpenAI API key (for gpt-* models)",
                "anthropic_api_key": "Optional. Anthropic API key (for claude-* models)",
                "google_api_key": "Optional. Google API key (for gemini-* models)",
            },
        },
        {
            "path": "/api/llm/voras/add-missing-translations",
            "method": "POST",
            "description": "Generate missing translations for a lemma",
            "parameters": {
                "guid": "Required. GUID of the lemma (e.g., 'N03_003')",
                "guids": "Optional. List of GUIDs for batch mode",
                "model": "Optional. LLM model to use (any model string exposed by /api/v1/models is accepted)",
                "openai_api_key": "Optional. OpenAI API key",
                "anthropic_api_key": "Optional. Anthropic API key",
                "google_api_key": "Optional. Google API key",
            },
        },
        {
            "path": "/api/llm/papuga/generate-pronunciations",
            "method": "POST",
            "description": "Generate pronunciations for a lemma's forms",
            "parameters": {
                "guid": "Required. GUID of the lemma (e.g., 'N03_003')",
                "lang_code": "Optional. Language code (default: en)",
                "model": "Optional. LLM model to use",
                "openai_api_key": "Optional. OpenAI API key",
                "anthropic_api_key": "Optional. Anthropic API key",
                "google_api_key": "Optional. Google API key",
            },
        },
        {
            "path": "/api/llm/<agent>/generate-audio",
            "method": "POST",
            "description": "Generate lemma audio in bulk using the selected audio agent (vieversys/strazdas)",
            "parameters": {
                "guids": "Required. List of lemma GUIDs",
                "language": "Required. Language code (e.g., 'bs')",
                "voice": "Optional. Voice name for the selected backend/agent. For vieversys/OpenAI, the path_name from /api/v1/audio/voices (e.g. 'amina'); omit to generate all default voices for the language.",
                "include_forms": "Optional bool. Reserved for form-level generation (currently base lemma only)",
                "force": "Optional bool. Reserved for overwrite behavior (currently skipped if manifest already exists)",
            },
        },
        {
            "path": "/api/llm/lokys/check-definition",
            "method": "POST",
            "description": "Check/improve the definition of a lemma",
            "parameters": {
                "guid": "Required. GUID of the lemma (e.g., 'N03_003')",
                "model": "Optional. LLM model to use",
                "openai_api_key": "Optional. OpenAI API key",
                "anthropic_api_key": "Optional. Anthropic API key",
                "google_api_key": "Optional. Google API key",
            },
        },
        {
            "path": "/api/llm/sentences/decompose",
            "method": "POST",
            "description": "Queue sentence decomposition (translation + lemma linking) for a list of sentence IDs. Use batch=true to accumulate IDs across callers before processing.",
            "parameters": {
                "sentence_ids": "Required. List of sentence database IDs (from /api/v1/sentences/add).",
                "model": "Optional. LLM model to use.",
                "batch": "Optional bool (default false). When true, accumulate IDs in a time-windowed task instead of queuing immediately.",
                "batch_window_minutes": "Optional int 1-10 (default 10). Window size when batch=true.",
            },
        },
    ]

    return jsonify(
        {
            "version": "1.0",
            "description": "API for triggering LLM-based agent operations",
            "note": "API keys can be passed in request body to avoid file-based configuration. Model names are passed through to agents; discover configured models via /api/v1/models.",
            "endpoints": endpoints,
        }
    )


@bp.route("/voras/check-translations", methods=["POST"])
@mirrored_facade("/api/llm/voras/check-translations", "POST")
def api_check_translations() -> ResponseReturnValue:
    """Check translations for a lemma using LLM validation.

    Request body (JSON):
        guid: Required. GUID of the lemma (e.g., 'N03_003')
        model: Optional. LLM model to use (default: gpt-5.4-mini)
        openai_api_key: Optional. OpenAI API key (for gpt-* models)
        anthropic_api_key: Optional. Anthropic API key (for claude-* models)
        google_api_key: Optional. Google API key (for gemini-* models)

    Returns:
        JSON response with validation results for each translation
    """
    data = request.get_json()
    if not data:
        return _build_error_response("Request body must be JSON")

    guid = data.get("guid")
    if not guid:
        return _build_error_response("guid is required")

    lemma, error = _get_lemma_or_error(guid)
    if error:
        return error
    assert lemma is not None

    try:
        config = _get_config_from_request(data)
        agent = VorasAgent(config=config)

        # Gather translations for this word
        from storage.translation_helpers import LANGUAGE_FIELDS

        translations = {}
        for lc in LANGUAGE_FIELDS.keys():
            translation = agent.get_translation(g.db, lemma, lc)
            if translation and translation.strip():
                translations[lc] = translation

        if not translations:
            return _build_success_response(
                {"translations": {}, "issues": []},
                message="No translations found to check",
            )

        # Use the LLM validator to check all translations at once
        from wordfreq.tools.llm_validators import validate_all_translations_for_word

        validation_results = validate_all_translations_for_word(
            lemma.lemma_text, translations, lemma.pos_type, config.model
        )

        # Format results
        issues = []
        all_good = True
        for lc, result in validation_results.items():
            has_issues = not result["is_correct"] or not result["is_lemma_form"]
            if has_issues and result["confidence"] >= 0.7:
                all_good = False
                issues.append(
                    {
                        "language_code": lc,
                        "current": translations[lc],
                        "suggested": result["suggested_translation"],
                        "is_correct": result["is_correct"],
                        "is_lemma_form": result["is_lemma_form"],
                        "issues": result["issues"],
                        "confidence": result["confidence"],
                    }
                )

        return _build_success_response(
            {
                "guid": guid,
                "lemma_text": lemma.lemma_text,
                "all_valid": all_good,
                "translations_checked": len(translations),
                "issues": issues,
                "validation_results": validation_results,
            }
        )

    except Exception as e:
        logger.exception("Error checking translations for lemma %s", guid)
        return _build_error_response(str(e), 500)


@bp.route("/voras/add-missing-translations", methods=["POST"])
@mirrored_facade("/api/llm/voras/add-missing-translations", "POST")
def api_add_missing_translations() -> ResponseReturnValue:
    """Generate missing translations for a lemma.

    Request body (JSON):
        guid: Required. GUID of the lemma (e.g., 'N03_003')
        languages: Required. List of language codes (e.g., ["hr", "bs"]). For a
            single language, pass a one-element list (e.g., ["fr"]).
        model: Optional. LLM model to use
        openai_api_key: Optional. OpenAI API key
        anthropic_api_key: Optional. Anthropic API key
        google_api_key: Optional. Google API key

    Returns:
        JSON response with generated translations
    """
    data = request.get_json()
    if not data:
        return _build_error_response("Request body must be JSON")

    guid = data.get("guid")
    guids_raw = data.get("guids")
    guids: List[str] = []
    if guid:
        guids.append(guid)
    if guids_raw is not None:
        if not isinstance(guids_raw, list) or not all(isinstance(item, str) for item in guids_raw):
            return _build_error_response("guids must be a list of GUID strings")
        guids.extend(guids_raw)
    guids = list(dict.fromkeys(guids))
    if not guids:
        return _build_error_response("guid or guids is required")

    languages_result = _get_required_language_list(data)
    if not isinstance(languages_result, list):
        return languages_result
    languages = languages_result

    try:
        from storage.translation_helpers import LANGUAGE_FIELDS

        allowed_languages = set(LANGUAGE_FIELDS.keys())
        if languages is not None:
            unknown_languages = sorted(
                language_code
                for language_code in languages
                if language_code not in allowed_languages
            )
            if unknown_languages:
                return _build_error_response(
                    "Unknown language codes: "
                    + ", ".join(unknown_languages)
                    + ". Allowed codes: "
                    + ", ".join(sorted(allowed_languages))
                )

        config = _get_config_from_request(data)
        agent = VorasAgent(config=config)
        lemmas: List[Lemma] = []
        missing_guids: List[str] = []
        for guid_value in guids:
            lemma = g.db.query(Lemma).filter(Lemma.guid == guid_value).first()
            if lemma is None:
                missing_guids.append(guid_value)
            else:
                lemmas.append(lemma)
        if not lemmas:
            return _build_error_response("No requested GUIDs were found", 404)

        result = agent.fix_missing_translations(
            language_code=languages, lemmas=lemmas, dry_run=False
        )

        g.db.commit()

        return _build_success_response(
            {
                "guids": [lemma.guid for lemma in lemmas],
                "missing_guids": missing_guids,
                "total_fixed": result.get("total_fixed", 0),
                "total_failed": result.get("total_failed", 0),
                "by_language": result.get("by_language", {}),
                "llm_cost_usd": result.get("llm_cost_usd", 0.0),
            }
        )

    except Exception as e:
        g.db.rollback()
        logger.exception("Error adding translations for GUIDs %s", guids)
        return _build_error_response(str(e), 500)


@bp.route("/papuga/generate-pronunciations", methods=["POST"])
@mirrored_facade("/api/llm/papuga/generate-pronunciations", "POST")
def api_generate_pronunciations() -> ResponseReturnValue:
    """Generate pronunciations for a lemma's forms.

    Request body (JSON):
        guid: Required. GUID of the lemma (e.g., 'N03_003')
        lang_code: Optional. Language code (default: en)
        model: Optional. LLM model to use
        openai_api_key: Optional. OpenAI API key
        anthropic_api_key: Optional. Anthropic API key
        google_api_key: Optional. Google API key

    Returns:
        JSON response with generated pronunciations
    """
    data = request.get_json()
    if not data:
        return _build_error_response("Request body must be JSON")

    guid = data.get("guid")
    if not guid:
        return _build_error_response("guid is required")

    lang_code = data.get("lang_code", "en")
    only_english = lang_code == "en"

    lemma, error = _get_lemma_or_error(guid)
    if error:
        return error
    assert lemma is not None  # Type narrowing for mypy

    try:
        config = _get_config_from_request(data)
        agent = PapugaAgent(config=config)

        # Generate pronunciations for the lemma using populate_missing_pronunciations
        result = agent.populate_missing_pronunciations(
            lemma_id=lemma.id,
            only_english=only_english,
            only_base_forms=False,
            dry_run=False,
        )

        g.db.commit()

        return _build_success_response(
            {
                "guid": guid,
                "lemma_text": lemma.lemma_text,
                "lang_code": lang_code,
                "populated_count": result.get("populated_count", result.get("populated", 0)),
                "failed_count": result.get("failed_count", result.get("failed", 0)),
                "batch_count": result.get("batch_count", result.get("batch_calls", 0)),
                "single_count": result.get("single_count", result.get("single_calls", 0)),
            }
        )

    except Exception as e:
        g.db.rollback()
        logger.exception("Error generating pronunciations for lemma %s", guid)
        return _build_error_response(str(e), 500)


@bp.route("/<agent>/generate-audio", methods=["POST"])
@mirrored_facade("/api/llm/<agent>/generate-audio", "POST")
def api_generate_audio(agent: str) -> ResponseReturnValue:
    """Generate lemma audio for a batch of GUIDs via a selected audio agent."""
    data = request.get_json()
    if not data:
        return _build_error_response("Request body must be JSON")

    guids = data.get("guids")
    language_code = data.get("language")
    voice_name = data.get("voice")
    include_forms = bool(data.get("include_forms", False))
    force = bool(data.get("force", False))
    # API callers default to uploading to S3 staging — local-only generation
    # is the exception (one-off debug runs explicitly pass upload_s3=False).
    upload_s3 = bool(data.get("upload_s3", True))
    auto_approve = bool(data.get("auto_approve", False))
    if not isinstance(guids, list) or not all(isinstance(guid_value, str) for guid_value in guids):
        return _build_error_response("guids is required and must be a list of strings")
    if not isinstance(language_code, str) or not language_code:
        return _build_error_response("language is required")

    lemmas = g.db.query(Lemma).filter(Lemma.guid.in_(guids)).all()
    found_guid_set = {lemma.guid for lemma in lemmas}
    missing_guids = [guid_value for guid_value in guids if guid_value not in found_guid_set]

    if not lemmas:
        return _build_error_response("No requested GUIDs were found", 404)

    try:
        config = _get_config_from_request(data)
        if agent == "vieversys":
            vieversys_agent = VieversysAgent(
                config=config, upload_s3=upload_s3, auto_approve=auto_approve
            )
            selected_gpt_voices: Optional[List[GptVoice]] = None
            if isinstance(voice_name, str) and voice_name:
                # OpenAI-backed voices are addressed by their path_name (e.g.
                # "amina"); cloud backends (polly/azure/google) use the raw
                # backend voice id. We try the OpenAI registry first and fall
                # back to passing the string through as a cloud voice id.
                resolved = GptVoice.from_path_name(voice_name, language_code)
                if resolved is not None:
                    selected_gpt_voices = [resolved]
            result = vieversys_agent.generate_batch(
                language_code=language_code,
                lemmas=lemmas,
                voices=selected_gpt_voices,
                cloud_voice_names=(
                    [voice_name]
                    if isinstance(voice_name, str) and voice_name and selected_gpt_voices is None
                    else None
                ),
            )
        elif agent == "strazdas":
            strazdas_agent = StrazdasAgent(config=config, upload_s3=upload_s3)
            result = strazdas_agent.generate_batch(language_code=language_code, lemmas=lemmas)
        else:
            return _build_error_response(
                "Unsupported audio agent. Use 'vieversys' or 'strazdas'", 400
            )

        by_guid: Dict[str, Dict[str, Any]] = {}
        for lemma_result in result.get("lemmas", []):
            guid_value = lemma_result.get("guid")
            if not isinstance(guid_value, str):
                continue
            if lemma_result.get("success"):
                by_guid[guid_value] = {"status": "generated"}
            else:
                by_guid[guid_value] = {"status": "failed", "error": lemma_result.get("error")}

        generated = int(result.get("success_count", 0))
        failed = int(result.get("error_count", 0))
        total = len(guids)
        skipped_existing = max(total - generated - failed, 0)

        return _build_success_response(
            {
                "guids": guids,
                "missing_guids": missing_guids,
                "language": language_code,
                "voice": voice_name,
                "agent": agent,
                "include_forms": include_forms,
                "force": force,
                "total": total,
                "generated": generated,
                "skipped_existing": skipped_existing,
                "failed": failed,
                "by_guid": by_guid,
                "tts_cost_usd": 0.0,
            }
        )
    except Exception as e:
        logger.exception("Error generating audio with agent=%s", agent)
        return _build_error_response(str(e), 500)


@bp.route("/lokys/check-definition", methods=["POST"])
@mirrored_facade("/api/llm/lokys/check-definition", "POST")
def api_check_definition() -> ResponseReturnValue:
    """Check/improve the definition of a lemma.

    Request body (JSON):
        guid: Required. GUID of the lemma (e.g., 'N03_003')
        model: Optional. LLM model to use
        openai_api_key: Optional. OpenAI API key
        anthropic_api_key: Optional. Anthropic API key
        google_api_key: Optional. Google API key

    Returns:
        JSON response with definition validation results and suggestions
    """
    data = request.get_json()
    if not data:
        return _build_error_response("Request body must be JSON")

    guid = data.get("guid")
    if not guid:
        return _build_error_response("guid is required")

    lemma, error = _get_lemma_or_error(guid)
    if error:
        return error
    assert lemma is not None  # Type narrowing for mypy

    try:
        config = _get_config_from_request(data)
        agent = LokysAgent(config=config)

        # Use the agent's helper method
        result = agent.check_single_definition(lemma, session=g.db)

        return _build_success_response(
            {
                "guid": guid,
                "lemma_text": lemma.lemma_text,
                "current_definition": lemma.definition_text,
                "is_valid": result.get("is_valid", False),
                "confidence": result.get("confidence", 0),
                "issues": result.get("issues", []),
                "suggested_definition": result.get("suggested_definition"),
            }
        )

    except Exception as e:
        logger.exception("Error checking definition for lemma %s", guid)
        return _build_error_response(str(e), 500)


@bp.route("/lokys/check-disambiguation", methods=["POST"])
@mirrored_facade("/api/llm/lokys/check-disambiguation", "POST")
def api_check_disambiguation() -> ResponseReturnValue:
    """Check if a lemma needs disambiguation.

    Request body (JSON):
        guid: Required. GUID of the lemma (e.g., 'N03_003')
        model: Optional. LLM model to use
        openai_api_key: Optional. OpenAI API key
        anthropic_api_key: Optional. Anthropic API key
        google_api_key: Optional. Google API key

    Returns:
        JSON response with disambiguation analysis and suggestions
    """
    data = request.get_json()
    if not data:
        return _build_error_response("Request body must be JSON")

    guid = data.get("guid")
    if not guid:
        return _build_error_response("guid is required")

    lemma, error = _get_lemma_or_error(guid)
    if error:
        return error
    assert lemma is not None  # Type narrowing for mypy

    try:
        config = _get_config_from_request(data)
        agent = LokysAgent(config=config)

        # Use the agent's helper method
        result = agent.check_single_disambiguation(lemma, session=g.db)

        return _build_success_response(
            {
                "guid": guid,
                "lemma_text": lemma.lemma_text,
                "needs_disambiguation": result.get("needs_disambiguation", False),
                "reason": result.get("reason"),
                "has_parenthetical": result.get("has_parenthetical", False),
                "duplicate_count": result.get("duplicate_count", 0),
                "duplicates": result.get("duplicates", []),
                "llm_suggestions": result.get("llm_suggestions", {}),
            }
        )

    except Exception as e:
        logger.exception("Error checking disambiguation for lemma %s", guid)
        return _build_error_response(str(e), 500)


_DECOMPOSE_SENTENCES_MAX = 15
_DECOMPOSE_LANGUAGES: List[str] = ["fr", "zh", "lt", "es", "bn", "uk", "kn"]


@bp.route("/sentences/decompose", methods=["POST"])
@mirrored_facade("/api/llm/sentences/decompose", "POST")
def decompose_sentences() -> ResponseReturnValue:
    """Queue sentence decomposition (translation + lemma linking) for a list of sentences.

    Each sentence must already exist in the database (create them first via
    ``POST /api/v1/sentences/add``). The queued task calls ``translate_sentence``
    which produces translations and per-word lemma associations for English,
    French, Chinese, Lithuanian, and Spanish.

    With ``batch=false`` (default) each sentence ID is queued as an individual
    task and processed as soon as the worker is free.

    With ``batch=true`` the IDs are accumulated into a single time-windowed task
    shared by all callers within ``batch_window_minutes`` minutes. The response
    is immediate; the task runs after the window closes (or when the worker picks
    it up).

    Request body (JSON):
        sentence_ids (list[int], required): Up to 15 sentence IDs from /api/v1/sentences/add.
        model (str, optional): LLM model to use (default: system default).
        batch (bool, optional): Whether to accumulate into a shared batch task (default: false).
        batch_window_minutes (int, optional): Batch window size in minutes 1-10 (default: 10).

    Returns (non-batch):
        data.queued_count: number of tasks enqueued
        data.task_ids: list of BarsukasTask IDs created

    Returns (batch):
        data.batched: true
        data.batch_task_id: ID of the shared batch task
        data.sentence_ids_added: number of IDs merged into the batch
    """
    data = request.get_json(silent=True) or {}

    sentence_ids_raw = data.get("sentence_ids")
    if not isinstance(sentence_ids_raw, list) or not sentence_ids_raw:
        return _build_error_response("sentence_ids must be a non-empty list")
    if len(sentence_ids_raw) > _DECOMPOSE_SENTENCES_MAX:
        return _build_error_response(
            f"sentence_ids may contain at most {_DECOMPOSE_SENTENCES_MAX} items"
        )
    sentence_ids: List[int] = []
    for item in sentence_ids_raw:
        if not isinstance(item, int):
            return _build_error_response("each sentence_id must be an integer")
        sentence_ids.append(item)

    model_raw = data.get("model", constants.DEFAULT_MODEL)
    if not isinstance(model_raw, str) or not model_raw.strip():
        return _build_error_response("model must be a non-empty string")
    model = model_raw.strip()

    use_batch = bool(data.get("batch", False))
    batch_window_minutes_raw = data.get("batch_window_minutes", 10)
    try:
        batch_window_minutes = int(batch_window_minutes_raw)
    except (TypeError, ValueError):
        return _build_error_response("batch_window_minutes must be an integer")
    if batch_window_minutes < 1 or batch_window_minutes > 10:
        return _build_error_response("batch_window_minutes must be between 1 and 10")

    if not use_batch:
        task_ids: List[int] = []
        for sid in sentence_ids:
            result = enqueue_task(
                g.db,
                task_type=TaskType.SENTENCES_TRANSLATE,
                target_type="sentence",
                target_id=sid,
                payload={
                    "sentence_id": sid,
                    "selected_languages": _DECOMPOSE_LANGUAGES,
                    "model": model,
                },
                dedup_key=f"{TaskType.SENTENCES_TRANSLATE}:{sid}",
            )
            task_ids.append(result.task.id)
        return _build_success_response(
            {"queued_count": len(task_ids), "task_ids": task_ids},
            f"Queued {len(task_ids)} sentence decomposition task(s)",
        )

    window_index = int(datetime.utcnow().timestamp() // (batch_window_minutes * 60))
    batch_dedup_key = (
        f"{TaskType.SENTENCES_TRANSLATE_BATCH_SUBMIT}:batch:"
        f"{window_index}:{batch_window_minutes}:{model}"
    )
    existing = (
        g.db.query(BarsukasTask)
        .filter(
            BarsukasTask.dedup_key == batch_dedup_key,
            BarsukasTask.status.in_(TaskStatus.ACTIVE),
            BarsukasTask.created_at >= datetime.utcnow() - timedelta(minutes=batch_window_minutes),
        )
        .order_by(BarsukasTask.created_at.desc())
        .first()
    )
    if existing:
        existing_payload = json.loads(existing.payload or "{}")
        accumulated = set(existing_payload.get("sentence_ids", []))
        accumulated.update(sentence_ids)
        existing_payload["sentence_ids"] = sorted(accumulated)
        existing.payload = json.dumps(existing_payload)
        g.db.flush()
        return _build_success_response(
            {
                "batched": True,
                "batch_task_id": existing.id,
                "sentence_ids_added": len(sentence_ids),
            },
            f"Added {len(sentence_ids)} sentence ID(s) to batch task {existing.id}",
        )

    result = enqueue_task(
        g.db,
        task_type=TaskType.SENTENCES_TRANSLATE_BATCH_SUBMIT,
        target_type="batch",
        target_id=None,
        payload={
            "sentence_ids": sentence_ids,
            "selected_languages": _DECOMPOSE_LANGUAGES,
            "model": model,
        },
        dedup_key=batch_dedup_key,
    )
    return _build_success_response(
        {
            "batched": True,
            "batch_task_id": result.task.id,
            "sentence_ids_added": len(sentence_ids),
        },
        f"Created batch task {result.task.id} with {len(sentence_ids)} sentence ID(s)",
    )


def _accumulate_or_enqueue_batch(
    *,
    task_type: str,
    coalesce_key: str,
    batch_window_minutes: int,
    payload_template: Dict[str, Any],
    sentence_ids: List[int],
    languages_field: Optional[str] = None,
) -> ResponseReturnValue:
    """Coalesce batch-phase enqueues within a time window.

    The ``coalesce_key`` is a bucket identifier (window + model), not a
    correctness key — different callers within the window merge into the same
    workqueue task. ``sentence_ids`` are unioned across callers, and if
    ``languages_field`` is given, that payload list is unioned too so the
    handler sees the combined language set requested by all callers. Per-sentence
    idempotency (skipping languages already produced) is the handler's job.
    """
    existing = (
        g.db.query(BarsukasTask)
        .filter(
            BarsukasTask.dedup_key == coalesce_key,
            BarsukasTask.status.in_(TaskStatus.ACTIVE),
            BarsukasTask.created_at >= datetime.utcnow() - timedelta(minutes=batch_window_minutes),
        )
        .order_by(BarsukasTask.created_at.desc())
        .first()
    )
    if existing:
        existing_payload = json.loads(existing.payload or "{}")
        accumulated_ids = set(existing_payload.get("sentence_ids", []))
        accumulated_ids.update(sentence_ids)
        existing_payload["sentence_ids"] = sorted(accumulated_ids)
        if languages_field:
            accumulated_langs = set(existing_payload.get(languages_field, []))
            accumulated_langs.update(payload_template.get(languages_field, []))
            existing_payload[languages_field] = sorted(accumulated_langs)
        existing.payload = json.dumps(existing_payload)
        g.db.flush()
        return _build_success_response(
            {
                "batched": True,
                "batch_task_id": existing.id,
                "sentence_ids_added": len(sentence_ids),
            },
            f"Added {len(sentence_ids)} sentence ID(s) to batch task {existing.id}",
        )

    payload = dict(payload_template)
    payload["sentence_ids"] = sentence_ids
    result = enqueue_task(
        g.db,
        task_type=task_type,
        target_type="batch",
        target_id=None,
        payload=payload,
        dedup_key=coalesce_key,
    )
    return _build_success_response(
        {
            "batched": True,
            "batch_task_id": result.task.id,
            "sentence_ids_added": len(sentence_ids),
        },
        f"Created batch task {result.task.id} with {len(sentence_ids)} sentence ID(s)",
    )


_BATCH_TRANSLATE_DEFAULT_TARGETS: List[str] = ["fr", "lt", "zh", "es", "bn", "uk", "kn"]


@bp.route("/sentences/batch_translate", methods=["POST"])
@mirrored_facade("/api/llm/sentences/batch_translate", "POST")
def batch_translate_sentences() -> ResponseReturnValue:
    """Queue Phase-1 sentence-level translations as an OpenAI Batch job.

    Phase 1 produces only ``SentenceTranslation`` rows (no per-word breakdown).
    The default target set covers every language used by the Phase-2 candidate-
    lemma lookup (``DEFAULT_SOURCE_LANGUAGES``) so a follow-up
    ``/sentences/batch_decompose`` call has rich data to score against.

    Request body (JSON):
        sentence_ids (list[int], required): Up to 15 sentence IDs.
        target_languages (list[str], optional): Languages to translate into.
            Defaults to ``["fr","lt","zh","es","bn","uk","kn"]``.
        model (str, optional): LLM model (default: system default).
        batch_window_minutes (int, optional): Batch window 1-10 (default: 10).

    Returns:
        data.batched: true
        data.batch_task_id: ID of the shared workqueue task
        data.sentence_ids_added: how many IDs joined the task
    """
    data = request.get_json(silent=True) or {}

    sentence_ids_raw = data.get("sentence_ids")
    if not isinstance(sentence_ids_raw, list) or not sentence_ids_raw:
        return _build_error_response("sentence_ids must be a non-empty list")
    if len(sentence_ids_raw) > _DECOMPOSE_SENTENCES_MAX:
        return _build_error_response(
            f"sentence_ids may contain at most {_DECOMPOSE_SENTENCES_MAX} items"
        )
    sentence_ids: List[int] = []
    for item in sentence_ids_raw:
        if not isinstance(item, int):
            return _build_error_response("each sentence_id must be an integer")
        sentence_ids.append(item)

    target_languages_result = _get_required_language_list(data, plural_field="target_languages")
    if not isinstance(target_languages_result, list):
        return target_languages_result
    target_languages = target_languages_result

    model_raw = data.get("model", constants.DEFAULT_MODEL)
    if not isinstance(model_raw, str) or not model_raw.strip():
        return _build_error_response("model must be a non-empty string")
    model = model_raw.strip()

    batch_window_minutes_raw = data.get("batch_window_minutes", 10)
    try:
        batch_window_minutes = int(batch_window_minutes_raw)
    except (TypeError, ValueError):
        return _build_error_response("batch_window_minutes must be an integer")
    if batch_window_minutes < 1 or batch_window_minutes > 10:
        return _build_error_response("batch_window_minutes must be between 1 and 10")

    from storage.translation_helpers import split_llm_language_batches

    window_index = int(datetime.utcnow().timestamp() // (batch_window_minutes * 60))
    language_batches = split_llm_language_batches(target_languages)
    responses: List[ResponseReturnValue] = []
    for language_batch in language_batches:
        languages_key = ":".join(language_batch)
        coalesce_key = (
            f"{TaskType.SENTENCES_BATCH_TRANSLATE_SUBMIT}:batch:"
            f"{window_index}:{batch_window_minutes}:{model}:{languages_key}"
        )
        responses.append(
            _accumulate_or_enqueue_batch(
                task_type=TaskType.SENTENCES_BATCH_TRANSLATE_SUBMIT,
                coalesce_key=coalesce_key,
                batch_window_minutes=batch_window_minutes,
                payload_template={
                    "target_languages": language_batch,
                    "model": model,
                },
                sentence_ids=sentence_ids,
                languages_field=None,
            )
        )

    if len(responses) == 1:
        return responses[0]

    return _build_success_response(
        {
            "batched": True,
            "batch_count": len(responses),
            "sentence_ids_added": len(sentence_ids),
            "language_batches": language_batches,
        },
        f"Created/updated {len(responses)} batch task(s)",
    )


_BATCH_DECOMPOSE_DEFAULT_TARGETS: List[str] = ["en", "fr", "zh", "lt", "es"]
_BATCH_DECOMPOSE_REQUIRED_LOOKUP: List[str] = [
    "en",
    "fr",
    "lt",
    "zh",
    "es",
    "bn",
    "uk",
    "kn",
]


@bp.route("/sentences/batch_decompose", methods=["POST"])
@mirrored_facade("/api/llm/sentences/batch_decompose", "POST")
def batch_decompose_sentences() -> ResponseReturnValue:
    """Queue Phase-3 per-word decomposition as an OpenAI Batch job.

    Requires that every sentence already has ``SentenceTranslation`` rows for
    each of the ``decompose_languages`` plus the candidate-lookup pool
    (``en, fr, lt, zh, es, bn, uk, kn``). If any are missing, returns ``400``
    with ``data.missing`` describing what's needed — call
    ``/sentences/batch_translate`` first.

    Request body (JSON):
        sentence_ids (list[int], required): Up to 15 sentence IDs.
        decompose_languages (list[str], optional): Languages to produce per-word
            breakdowns for. Defaults to ``["en","fr","zh","lt","es"]``.
        model (str, optional): LLM model (default: system default).
        batch_window_minutes (int, optional): Batch window 1-10 (default: 10).

    Returns:
        data.batched: true
        data.batch_task_id: ID of the shared workqueue task
        data.sentence_ids_added: how many IDs joined the task
    """
    from storage.models.schema import Sentence, SentenceTranslation

    data = request.get_json(silent=True) or {}

    sentence_ids_raw = data.get("sentence_ids")
    if not isinstance(sentence_ids_raw, list) or not sentence_ids_raw:
        return _build_error_response("sentence_ids must be a non-empty list")
    if len(sentence_ids_raw) > _DECOMPOSE_SENTENCES_MAX:
        return _build_error_response(
            f"sentence_ids may contain at most {_DECOMPOSE_SENTENCES_MAX} items"
        )
    sentence_ids = []
    for item in sentence_ids_raw:
        if not isinstance(item, int):
            return _build_error_response("each sentence_id must be an integer")
        sentence_ids.append(item)

    decompose_raw = data.get("decompose_languages")
    if decompose_raw is None:
        decompose_languages = list(_BATCH_DECOMPOSE_DEFAULT_TARGETS)
    else:
        if not isinstance(decompose_raw, list) or not decompose_raw:
            return _build_error_response(
                "decompose_languages must be a non-empty list when provided"
            )
        decompose_languages = []
        for item in decompose_raw:
            if not isinstance(item, str) or not item.strip():
                return _build_error_response("each decompose_language must be a non-empty string")
            decompose_languages.append(item.strip())

    model_raw = data.get("model", constants.DEFAULT_MODEL)
    if not isinstance(model_raw, str) or not model_raw.strip():
        return _build_error_response("model must be a non-empty string")
    model = model_raw.strip()

    batch_window_minutes_raw = data.get("batch_window_minutes", 10)
    try:
        batch_window_minutes = int(batch_window_minutes_raw)
    except (TypeError, ValueError):
        return _build_error_response("batch_window_minutes must be an integer")
    if batch_window_minutes < 1 or batch_window_minutes > 10:
        return _build_error_response("batch_window_minutes must be between 1 and 10")

    required_languages = sorted(set(decompose_languages) | set(_BATCH_DECOMPOSE_REQUIRED_LOOKUP))
    missing: List[Dict[str, Any]] = []
    for sid in sentence_ids:
        sentence = g.db.get(Sentence, sid)
        if sentence is None:
            missing.append({"sentence_id": sid, "error": "not_found"})
            continue
        existing = {
            row.language_code
            for row in g.db.query(SentenceTranslation).filter_by(sentence_id=sid).all()
        }
        absent = [lang for lang in required_languages if lang not in existing]
        if absent:
            missing.append({"sentence_id": sid, "missing_languages": absent})

    if missing:
        response = jsonify(
            {
                "success": False,
                "error": "missing translations; run /api/llm/sentences/batch_translate first",
                "data": {"missing": missing, "required_languages": required_languages},
            }
        )
        response.status_code = 400
        return response

    window_index = int(datetime.utcnow().timestamp() // (batch_window_minutes * 60))
    coalesce_key = (
        f"{TaskType.SENTENCES_BATCH_DECOMPOSE_SUBMIT}:batch:"
        f"{window_index}:{batch_window_minutes}:{model}"
    )

    return _accumulate_or_enqueue_batch(
        task_type=TaskType.SENTENCES_BATCH_DECOMPOSE_SUBMIT,
        coalesce_key=coalesce_key,
        batch_window_minutes=batch_window_minutes,
        payload_template={
            "decompose_languages": decompose_languages,
            "model": model,
        },
        sentence_ids=sentence_ids,
        languages_field="decompose_languages",
    )
