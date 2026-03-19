#!/usr/bin/python3

"""Verbalator routes - custom LLM query interface."""

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, current_app, g, jsonify, render_template, request

# Add src to path if not already present
if str(Path(__file__).parent.parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import util.flesch_kincaid as fk
from benchmarks.datastore.common import Model
from benchmarks.verbalator import common, prompt_builder, samples
from clients.unified_client import UnifiedLLMClient as UnifiedClient
import verbalator.actions  # noqa: F401 – triggers action registration
from verbalator.action_registry import get_action, list_actions
from verbalator.colors import COLOR_ORDER

logger = logging.getLogger(__name__)

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
        g.bench_db.query(Model)
        .filter(Model.model_type == "remote")
        .order_by(Model.displayname)
        .all()
    )
    local = (
        g.bench_db.query(Model)
        .filter(Model.model_type != "remote")
        .order_by(Model.displayname)
        .all()
    )
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


def _is_local_model(model: Optional[Model]) -> bool:
    """Return whether the selected model is local to this machine."""
    return bool(model and model.model_type != "remote")


def _can_start_local_query(model_name: str) -> bool:
    """Reserve or refresh the interactive local-model slot for Verbalator."""
    worker = current_app.extensions.get("benchmark_run_worker")
    if worker is None:
        return True

    touch = getattr(worker, "touch_interactive_local_job", None)
    if touch is None:
        return False

    return bool(touch(model_name=model_name, owner="verbalator"))


@bp.route("/")
def index():
    """Show the verbalator query interface."""
    actions = [a.to_dict() for a in list_actions()]
    return render_template(
        "verbalator/index.html",
        prompts=common.PROMPTS,
        samples=samples.ALL_SAMPLES,
        models=_get_models(),
        default_model=DEFAULT_MODEL,
        actions=actions,
        color_order=COLOR_ORDER,
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
        db_model = g.bench_db.query(Model).filter(Model.codename == model_codename).first()
        model_path = db_model.model_path if db_model and db_model.model_path else model_codename

        if _is_local_model(db_model) and not _can_start_local_query(model_path):
            return (
                jsonify(
                    {
                        "error": (
                            "Local model is currently busy with benchmark or another local-model"
                            " Verbalator session."
                        )
                    }
                ),
                409,
            )

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


def _resolve_model_path(model_codename: str) -> Tuple[str, Optional[Model]]:
    """Look up model_path from DB using the posted codename."""
    db_model = g.bench_db.query(Model).filter(Model.codename == model_codename).first()
    model_path = db_model.model_path if db_model and db_model.model_path else model_codename
    return model_path, db_model


@bp.route("/action", methods=["POST"])
def run_action():
    """Run a verbalator action and return structured JSON results."""
    try:
        data = request.get_json()
        action_name = data.get("action_name")
        if not action_name:
            return jsonify({"error": "No action_name provided"}), 400

        action = get_action(action_name)
        text = data.get("text", "")
        if not text.strip():
            return jsonify({"error": "No text provided"}), 400

        context_text: Optional[str] = data.get("context")
        target_language: Optional[str] = data.get("target_language")
        model_codename = data.get("model", DEFAULT_MODEL)

        model_path, db_model = _resolve_model_path(model_codename)

        if _is_local_model(db_model) and not _can_start_local_query(model_path):
            return (
                jsonify(
                    {
                        "error": (
                            "Local model is currently busy with benchmark or "
                            "another local-model Verbalator session."
                        )
                    }
                ),
                409,
            )

        # Build prompt and schema from the action
        system_context, prompt = action.build_prompt(
            text=text,
            context=context_text,
            target_language=target_language,
        )
        schema = action.build_schema()

        # Call LLM with structured JSON output
        client = _get_unified_client()
        response = client.generate_chat(
            prompt=prompt,
            model=model_path,
            json_schema=schema,
            context=system_context,
        )

        # Parse result
        result: Any = response.structured_data or response.response_text
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                return jsonify({"error": "Invalid JSON response from LLM"}), 500

        return jsonify(
            {
                "action": action_name,
                "result": result,
                "usage": response.usage.to_dict(),
                "template": action.get_template_name(),
            }
        )

    except KeyError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("Error running action %s", data.get("action_name"))
        return jsonify({"error": str(e)}), 500
