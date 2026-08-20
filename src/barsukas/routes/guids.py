#!/usr/bin/python3

"""GUID lookup: resolve any GUID, including ones that no longer name anything.

Every other page in Barsukas is reached by database id. A GUID is what the
release files, the Trakaido export and any external reference actually carry,
and a retired one used to be a dead end: ``resolve_guid`` returned ``None`` for
a GUID that was never issued and for one that was replaced years ago, with no
way to tell the two apart. This page answers "what happened to A05_001?".
"""

from typing import Dict, Optional

from flask import Blueprint, abort, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from storage.guid_router import (
    GuidKind,
    ResolvedGuid,
    is_wellformed_guid,
    resolve_guid_with_history,
)

bp = Blueprint("guids", __name__, url_prefix="/guids")

#: Where to send a viewer once a GUID resolves to a live row, per element kind.
#: Names, unlike the rest, call their detail view ``detail``.
_DETAIL_ENDPOINTS: Dict[GuidKind, str] = {
    "lemma": "lemmas.view_lemma",
    "sentence": "sentences.view_sentence",
    "phrase": "phrases.view_phrase",
    "idiom": "idioms.view_idiom",
    "name": "names.detail",
}

#: The view argument each of those endpoints expects.
_DETAIL_ID_ARGS: Dict[GuidKind, str] = {
    "lemma": "lemma_id",
    "sentence": "sentence_id",
    "phrase": "phrase_id",
    "idiom": "idiom_id",
    "name": "name_id",
}


def _detail_url(kind: GuidKind, obj: object) -> Optional[str]:
    """URL of the detail page for a resolved object, or None if it has none."""
    endpoint = _DETAIL_ENDPOINTS.get(kind)
    id_arg = _DETAIL_ID_ARGS.get(kind)
    row_id = getattr(obj, "id", None)
    if endpoint is None or id_arg is None or row_id is None:
        return None
    return url_for(endpoint, **{id_arg: row_id})


def _render_resolved(guid: str, resolved: Optional[ResolvedGuid]) -> str:
    """Render the lookup page for a GUID that did not resolve to a live row.

    ``resolved`` is None when ``guid`` is not GUID-shaped at all, which the
    template reports as a malformed entry rather than a missing record.
    """
    return render_template(
        "guids/lookup.html",
        guid=guid,
        resolved=resolved,
        malformed=resolved is None,
        detail_url=(
            _detail_url(resolved.kind, resolved.replacement)
            if resolved is not None and resolved.replacement is not None
            else None
        ),
    )


@bp.route("/")
def index() -> ResponseReturnValue:
    """Search box, and the result when a ``guid`` query argument is present.

    A GUID that names nothing renders the "never issued" panel with a normal
    200: this is a form reporting on what was typed, and a typo is not an error
    condition. The permalink at :func:`lookup` 404s in that case instead.
    """
    guid = (request.args.get("guid") or "").strip()
    if not guid:
        return render_template(
            "guids/lookup.html", guid="", resolved=None, malformed=False, detail_url=None
        )

    # A string that is not GUID-shaped is a typo, not a missing record.
    if not is_wellformed_guid(guid):
        return _render_resolved(guid, None)

    resolved: ResolvedGuid = resolve_guid_with_history(g.db, guid)

    # A live GUID needs no explanation - go straight to the record.
    if resolved.exists:
        target = _detail_url(resolved.kind, resolved.obj)
        if target is not None:
            return redirect(target)

    return _render_resolved(guid, resolved)


@bp.route("/<guid>")
def lookup(guid: str) -> ResponseReturnValue:
    """Permalink form, so a GUID can be pasted into the address bar.

    Unlike :func:`index`, a GUID that names nothing and was never retired is a
    genuine 404 here. The two differ deliberately: the search box is a form
    reporting on what the user typed, so a typo should come back as a page with
    the "never issued" explanation rather than an error, while a permalink is an
    address claiming a record exists at it. Something following a link or
    scraping for dead references needs that claim to fail as a 404.

    A tombstoned GUID is *not* a 404. The number was issued, and what replaced
    it is the answer the caller wants, so it renders like it does in the search
    box.
    """
    if not is_wellformed_guid(guid):
        abort(404)

    resolved: ResolvedGuid = resolve_guid_with_history(g.db, guid)

    if resolved.exists:
        target = _detail_url(resolved.kind, resolved.obj)
        if target is not None:
            return redirect(target)

    if not resolved.is_tombstoned:
        abort(404)

    return _render_resolved(guid, resolved)
