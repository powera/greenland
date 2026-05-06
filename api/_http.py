"""Internal HTTP transport helper for api facade modules."""

from dataclasses import dataclass
from typing import Mapping, Optional

import requests

from api.constants import DEFAULT_BARSUKAS_BASE_URL, REQUEST_TIMEOUT_SECONDS


@dataclass(frozen=True)
class HttpResult:
    status_code: int
    text: str
    json_data: object | None
    url: str


def send_request(
    method: str,
    path: str,
    *,
    params: Optional[Mapping[str, str | int]] = None,
    form_data: Optional[Mapping[str, str | int]] = None,
    base_url: str = DEFAULT_BARSUKAS_BASE_URL,
    timeout_seconds: int = REQUEST_TIMEOUT_SECONDS,
) -> HttpResult:
    """Send one HTTP request to Barsukas and return normalized result."""
    normalized_base_url = base_url.rstrip("/")
    normalized_path = path if path.startswith("/") else f"/{path}"
    target_url = f"{normalized_base_url}{normalized_path}"

    response = requests.request(
        method=method.upper(),
        url=target_url,
        params=params,
        data=form_data,
        timeout=timeout_seconds,
    )
    try:
        parsed_json: object | None = response.json()
    except ValueError:
        parsed_json = None

    return HttpResult(
        status_code=response.status_code,
        text=response.text,
        json_data=parsed_json,
        url=response.url,
    )
