"""Lemma page URLs keyed by GUID (``/lemmas/N06_012``) rather than primary key.

Primary keys are renumbered whenever the database is rebuilt from data/release,
so a ``/lemmas/33`` link copied into notes or chat silently points at a
different word after a reload.  GUIDs survive the round-trip.

Routes declare ``<lemma:lemma_id>`` and their views keep taking an ``int``:

* ``LemmaRefConverter.to_url`` turns the integer id that ``url_for`` is given
  into the lemma's GUID, so existing ``url_for(..., lemma_id=lemma.id)`` call
  sites produce GUID URLs without change.
* ``LemmaRefConverter.to_python`` accepts either form.  The GUID cannot be
  resolved there because URL matching runs before the app's ``before_request``
  opens ``g.db``; :func:`resolve_lemma_ref` does it as a blueprint
  ``before_request`` hook, which Flask runs after the app-level one.
* Legacy integer URLs still work; GET requests for them redirect to the GUID
  form so the address bar always shows the stable link.
"""

from typing import Any, Dict, Optional, Union

from flask import Flask, abort, g, has_request_context, redirect, request, url_for
from flask.typing import ResponseReturnValue
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.routing import BaseConverter

from storage.crud.lemma import get_lemma_by_guid
from storage.models.schema import Lemma

CONVERTER_NAME = "lemma"


class LemmaRefConverter(BaseConverter):
    """URL segment that is either a lemma GUID or a legacy integer id."""

    # Digits (legacy primary key) or a GUID such as N06_012.  Kept narrower than
    # the default [^/]+ so static siblings like /lemmas/add can never match.
    regex = r"\d+|[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9]+"

    def to_python(self, value: str) -> Union[int, str]:
        if value.isdigit():
            return int(value)
        return value

    def to_url(self, value: Any) -> str:
        if isinstance(value, int):
            guid = _guid_for_lemma_id(value)
            if guid:
                return guid
            return str(value)
        return super().to_url(value)


def _guid_for_lemma_id(lemma_id: int) -> Optional[str]:
    """GUID for ``lemma_id`` from the request session, or None if unavailable.

    ``Session.get`` answers from the identity map when the lemma is already
    loaded, which it usually is when a page links to it, so list pages do not
    pay a query per row.
    """
    if not has_request_context():
        return None
    db = g.get("db")
    if db is None:
        return None
    try:
        lemma = db.get(Lemma, lemma_id)
    except SQLAlchemyError:
        # e.g. rendering an error page after a failed flush; the integer URL
        # still resolves, so fall back rather than mask the original error.
        return None
    if lemma is None:
        return None
    guid: Optional[str] = lemma.guid
    return guid


def register_lemma_url_converter(app: Flask) -> None:
    """Install the ``<lemma:...>`` converter; call before registering blueprints."""
    app.url_map.converters[CONVERTER_NAME] = LemmaRefConverter


def resolve_lemma_ref() -> Optional[ResponseReturnValue]:
    """Blueprint ``before_request``: turn a GUID ``lemma_id`` into the integer id.

    Unknown GUIDs 404.  A GET for a legacy integer URL redirects to the GUID URL.
    """
    view_args = request.view_args
    if not view_args or "lemma_id" not in view_args:
        return None
    lemma_ref = view_args["lemma_id"]

    if isinstance(lemma_ref, str):
        lemma = get_lemma_by_guid(g.db, lemma_ref)
        if lemma is None:
            abort(404)
        view_args["lemma_id"] = lemma.id
        return None

    # 302, not 301: browsers cache permanent redirects, and the integer id is
    # exactly what a rebuild renumbers.
    if request.method == "GET" and request.endpoint:
        guid = _guid_for_lemma_id(lemma_ref)
        if guid:
            url_values: Dict[str, Any] = {**request.args.to_dict(), **view_args}
            return redirect(url_for(request.endpoint, **url_values))
    return None
