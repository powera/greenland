#!/usr/bin/python3

"""Routes for viewing operation logs."""

import json
from collections import defaultdict
from typing import Any, Dict, List, Set, Union

from barsukas.config import Config
from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from werkzeug.wrappers import Response

from barsukas.helpers.flash_helpers import flash_and_log
from storage.guid_router import (
    guid_kind,
    is_wellformed_guid,
    resolve_guid_with_history,
)
from storage.models.idiom import Idiom
from storage.models.name_entity import Name
from storage.models.operation_log import OperationLog
from storage.models.schema import Lemma, Phrase, Sentence

bp = Blueprint("operation_logs", __name__, url_prefix="/logs")


# The model whose ``guid`` column each GUID kind lives in. Typed as Any because
# the five models share no common base that declares ``guid``.
_MODELS_BY_KIND: Dict[str, Any] = {
    "lemma": Lemma,
    "sentence": Sentence,
    "phrase": Phrase,
    "idiom": Idiom,
    "name": Name,
}


def _resolve_entities(logs: List[OperationLog]) -> Dict[str, Any]:
    """Map each page's entity GUIDs to their rows, one query per kind.

    guid_kind() is pure string classification, so grouping first costs nothing
    and bounds this at five queries per page however many entries there are.
    """
    guids_by_kind: Dict[str, Set[str]] = defaultdict(set)
    for log in logs:
        if log.entity_guid:
            guids_by_kind[guid_kind(log.entity_guid)].add(log.entity_guid)

    resolved: Dict[str, Any] = {}
    for kind, guids in guids_by_kind.items():
        model = _MODELS_BY_KIND.get(kind)
        if model is None:
            continue
        for row in g.db.query(model).filter(model.guid.in_(guids)).all():
            resolved[row.guid] = row
    return resolved


@bp.route("/")
def list_logs() -> ResponseReturnValue:
    """List operation logs with pagination and filtering."""
    page = request.args.get("page", 1, type=int)
    source_filter = request.args.get("source", "").strip()
    operation_type_filter = request.args.get("operation_type", "").strip()
    lemma_id_filter = request.args.get("lemma_id", "", type=str).strip()
    guid_filter = request.args.get("guid", "").strip()

    # Build query
    query = g.db.query(OperationLog)

    # Apply filters
    if source_filter:
        query = query.filter(OperationLog.source == source_filter)

    if operation_type_filter:
        query = query.filter(OperationLog.operation_type == operation_type_filter)

    if lemma_id_filter:
        try:
            lemma_id = int(lemma_id_filter)
            query = query.filter(OperationLog.lemma_id == lemma_id)
        except ValueError:
            pass

    if guid_filter:
        if is_wellformed_guid(guid_filter):
            query = query.filter(OperationLog.entity_guid == guid_filter)
        else:
            # Distinguishing a typo from a GUID with no entries is the whole
            # point of is_wellformed_guid; an empty page would say neither.
            flash_and_log(f"'{guid_filter}' is not a well-formed GUID", "warning")
            guid_filter = ""

    # Order by most recent first
    query = query.order_by(OperationLog.timestamp.desc())

    # Paginate
    total = query.count()
    logs = query.limit(Config.ITEMS_PER_PAGE).offset((page - 1) * Config.ITEMS_PER_PAGE).all()

    entities_by_guid = _resolve_entities(logs)

    # Batch load lemmas for legacy rows only. An entry written before
    # entity_guid existed may carry a non-lemma id in lemma_id -- log_operation
    # aliased entity_id into that column -- so joining it against Lemma for a
    # conversation entry shows an unrelated word. Rows that have a GUID use it.
    legacy_lemma_ids = [log.lemma_id for log in logs if log.lemma_id and not log.entity_guid]
    lemmas_by_id = {}
    if legacy_lemma_ids:
        lemmas = g.db.query(Lemma).filter(Lemma.id.in_(legacy_lemma_ids)).all()
        lemmas_by_id = {lemma.id: lemma for lemma in lemmas}

    # Parse JSON facts and enrich with entity info
    enriched_logs = []
    for log in logs:
        try:
            fact_data = json.loads(log.fact)
        except json.JSONDecodeError:
            fact_data = {"error": "Invalid JSON"}

        # Only trust lemma_id as a lemma when the fact does not say otherwise.
        # log_operation aliased entity_id into that column, so a conversation
        # entry carries a conversation id there; linking it to /lemmas/<id>
        # renders a confident link to an unrelated word.
        legacy_entity_type = fact_data.get("entity_type") if isinstance(fact_data, dict) else None
        legacy_lemma = (
            lemmas_by_id.get(log.lemma_id)
            if log.lemma_id and not log.entity_guid and legacy_entity_type in (None, "lemma")
            else None
        )

        enriched_logs.append(
            {
                "log": log,
                "fact_data": fact_data,
                "entity": entities_by_guid.get(log.entity_guid) if log.entity_guid else None,
                "entity_kind": guid_kind(log.entity_guid) if log.entity_guid else None,
                "lemma": legacy_lemma,
                "legacy_entity_type": legacy_entity_type,
            }
        )

    # Get unique sources and operation types for filters
    sources = g.db.query(OperationLog.source).distinct().order_by(OperationLog.source).all()
    sources = [s[0] for s in sources if s[0]]

    operation_types = (
        g.db.query(OperationLog.operation_type)
        .distinct()
        .order_by(OperationLog.operation_type)
        .all()
    )
    operation_types = [o[0] for o in operation_types if o[0]]

    # Calculate pagination
    total_pages = (total + Config.ITEMS_PER_PAGE - 1) // Config.ITEMS_PER_PAGE

    return render_template(
        "logs/list.html",
        logs=enriched_logs,
        page=page,
        total_pages=total_pages,
        total=total,
        source_filter=source_filter,
        operation_type_filter=operation_type_filter,
        lemma_id_filter=lemma_id_filter,
        guid_filter=guid_filter,
        sources=sources,
        operation_types=operation_types,
    )


@bp.route("/<int:log_id>")
def view_log(log_id: int) -> Union[str, Response]:
    """View a single operation log entry."""
    log = g.db.query(OperationLog).get(log_id)
    if not log:
        flash_and_log("Log entry not found", "error")
        return redirect(url_for("operation_logs.list_logs"))

    try:
        fact_data = json.loads(log.fact)
    except json.JSONDecodeError:
        fact_data = {"error": "Invalid JSON"}

    # resolve_guid_with_history rather than resolve_guid: a *_delete entry names
    # a GUID whose row is already gone, and only the history variant can say
    # whether it was retired and what replaced it.
    resolved = resolve_guid_with_history(g.db, log.entity_guid) if log.entity_guid else None

    # Legacy rows only, and only when the fact does not say the id belongs to
    # something else -- see the comment in list_logs.
    legacy_entity_type = fact_data.get("entity_type") if isinstance(fact_data, dict) else None
    lemma = None
    if log.lemma_id and not log.entity_guid and legacy_entity_type in (None, "lemma"):
        lemma = g.db.query(Lemma).get(log.lemma_id)

    return render_template(
        "logs/view.html",
        log=log,
        fact_data=fact_data,
        lemma=lemma,
        resolved=resolved,
        legacy_entity_type=legacy_entity_type,
    )
