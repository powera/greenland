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

import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from barsukas.config import Config
from barsukas.routes._mirror import mirrored_facade
from flask import Blueprint, g, jsonify, request
from flask.typing import ResponseReturnValue

import constants
from agents.lokys import LokysAgent
from agents.papuga import PapugaAgent
from agents.voras.agent import VorasAgent
from storage.backend.config import BackendType, DataSourceConfig
from storage.models.schema import Lemma

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
                "model": "Optional. LLM model to use",
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
    ]

    return jsonify(
        {
            "version": "1.0",
            "description": "API for triggering LLM-based agent operations",
            "note": "API keys can be passed in request body to avoid file-based configuration",
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
    assert lemma is not None  # Type narrowing for mypy

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
        languages: Optional list of language codes (e.g., ["hr", "bs"]).
            When omitted/null, uses all configured Voras generation languages.
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
    if not guid:
        return _build_error_response("guid is required")

    languages_raw = data.get("languages")
    languages: Optional[List[str]]
    if languages_raw is None:
        languages = None
    else:
        if not isinstance(languages_raw, list) or not all(
            isinstance(language_code, str) for language_code in languages_raw
        ):
            return _build_error_response("languages must be a list of language code strings")
        languages = languages_raw

    lemma, error = _get_lemma_or_error(guid)
    if error:
        return error
    assert lemma is not None  # Type narrowing for mypy

    try:
        from storage.translation_helpers import get_tier_1_and_tier_2_languages

        allowed_languages = set(get_tier_1_and_tier_2_languages())
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

        # Use the agent's fix_missing_translations method with the specific lemma
        result = agent.fix_missing_translations(
            language_code=languages,
            lemmas=[lemma],
            dry_run=False,
        )

        g.db.commit()

        return _build_success_response(
            {
                "guid": guid,
                "lemma_text": lemma.lemma_text,
                "total_fixed": result.get("total_fixed", 0),
                "total_failed": result.get("total_failed", 0),
                "by_language": result.get("by_language", {}),
            }
        )

    except Exception as e:
        g.db.rollback()
        logger.exception("Error adding translations for lemma %s", guid)
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
