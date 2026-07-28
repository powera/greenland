"""Tag read/review endpoints.

Tags are free-form labels on a lemma (``["legal", "archaic"]``). Corpus
ingestion applies them in bulk without a human in the loop, so these endpoints
exist to review the result afterwards: list what a run produced, then hard-delete
the tags that do not belong. Every mutation is written to the operation log.

MIRRORED: routes annotated with ``@mirrored_facade`` have a typed Python
facade in ``api/`` that must be kept in sync.
"""

from typing import Any, Dict, List, Optional, Tuple

from flask import g, request
from flask.typing import ResponseReturnValue

from barsukas.config import Config
from barsukas.routes._mirror import mirrored_facade
from barsukas.routes.api import bp
from barsukas.routes.api.meta_routes import _build_error_response, _build_success_response
from storage.crud.lemma import get_lemma_by_guid
from storage.crud.lemma_tags import add_tags, normalize_tags, read_tags, remove_tags
from storage.models.schema import Lemma


def _require_tag_list(
    payload: Dict[str, Any],
) -> Tuple[List[str], Optional[ResponseReturnValue]]:
    """Extract and normalize the ``tags`` field of a request body.

    Returns ``(tags, None)`` on success or ``([], error_response)`` on failure.
    """
    raw = payload.get("tags")
    if not isinstance(raw, list) or not raw:
        return [], _build_error_response("tags must be a non-empty list")
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            return [], _build_error_response("each tag must be a non-empty string")

    normalized = normalize_tags(raw)
    if not normalized:
        return [], _build_error_response("tags must contain at least one non-empty value")
    return normalized, None


def _lemma_summary(lemma: Lemma) -> Dict[str, Any]:
    return {
        "guid": lemma.guid,
        "lemma_text": lemma.lemma_text,
        "definition": lemma.definition_text,
        "pos_type": lemma.pos_type,
        "tags": read_tags(lemma),
    }


@bp.route("/v1/tags")
@mirrored_facade("/api/v1/tags", "GET")
def list_tags() -> ResponseReturnValue:
    """List every tag in use with the number of lemmas carrying it.

    Tags are stored as a JSON array per lemma rather than in their own table, so
    the counts are aggregated in Python over the tagged lemmas.

    Example:
        GET /api/v1/tags
    """
    counts: Dict[str, int] = {}
    tagged_lemmas = g.db.query(Lemma).filter(Lemma.tags.isnot(None)).all()
    for lemma in tagged_lemmas:
        for tag in read_tags(lemma):
            counts[tag] = counts.get(tag, 0) + 1

    data = [{"tag": tag, "lemma_count": counts[tag]} for tag in sorted(counts)]
    return _build_success_response(data, {"total": len(data)})


@bp.route("/v1/tags/<tag>")
@mirrored_facade("/api/v1/tags/<tag>", "GET")
def list_lemmas_for_tag(tag: str) -> ResponseReturnValue:
    """List the lemmas carrying ``tag``.

    This is the review sweep after a bulk corpus run: fetch everything a run
    tagged, then DELETE the ones that do not belong.

    Example:
        GET /api/v1/tags/legal
    """
    normalized = normalize_tags([tag])
    if not normalized:
        return _build_error_response("tag must be a non-empty string")
    wanted = normalized[0]

    # Narrow in SQL on the raw JSON text, then confirm in Python so a substring
    # hit such as "legalese" cannot masquerade as a match for "legal".
    candidates = (
        g.db.query(Lemma)
        .filter(Lemma.tags.isnot(None), Lemma.tags.like(f"%{wanted}%"))
        .order_by(Lemma.lemma_text)
        .all()
    )
    matched = [lemma for lemma in candidates if wanted in read_tags(lemma)]

    data = [_lemma_summary(lemma) for lemma in matched]
    return _build_success_response(data, {"tag": wanted, "total": len(data)})


@bp.route("/v1/lemma/<guid>/tags")
@mirrored_facade("/api/v1/lemma/<guid>/tags", "GET")
def get_lemma_tags(guid: str) -> ResponseReturnValue:
    """Return the tags on one lemma.

    Example:
        GET /api/v1/lemma/N01_001/tags
    """
    lemma = get_lemma_by_guid(g.db, guid)
    if not lemma:
        return _build_error_response(f"Lemma with GUID '{guid}' not found", 404)
    return _build_success_response({"guid": lemma.guid, "tags": read_tags(lemma)})


@bp.route("/v1/lemma/<guid>/tags", methods=["POST"])
@mirrored_facade("/api/v1/lemma/<guid>/tags", "POST")
def add_lemma_tags(guid: str) -> ResponseReturnValue:
    """Add tags to a lemma, keeping any already present.

    Body: ``{"tags": ["legal"]}``. Tags are free-form, so an unrecognized tag is
    stored rather than rejected. Adding a tag the lemma already carries is a
    no-op and is not logged.
    """
    lemma = get_lemma_by_guid(g.db, guid)
    if not lemma:
        return _build_error_response(f"Lemma with GUID '{guid}' not found", 404)

    payload = request.get_json(silent=True) or {}
    tags, error = _require_tag_list(payload)
    if error is not None:
        return error

    previous = read_tags(lemma)
    updated = add_tags(g.db, lemma, tags, source=Config.OPERATION_LOG_SOURCE)
    g.db.commit()

    return _build_success_response(
        {"guid": lemma.guid, "tags": updated},
        {"added": [tag for tag in updated if tag not in previous]},
    )


@bp.route("/v1/lemma/<guid>/tags", methods=["DELETE"])
@mirrored_facade("/api/v1/lemma/<guid>/tags", "DELETE")
def delete_lemma_tags(guid: str) -> ResponseReturnValue:
    """Hard-delete tags from a lemma.

    Body: ``{"tags": ["legal"]}``. The tags are removed outright rather than
    flagged; the operation log keeps the record. Removing a tag the lemma does
    not carry is a no-op and is not logged.
    """
    lemma = get_lemma_by_guid(g.db, guid)
    if not lemma:
        return _build_error_response(f"Lemma with GUID '{guid}' not found", 404)

    payload = request.get_json(silent=True) or {}
    tags, error = _require_tag_list(payload)
    if error is not None:
        return error

    previous = read_tags(lemma)
    updated = remove_tags(g.db, lemma, tags, source=Config.OPERATION_LOG_SOURCE)
    g.db.commit()

    return _build_success_response(
        {"guid": lemma.guid, "tags": updated},
        {"removed": [tag for tag in previous if tag not in updated]},
    )
