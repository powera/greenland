#!/usr/bin/python3

"""API routes for triggering LLM-based agent operations.

This module provides REST API endpoints for triggering LLM agent operations
programmatically, with API keys passed via JSON request parameters rather
than loaded from files. This allows external systems to trigger agent
operations without needing file-based key configuration.

Example request:
    POST /api/llm/papuga/generate-pronunciations
    {
        "lemma_id": 123,
        "lang_code": "en",
        "model": "gpt-5-mini",
        "openai_api_key": "sk-..."
    }
"""

import logging
from typing import Any, Dict, Optional, Tuple, Union

from config import Config
from flask import Blueprint, g, jsonify, request
from flask.typing import ResponseReturnValue

import constants
from agents.lokys import LokysAgent
from agents.papuga import PapugaAgent
from agents.voras.agent import VorasAgent
from wordfreq.storage.backend.config import BackendType, DataSourceConfig
from wordfreq.storage.models.schema import Lemma

bp = Blueprint("llm_api", __name__, url_prefix="/api/llm")
logger = logging.getLogger(__name__)


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
    lemma_id: int,
) -> Union[Tuple[Lemma, None], Tuple[None, ResponseReturnValue]]:
    """Get a lemma by ID or return an error response.

    Returns:
        Tuple of (lemma, None) if found, or (None, error_response) if not found
    """
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        return None, _build_error_response(f"Lemma with ID {lemma_id} not found", 404)
    return lemma, None


@bp.route("/info", methods=["GET"])
def api_info() -> ResponseReturnValue:
    """Get information about available LLM API endpoints."""
    endpoints = [
        {
            "path": "/api/llm/voras/check-translations",
            "method": "POST",
            "description": "Check translations for a lemma using LLM validation",
            "parameters": {
                "lemma_id": "Required. ID of the lemma to check",
                "model": "Optional. LLM model to use (default: gpt-5-mini)",
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
                "lemma_id": "Required. ID of the lemma",
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
                "lemma_id": "Required. ID of the lemma",
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
                "lemma_id": "Required. ID of the lemma",
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
def api_check_translations() -> ResponseReturnValue:
    """Check translations for a lemma using LLM validation.

    Request body (JSON):
        lemma_id: Required. ID of the lemma to check
        model: Optional. LLM model to use (default: gpt-5-mini)
        openai_api_key: Optional. OpenAI API key (for gpt-* models)
        anthropic_api_key: Optional. Anthropic API key (for claude-* models)
        google_api_key: Optional. Google API key (for gemini-* models)

    Returns:
        JSON response with validation results for each translation
    """
    data = request.get_json()
    if not data:
        return _build_error_response("Request body must be JSON")

    lemma_id = data.get("lemma_id")
    if not lemma_id:
        return _build_error_response("lemma_id is required")

    lemma, error = _get_lemma_or_error(lemma_id)
    if error:
        return error
    assert lemma is not None  # Type narrowing for mypy

    try:
        config = _get_config_from_request(data)
        agent = VorasAgent(config=config)

        # Gather translations for this word
        from wordfreq.storage.translation_helpers import LANGUAGE_FIELDS

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
                "lemma_id": lemma_id,
                "lemma_text": lemma.lemma_text,
                "all_valid": all_good,
                "translations_checked": len(translations),
                "issues": issues,
                "validation_results": validation_results,
            }
        )

    except Exception as e:
        logger.exception("Error checking translations for lemma %d", lemma_id)
        return _build_error_response(str(e), 500)


@bp.route("/voras/add-missing-translations", methods=["POST"])
def api_add_missing_translations() -> ResponseReturnValue:
    """Generate missing translations for a lemma.

    Request body (JSON):
        lemma_id: Required. ID of the lemma
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

    lemma_id = data.get("lemma_id")
    if not lemma_id:
        return _build_error_response("lemma_id is required")

    lemma, error = _get_lemma_or_error(lemma_id)
    if error:
        return error
    assert lemma is not None  # Type narrowing for mypy

    try:
        config = _get_config_from_request(data)
        agent = VorasAgent(config=config)

        # Use the agent's fix_missing_translations method with the specific lemma
        result = agent.fix_missing_translations(lemmas=[lemma], dry_run=False)

        g.db.commit()

        return _build_success_response(
            {
                "lemma_id": lemma_id,
                "lemma_text": lemma.lemma_text,
                "total_fixed": result.get("total_fixed", 0),
                "total_failed": result.get("total_failed", 0),
                "by_language": result.get("by_language", {}),
            }
        )

    except Exception as e:
        g.db.rollback()
        logger.exception("Error adding translations for lemma %d", lemma_id)
        return _build_error_response(str(e), 500)


@bp.route("/papuga/generate-pronunciations", methods=["POST"])
def api_generate_pronunciations() -> ResponseReturnValue:
    """Generate pronunciations for a lemma's forms.

    Request body (JSON):
        lemma_id: Required. ID of the lemma
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

    lemma_id = data.get("lemma_id")
    if not lemma_id:
        return _build_error_response("lemma_id is required")

    lang_code = data.get("lang_code", "en")
    only_english = lang_code == "en"

    lemma, error = _get_lemma_or_error(lemma_id)
    if error:
        return error
    assert lemma is not None  # Type narrowing for mypy

    try:
        config = _get_config_from_request(data)
        agent = PapugaAgent(config=config)

        # Generate pronunciations for the lemma using populate_missing_pronunciations
        result = agent.populate_missing_pronunciations(
            lemma_id=lemma_id,
            only_english=only_english,
            only_base_forms=False,
            dry_run=False,
        )

        g.db.commit()

        return _build_success_response(
            {
                "lemma_id": lemma_id,
                "lemma_text": lemma.lemma_text,
                "lang_code": lang_code,
                "populated_count": result.get("populated_count", 0),
                "failed_count": result.get("failed_count", 0),
                "batch_count": result.get("batch_count", 0),
                "single_count": result.get("single_count", 0),
            }
        )

    except Exception as e:
        g.db.rollback()
        logger.exception("Error generating pronunciations for lemma %d", lemma_id)
        return _build_error_response(str(e), 500)


@bp.route("/lokys/check-definition", methods=["POST"])
def api_check_definition() -> ResponseReturnValue:
    """Check/improve the definition of a lemma.

    Request body (JSON):
        lemma_id: Required. ID of the lemma
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

    lemma_id = data.get("lemma_id")
    if not lemma_id:
        return _build_error_response("lemma_id is required")

    lemma, error = _get_lemma_or_error(lemma_id)
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
                "lemma_id": lemma_id,
                "lemma_text": lemma.lemma_text,
                "current_definition": lemma.definition_text,
                "is_valid": result.get("is_valid", False),
                "confidence": result.get("confidence", 0),
                "issues": result.get("issues", []),
                "suggested_definition": result.get("suggested_definition"),
            }
        )

    except Exception as e:
        logger.exception("Error checking definition for lemma %d", lemma_id)
        return _build_error_response(str(e), 500)


@bp.route("/lokys/check-disambiguation", methods=["POST"])
def api_check_disambiguation() -> ResponseReturnValue:
    """Check if a lemma needs disambiguation.

    Request body (JSON):
        lemma_id: Required. ID of the lemma
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

    lemma_id = data.get("lemma_id")
    if not lemma_id:
        return _build_error_response("lemma_id is required")

    lemma, error = _get_lemma_or_error(lemma_id)
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
                "lemma_id": lemma_id,
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
        logger.exception("Error checking disambiguation for lemma %d", lemma_id)
        return _build_error_response(str(e), 500)
