"""Internal HTTP helper used by the facade modules.

Kept intentionally minimal: the facades pass a path + query params and get a
parsed JSON response back. Anything richer (retries, auth, async) belongs in
a dedicated client class, not here.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

import requests

from api.constants import BASE_URL, DEFAULT_TIMEOUT_SECONDS, USER_AGENT


class BarsukasAPIError(RuntimeError):
    """Raised when the Barsukas API returns a non-2xx response."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.message = message


def get_json(
    path: str,
    params: Optional[Mapping[str, Any]] = None,
    *,
    base_url: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> Any:
    """GET ``path`` and return parsed JSON.

    ``path`` must start with ``/`` and is appended to ``base_url`` (default
    :data:`api.constants.BASE_URL`). Query params with ``None`` values are
    dropped so callers can pass optional filters unconditionally.
    """
    if not path.startswith("/"):
        raise ValueError(f"path must start with '/': {path!r}")

    cleaned_params = (
        {key: value for key, value in params.items() if value is not None} if params else None
    )

    url = (base_url.rstrip("/") if base_url else BASE_URL) + path
    response = requests.get(
        url,
        params=cleaned_params,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )

    if not response.ok:
        try:
            payload = response.json()
            message = payload.get("error") or response.text
        except ValueError:
            message = response.text
        raise BarsukasAPIError(response.status_code, message)

    return response.json()
