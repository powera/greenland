#!/usr/bin/python3

"""Verbalator routes - custom LLM query interface."""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, g, render_template, request, jsonify

# Add src to path if not already present
if str(Path(__file__).parent.parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import util.flesch_kincaid as fk
from benchmarks.datastore.common import Model
from benchmarks.verbalator import common, prompt_builder, samples
from clients.unified_client import UnifiedLLMClient as UnifiedClient

bp = Blueprint(
    "verbalator",
    __name__,
    url_prefix="/verbalator",
)

DEFAULT_MODEL = "gpt-5-mini"

_unified_client: Optional[UnifiedClient] = None


def _get_unified_client() -> UnifiedClient:
    global _unified_client
    if _unified_client is None:
        _unified_client = UnifiedClient()
    return _unified_client


def _get_models() -> List[Dict[str, Any]]:
    """Fetch all models from DB, remote first then local, each sorted by displayname."""
    remote = (
        g.db.query(Model).filter(Model.model_type == "remote").order_by(Model.displayname).all()
    )
    local = g.db.query(Model).filter(Model.model_type != "remote").order_by(Model.displayname).all()
    return [
        {
            "codename": m.codename,
            "displayname": m.displayname,
            "model_path": m.model_path,
            "model_type": m.model_type,
            "filesize_mb": m.filesize_mb,
        }
        for m in remote + local
    ]


@bp.route("/")
def index():
    """Show the verbalator query interface."""
    return render_template(
        "verbalator/index.html",
        prompts=common.PROMPTS,
        samples=samples.ALL_SAMPLES,
        models=_get_models(),
        default_model=DEFAULT_MODEL,
    )


@bp.route("/query", methods=["POST"])
def query():
    """Handle text generation requests."""
    try:
        # Parse request data
        data = request.get_json()

        # Extract parameters
        prompt = prompt_builder.build(data.get("prompt"), data)
        if not prompt:
            return jsonify({"error": "No prompt provided"}), 400

        # Look up model_path from DB using the posted codename
        model_codename = data.get("model", DEFAULT_MODEL)
        db_model = g.db.query(Model).filter(Model.codename == model_codename).first()
        model_path = db_model.model_path if db_model and db_model.model_path else model_codename

        # Generate response via unified client (handles OpenAI, Anthropic, LMStudio, etc.)
        entry = data.get("entry")
        full_prompt = f"{prompt}\n\n{entry}" if entry else prompt
        response = _get_unified_client().generate_chat(full_prompt, model=model_path)

        # Calculate reading level
        reading_level = fk.flesch_kincaid_grade(response.response_text)

        # Send response
        return jsonify(
            {
                "response": response.response_text,
                "usage": response.usage.to_dict(),
                "reading_level": reading_level,
            }
        )

    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500
