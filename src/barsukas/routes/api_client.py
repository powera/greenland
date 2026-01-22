#!/usr/bin/python3

"""Web UI for making LLM API calls to remote BARSUKAS servers.

This provides a web interface similar to the agent launcher, but for
triggering LLM API operations on remote (or local) BARSUKAS instances.
"""

import logging

from flask import Blueprint, render_template
from flask.typing import ResponseReturnValue

bp = Blueprint("api_client", __name__, url_prefix="/api-client")
logger = logging.getLogger(__name__)


@bp.route("/")
def api_client_ui() -> ResponseReturnValue:
    """Render the LLM API client interface."""
    # Available endpoints with their parameters
    endpoints = [
        {
            "id": "check-translations",
            "name": "Check Translations (Voras)",
            "path": "/api/llm/voras/check-translations",
            "description": "Validate existing translations for a lemma using LLM",
            "params": [
                {"name": "guid", "type": "text", "required": True, "label": "GUID (e.g. N03_003)"},
            ],
        },
        {
            "id": "add-translations",
            "name": "Add Missing Translations (Voras)",
            "path": "/api/llm/voras/add-missing-translations",
            "description": "Generate missing translations for a lemma",
            "params": [
                {"name": "guid", "type": "text", "required": True, "label": "GUID (e.g. N03_003)"},
            ],
        },
        {
            "id": "generate-pronunciations",
            "name": "Generate Pronunciations (Papuga)",
            "path": "/api/llm/papuga/generate-pronunciations",
            "description": "Generate IPA and phonetic pronunciations for a lemma's forms",
            "params": [
                {"name": "guid", "type": "text", "required": True, "label": "GUID (e.g. N03_003)"},
                {
                    "name": "lang_code",
                    "type": "select",
                    "required": False,
                    "label": "Language",
                    "options": [("en", "English"), ("lt", "Lithuanian"), ("fr", "French")],
                    "default": "en",
                },
            ],
        },
        {
            "id": "check-definition",
            "name": "Check Definition (Lokys)",
            "path": "/api/llm/lokys/check-definition",
            "description": "Check and suggest improvements for a lemma's definition",
            "params": [
                {"name": "guid", "type": "text", "required": True, "label": "GUID (e.g. N03_003)"},
            ],
        },
        {
            "id": "check-disambiguation",
            "name": "Check Disambiguation (Lokys)",
            "path": "/api/llm/lokys/check-disambiguation",
            "description": "Check if a lemma needs disambiguation (parentheticals)",
            "params": [
                {"name": "guid", "type": "text", "required": True, "label": "GUID (e.g. N03_003)"},
            ],
        },
    ]

    # Available models
    models = [
        ("gpt-5-mini", "GPT-5 Mini (OpenAI)"),
        ("gpt-4o-mini", "GPT-4o Mini (OpenAI)"),
        ("claude-3-5-haiku-20241022", "Claude 3.5 Haiku (Anthropic)"),
        ("claude-3-7-sonnet-20250219", "Claude 3.7 Sonnet (Anthropic)"),
        ("gemini-2.5-flash", "Gemini 2.5 Flash (Google)"),
    ]

    return render_template(
        "api_client/index.html",
        endpoints=endpoints,
        models=models,
    )
