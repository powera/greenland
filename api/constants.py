"""Shared constants for the Barsukas HTTP API client."""

from __future__ import annotations

import os
from typing import Final

DEFAULT_BASE_URL: Final[str] = "http://localhost:5000"

BASE_URL: Final[str] = os.environ.get("BARSUKAS_API_URL", DEFAULT_BASE_URL).rstrip("/")

API_V1_PREFIX: Final[str] = "/api/v1"

DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

USER_AGENT: Final[str] = "greenland-mint-api-client/1.0"
