"""Shared constants for the Barsukas HTTP API client."""

from __future__ import annotations

import os
from typing import Final

DEFAULT_BASE_URL: Final[str] = "http://100.118.20.30:5555"

BASE_URL: Final[str] = os.environ.get("BARSUKAS_API_URL", DEFAULT_BASE_URL).rstrip("/")

API_V1_PREFIX: Final[str] = "/api/v1"

DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

# Endpoints that make a synchronous LLM call need far longer than a plain
# database read: a slow or retrying model can hold the request open for
# minutes, and a client-side timeout there loses the result of a call that
# has already been paid for.
LLM_TIMEOUT_SECONDS: Final[float] = 300.0

USER_AGENT: Final[str] = "greenland-mint-api-client/1.0"
