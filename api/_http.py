"""Internal HTTP helper used by the facade modules.

Kept intentionally minimal: the facades pass a path + query params and get a
parsed JSON response back. Anything richer (retries, auth, async) belongs in
a dedicated client class, not here.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

import requests

from api.constants import BASE_URL, DEFAULT_TIMEOUT_SECONDS, USER_AGENT


# One pooled session for the whole process.  These facades are called in loops
# -- a wordlist import makes a request per word -- and a bare ``requests.get``
# opens a fresh connection every time, so the handshake dominates a run against
# a local server.  Nothing here is concurrent, so a single session is safe.
_SESSION = requests.Session()


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
    response = _SESSION.get(
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


def post_json(
    path: str,
    body: Optional[Mapping[str, Any]] = None,
    *,
    base_url: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> Any:
    """POST ``path`` with ``body`` as JSON and return parsed JSON.

    Body keys with ``None`` values are dropped so callers can pass optional
    fields unconditionally.
    """
    if not path.startswith("/"):
        raise ValueError(f"path must start with '/': {path!r}")

    cleaned_body = {key: value for key, value in body.items() if value is not None} if body else {}

    url = (base_url.rstrip("/") if base_url else BASE_URL) + path
    response = _SESSION.post(
        url,
        json=cleaned_body,
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


def delete_json(
    path: str,
    body: Optional[Mapping[str, Any]] = None,
    *,
    base_url: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> Any:
    """DELETE ``path`` with ``body`` as JSON and return parsed JSON.

    A request body on DELETE is unusual but is what the tag endpoints take: the
    body names which tags to remove, since the lemma itself survives.
    """
    if not path.startswith("/"):
        raise ValueError(f"path must start with '/': {path!r}")

    cleaned_body = {key: value for key, value in body.items() if value is not None} if body else {}

    url = (base_url.rstrip("/") if base_url else BASE_URL) + path
    response = _SESSION.delete(
        url,
        json=cleaned_body,
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


def patch_json(
    path: str,
    body: Optional[Mapping[str, Any]] = None,
    *,
    base_url: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> Any:
    """PATCH ``path`` with ``body`` as JSON and return parsed JSON."""
    if not path.startswith("/"):
        raise ValueError(f"path must start with '/': {path!r}")

    cleaned_body = {key: value for key, value in body.items() if value is not None} if body else {}

    url = (base_url.rstrip("/") if base_url else BASE_URL) + path
    response = _SESSION.patch(
        url,
        json=cleaned_body,
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
