"""Bounded, process-local cache for expensive benchmark results pages.

External writers are observed after the TTL. No database or credentials are
needed on a cache hit. Interactive worker controls are deliberately excluded.
"""

from collections import OrderedDict
from threading import RLock
from time import monotonic
from typing import Any

from flask import Flask, Response, g, request, session
from sqlalchemy import event


CACHED_ENDPOINTS = frozenset(
    {
        "dashboard.index",
        "benchmarks.list_benchmarks",
        "benchmarks.view_benchmark",
        "models.list_models",
        "models.view_model",
        "runs.list_runs",
        "runs.view_run",
        "runs.compare_runs",
    }
)


class BenchmarkPageCache:
    """Cache response bytes with a TTL and a total byte budget."""

    def __init__(self, ttl: float, max_bytes: int) -> None:
        self.ttl = ttl
        self.max_bytes = max_bytes
        self._entries: OrderedDict[tuple[str, ...], tuple[float, bytes, str]] = OrderedDict()
        self._size = 0
        self._generation = 0
        self._lock = RLock()

    def clear(self, *args: Any) -> None:
        """Invalidate pages, including requests still calculating a response."""
        with self._lock:
            self._entries.clear()
            self._size = 0
            self._generation += 1

    def install(self, app: Flask) -> None:
        """Register before database setup so hits avoid opening a session."""

        @app.before_request
        def lookup() -> Response | None:
            if (
                self.ttl <= 0
                or request.method != "GET"
                or request.endpoint not in CACHED_ENDPOINTS
                or session
            ):
                return None
            # Host and client affect generated links and network authorization.
            cache_key = (request.host_url, request.full_path, request.remote_addr or "")
            with self._lock:
                now = monotonic()
                for expired_key in list(self._entries):
                    if self._entries[expired_key][0] <= now:
                        self._size -= len(self._entries.pop(expired_key)[1])
                g.benchmark_cache_key = cache_key
                g.benchmark_cache_generation = self._generation
                cached = self._entries.get(cache_key)
                if cached is not None:
                    self._entries.move_to_end(cache_key)
                    return Response(cached[1], content_type=cached[2])
            return None

        @app.after_request
        def store(response: Response) -> Response:
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                self.clear()
                return response
            cache_key = g.get("benchmark_cache_key")
            if (
                cache_key is None
                or response.status_code != 200
                or response.is_streamed
                or session.modified
                or session
                or "Set-Cookie" in response.headers
            ):
                return response
            body = response.get_data()
            expires_at = monotonic() + self.ttl
            score_cache = app.extensions.get("benchmark_score_cache")
            if score_cache is not None and score_cache.expires_at > 0:
                expires_at = min(expires_at, score_cache.expires_at)
            with self._lock:
                if (
                    g.benchmark_cache_generation != self._generation
                    or cache_key in self._entries
                    or len(body) > self.max_bytes
                ):
                    return response
                while self._entries and self._size + len(body) > self.max_bytes:
                    self._size -= len(self._entries.popitem(last=False)[1][1])
                self._entries[cache_key] = (
                    expires_at,
                    body,
                    response.content_type,
                )
                self._size += len(body)
            return response

    def watch_session(self, db: Any) -> None:
        """Invalidate on a successful commit from a web request."""
        event.listen(db, "after_commit", self.clear)
