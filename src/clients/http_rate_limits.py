"""Per-host minimum-interval rate limits for outbound HTTP requests.

Wikimedia enforces a per-clock-minute request quota: bursting a handful of
requests trips a ~60s cooldown. To stay under it, outbound GETs are paced to a
minimum interval *per host*. This module owns the per-host data; the default
fallback for unlisted hosts lives in :data:`constants.DEFAULT_HTTP_MIN_INTERVAL_SECONDS`.

A value of ``0`` disables pacing for that host.
"""

from typing import Dict
from urllib.parse import urlparse

import constants

# Minimum seconds between requests to each host. Hosts not listed here fall back
# to constants.DEFAULT_HTTP_MIN_INTERVAL_SECONDS.
HOST_MIN_INTERVAL_SECONDS: Dict[str, float] = {
    "www.wikidata.org": 6.0,
    "en.wikipedia.org": 6.0,
    "de.wikipedia.org": 6.0,
    "fr.wikipedia.org": 6.0,
    "en.wikisource.org": 6.0,
}


def min_interval_for_host(host: str) -> float:
    """Return the minimum seconds between requests for ``host``.

    Args:
        host: A bare hostname (e.g. ``"en.wikipedia.org"``).

    Returns:
        The per-host interval if configured, otherwise the project default.
    """
    return HOST_MIN_INTERVAL_SECONDS.get(host, constants.DEFAULT_HTTP_MIN_INTERVAL_SECONDS)


def min_interval_for_url(url: str) -> float:
    """Return the minimum seconds between requests for the host in ``url``."""
    return min_interval_for_host(urlparse(url).hostname or "")
