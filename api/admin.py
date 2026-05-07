"""HTTP facade for admin endpoints under ``/api/v1/admin``.

Mirrors ``src/barsukas/routes/admin.py``. Any change to a route signature or
response shape there must be reflected here in the same commit.

These endpoints control the Barsukas process itself (e.g. graceful restart).
They are currently intended for tailnet-only use; auth will be added later.
"""

from __future__ import annotations

from typing import TypedDict

from api._http import post_json
from api._mirror import mirrored_route


class RestartResponse(TypedDict):
    success: bool
    message: str


@mirrored_route("/api/v1/admin/restart", "POST")
def restart() -> RestartResponse:
    """Initiate a graceful restart of the Barsukas process.

    Returns as soon as the restart has been scheduled. The server then waits
    for in-flight requests to drain and exits with code 42, which the launch
    script interprets as a restart signal.
    """
    from typing import cast

    return cast(RestartResponse, post_json("/api/v1/admin/restart"))
