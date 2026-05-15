from datetime import datetime
from typing import Any, Dict

from flask import g, jsonify, request
from flask.typing import ResponseReturnValue

from barsukas.routes.api import bp
from barsukas.routes._mirror import mirrored_facade
from storage.models import Lemma
from storage.models.schema import BarsukasTask
from sqlalchemy import func, or_


def _serialize_value(value: Any, field_name: str = "") -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _build_error_response(message: str, status_code: int = 400) -> ResponseReturnValue:
    return {"error": message}, status_code


def _build_success_response(
    data: Any, metadata: Dict[str, Any] | None = None
) -> ResponseReturnValue:
    response: Dict[str, Any] = {"data": data}
    if metadata:
        response["metadata"] = metadata
    return response


@bp.route("/v1")
def api_info() -> ResponseReturnValue:
    """
    Get information about the API and available endpoints.

    Returns:
        - version: API version
        - endpoints: List of available endpoints with descriptions
    """
    endpoints = [
        {
            "path": "/api/v1/search",
            "method": "GET",
            "description": "Search for lemmas by keyword",
            "parameters": [
                {
                    "name": "q",
                    "type": "query",
                    "required": True,
                    "description": "Search query (searches lemma text, definition, disambiguation, translations)",
                },
                {
                    "name": "pos_type",
                    "type": "query",
                    "required": False,
                    "description": "Filter by part of speech (e.g., 'noun', 'verb')",
                },
                {
                    "name": "difficulty",
                    "type": "query",
                    "required": False,
                    "description": "Filter by difficulty level (1-30, '-1' for excluded, 'null' for not set)",
                },
                {
                    "name": "missing_translation",
                    "type": "query",
                    "required": False,
                    "description": "Only return lemmas missing this target language translation",
                },
                {
                    "name": "limit",
                    "type": "query",
                    "required": False,
                    "description": "Max results to return (default: 20, max: 100)",
                },
                {
                    "name": "offset",
                    "type": "query",
                    "required": False,
                    "description": "Number of results to skip for pagination (default: 0)",
                },
            ],
        },
        {
            "path": "/api/v1/lemmas/by-difficulty",
            "method": "GET",
            "description": "List lemmas by difficulty level without requiring a text query",
            "parameters": [
                {
                    "name": "difficulty",
                    "type": "query",
                    "required": True,
                    "description": "Difficulty level (1-30, '-1' for excluded, 'null' for not set)",
                },
                {
                    "name": "pos_type",
                    "type": "query",
                    "required": False,
                    "description": "Optional part-of-speech filter",
                },
                {
                    "name": "limit",
                    "type": "query",
                    "required": False,
                    "description": "Max results to return (default: 200, max: 1000)",
                },
                {
                    "name": "offset",
                    "type": "query",
                    "required": False,
                    "description": "Number of results to skip for pagination (default: 0)",
                },
            ],
        },
        {
            "path": "/api/v1/lemmas/translations",
            "method": "GET",
            "description": "Fetch translations for multiple lemma GUIDs in one request",
            "parameters": [
                {
                    "name": "guids",
                    "type": "query",
                    "required": True,
                    "description": "Comma-separated GUID list",
                },
                {
                    "name": "language",
                    "type": "query",
                    "required": False,
                    "description": "Optional language filter",
                },
            ],
        },
        {
            "path": "/api/v1/models",
            "method": "GET",
            "description": "List LLM models registered in the benchmarks database (requires postgres)",
            "parameters": [
                {
                    "name": "q",
                    "type": "query",
                    "required": False,
                    "description": "Case-insensitive substring search across codename, displayname, model_path, lmstudio_model_name",
                }
            ],
        },
        {
            "path": "/api/v1/metadata/words",
            "method": "GET",
            "description": "Get per-language lemma counts and metadata coverage (audio, derivative forms, subtypes)",
            "parameters": [
                {
                    "name": "language",
                    "type": "query",
                    "required": False,
                    "description": "Filter to a specific language code (e.g., 'en', 'zh', 'lt')",
                }
            ],
        },
        {
            "path": "/api/v1/metadata/pos-subtypes",
            "method": "GET",
            "description": "List available POS subtypes, optionally filtered by POS type",
            "parameters": [
                {
                    "name": "pos_type",
                    "type": "query",
                    "required": False,
                    "description": "Optional part-of-speech filter (e.g., noun, verb)",
                }
            ],
        },
        {
            "path": "/api/v1/metadata/levels/by-pos",
            "method": "GET",
            "description": "Get word difficulty-level distribution for a POS type + subtype",
            "parameters": [
                {
                    "name": "pos_type",
                    "type": "query",
                    "required": True,
                    "description": "Part-of-speech type (e.g., noun, verb)",
                },
                {
                    "name": "pos_subtype",
                    "type": "query",
                    "required": True,
                    "description": "Part-of-speech subtype (e.g., physical_object)",
                },
            ],
        },
        {
            "path": "/api/v1/metadata/sentences",
            "method": "GET",
            "description": "Get per-language sentence counts and metadata coverage (audio, verification, pattern types)",
            "parameters": [
                {
                    "name": "language",
                    "type": "query",
                    "required": False,
                    "description": "Filter to a specific language code (e.g., 'en', 'zh', 'lt')",
                }
            ],
        },
        {
            "path": "/api/v1/sentences/add",
            "method": "POST",
            "description": "Add up to 15 sentences to the database, deduplicating by text. Returns IDs for use with /api/llm/sentences/decompose.",
            "parameters": [
                {
                    "name": "sentences",
                    "type": "body",
                    "required": True,
                    "description": "List of sentence strings (max 15)",
                },
                {
                    "name": "source",
                    "type": "body",
                    "required": True,
                    "description": "Source identifier stored as source_filename on each created Sentence row",
                },
                {
                    "name": "language",
                    "type": "body",
                    "required": False,
                    "description": "Source language code of the input sentences (default: en)",
                },
            ],
        },
        {
            "path": "/api/v1/lemma/<guid>",
            "method": "GET",
            "description": "Get basic information about a lemma",
            "parameters": [],
        },
        {
            "path": "/api/v1/lemma/<guid>/translations",
            "method": "GET",
            "description": "Get translations of a lemma in various languages",
            "parameters": [
                {
                    "name": "language",
                    "type": "query",
                    "required": False,
                    "description": "Filter to specific language code (e.g., 'zh', 'fr', 'lt')",
                }
            ],
        },
        {
            "path": "/api/v1/lemma/<guid>/forms",
            "method": "GET",
            "description": "Get derivative/declined forms of a lemma",
            "parameters": [
                {
                    "name": "language",
                    "type": "query",
                    "required": False,
                    "description": "Filter to specific language code (e.g., 'zh', 'fr', 'lt')",
                }
            ],
        },
        {
            "path": "/api/v1/lemma/<guid>/grammar",
            "method": "GET",
            "description": "Get grammar facts about a lemma",
            "parameters": [
                {
                    "name": "language",
                    "type": "query",
                    "required": False,
                    "description": "Filter to specific language code (e.g., 'zh', 'fr', 'lt')",
                }
            ],
        },
        {
            "path": "/api/v1/lemma/<guid>/pronunciations",
            "method": "GET",
            "description": "Get pronunciations (IPA and phonetic) for base forms of a lemma",
            "parameters": [
                {
                    "name": "language",
                    "type": "query",
                    "required": False,
                    "description": "Filter to specific language code (e.g., 'en', 'lt', 'fr')",
                }
            ],
        },
        {
            "path": "/api/v1/lemma/<guid>/audio",
            "method": "GET",
            "description": "Get lemma-level and form-level audio availability by language",
            "parameters": [
                {
                    "name": "language",
                    "type": "query",
                    "required": False,
                    "description": "Filter to specific language code (e.g., 'en', 'lt', 'fr')",
                }
            ],
        },
        {
            "path": "/api/v1/audio/voices",
            "method": "GET",
            "description": "List available TTS voices by backend and language",
            "parameters": [
                {
                    "name": "language",
                    "type": "query",
                    "required": False,
                    "description": "Filter to specific language code (e.g., 'bs')",
                }
            ],
        },
        {
            "path": "/api/v1/lemma/<guid>/wordfreq",
            "method": "GET",
            "description": "Get per-language wordfreq corpus rollups and best ranks for a lemma",
            "parameters": [],
        },
        {
            "path": "/api/v1/lemma/<guid>/sentences",
            "method": "GET",
            "description": "Get example sentences that use this lemma",
            "parameters": [
                {
                    "name": "language",
                    "type": "query",
                    "required": False,
                    "description": "Filter sentence translations to specific language code",
                }
            ],
        },
    ]

    return jsonify(
        {
            "version": "1.0",
            "description": "Read-only API for accessing lemma information",
            "endpoints": endpoints,
        }
    )


@bp.route("/v1/metadata/pos-subtypes")
@mirrored_facade("/api/v1/metadata/pos-subtypes", "GET")
def list_pos_subtypes() -> ResponseReturnValue:
    """List distinct POS subtypes, optionally filtered by POS type."""
    pos_type = request.args.get("pos_type", "").strip()
    subtype_query = g.db.query(Lemma.pos_subtype).filter(
        Lemma.pos_subtype.isnot(None),
        Lemma.pos_subtype != "",
    )
    if pos_type:
        subtype_query = subtype_query.filter(Lemma.pos_type == pos_type)

    subtypes = sorted({row[0] for row in subtype_query.distinct().all()})
    metadata: Dict[str, Any] = {
        "count": len(subtypes),
    }
    if pos_type:
        metadata["pos_type"] = pos_type
    return _build_success_response(subtypes, metadata)


@bp.route("/v1/metadata/levels/by-pos")
@mirrored_facade("/api/v1/metadata/levels/by-pos", "GET")
def get_level_distribution_by_pos() -> ResponseReturnValue:
    """Return difficulty distribution for lemmas in one POS type/subtype bucket."""
    pos_type = request.args.get("pos_type", "").strip()
    pos_subtype = request.args.get("pos_subtype", "").strip()
    if not pos_type:
        return _build_error_response("pos_type is required", 400)
    if not pos_subtype:
        return _build_error_response("pos_subtype is required", 400)

    rows = (
        g.db.query(Lemma.difficulty_level, func.count().label("count"))
        .filter(Lemma.pos_type == pos_type, Lemma.pos_subtype == pos_subtype)
        .group_by(Lemma.difficulty_level)
        .order_by(Lemma.difficulty_level)
        .all()
    )
    distribution = {
        "null" if row.difficulty_level is None else str(row.difficulty_level): row.count
        for row in rows
    }
    total_words = sum(row.count for row in rows)

    return _build_success_response(
        distribution,
        {
            "pos_type": pos_type,
            "pos_subtype": pos_subtype,
            "total_words": total_words,
        },
    )


@bp.route("/v1/models")
@mirrored_facade("/api/v1/models", "GET")
def list_models() -> ResponseReturnValue:
    """Search LLM models registered in the benchmarks database.

    Query parameters:
        - q: Optional. Case-insensitive substring search across codename, displayname,
             model_path, and lmstudio_model_name fields.
    """
    bench_db = g.get("bench_db")
    if bench_db is None:
        return _build_error_response(
            "Model registry not available (benchmarks database not configured)", 503
        )

    from benchmarks.datastore.common import Model

    query = bench_db.query(Model).order_by(Model.codename)

    search_term = request.args.get("q", "").strip()
    if search_term:
        pattern = f"%{search_term}%"
        query = query.filter(
            or_(
                Model.codename.ilike(pattern),
                Model.displayname.ilike(pattern),
                Model.model_path.ilike(pattern),
                Model.lmstudio_model_name.ilike(pattern),
            )
        )

    models = query.all()

    models_data = [
        {
            "codename": m.codename,
            "displayname": m.displayname,
            "model_path": m.model_path,
            "model_type": m.model_type,
            "lmstudio_model_name": m.lmstudio_model_name,
            "launch_date": str(m.launch_date) if m.launch_date else None,
            "license_name": m.license_name,
        }
        for m in models
    ]

    return _build_success_response(
        models_data,
        {"count": len(models_data), "search": search_term or None},
    )


from datetime import datetime

from flask import g
from flask.typing import ResponseReturnValue

from barsukas.routes.api import bp
from barsukas.routes._mirror import mirrored_facade
from storage.models.schema import BarsukasTask


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


@bp.route("/v1/tasks/<int:task_id>")
@mirrored_facade("/api/v1/tasks/<task_id>", "GET")
def get_task(task_id: int) -> ResponseReturnValue:
    task = g.db.query(BarsukasTask).filter(BarsukasTask.id == task_id).first()
    if task is None:
        return {"error": f"Task {task_id} not found"}, 404
    return {
        "data": {
            "id": task.id,
            "status": task.status,
            "task_type": task.task_type,
            "target_id": task.target_id,
            "created_at": _iso(task.created_at),
            "started_at": _iso(task.started_at),
            "finished_at": _iso(task.finished_at),
            "result_message": task.result_message,
            "error": task.error_detail,
        }
    }
