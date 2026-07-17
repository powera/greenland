"""Tests for per-host HTTP rate-limit lookups."""

import constants
from clients.http_rate_limits import min_interval_for_host, min_interval_for_url


def test_known_host_uses_configured_interval() -> None:
    assert min_interval_for_host("en.wikipedia.org") == 6.0
    assert min_interval_for_url("https://www.wikidata.org/w/api.php") == 6.0
    assert min_interval_for_url("https://query.wikidata.org/sparql") == 6.0


def test_unknown_host_falls_back_to_default(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(constants, "DEFAULT_HTTP_MIN_INTERVAL_SECONDS", 3.5)
    assert min_interval_for_host("example.com") == 3.5
    assert min_interval_for_url("https://example.com/path") == 3.5


def test_url_without_host_uses_default(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(constants, "DEFAULT_HTTP_MIN_INTERVAL_SECONDS", 2.0)
    assert min_interval_for_url("not-a-url") == 2.0
