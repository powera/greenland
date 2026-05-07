"""Admin endpoints exposed under ``/api/v1/admin``.

Currently a thin wrapper around the existing graceful-restart machinery in
:mod:`barsukas.routes.settings`. Intentionally kept minimal: this is a
tailnet-only service for now; auth/security will be added later.

MIRRORED: routes here have a typed Python facade in ``api/admin.py``.
Edits must keep both sides in sync (path, method, response shape).
"""

from __future__ import annotations

from flask import Blueprint
from flask.typing import ResponseReturnValue

from barsukas.routes._mirror import mirrored_facade
from barsukas.routes.settings import initiate_restart

bp = Blueprint("admin", __name__, url_prefix="/api/v1/admin")


@bp.route("/restart", methods=["POST"])
@mirrored_facade("/api/v1/admin/restart", "POST")
def restart() -> ResponseReturnValue:
    """Initiate a graceful restart of the Barsukas process.

    Delegates to :func:`barsukas.routes.settings.initiate_restart` so the
    request-tracking state stays in one place.
    """
    return initiate_restart()
