"""Offline checks for benchmark page caching and external-writer freshness."""

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from flask import Flask, session
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from benchmarks.server.cache import BenchmarkPageCache


@pytest.fixture
def cached_app() -> Iterator[tuple[Flask, BenchmarkPageCache, list[int]]]:
    app = Flask(__name__)
    app.secret_key = "test-only"
    cache = BenchmarkPageCache(ttl=60, max_bytes=1024)
    cache.install(app)
    calls: list[int] = []

    @app.before_request
    def database_setup() -> None:
        calls.append(1)

    @app.route("/results", endpoint="dashboard.index")
    def results() -> str:
        if session.pop("_flashes", None):
            return "flash message"
        return f"results {len(calls)}"

    @app.route("/edit", methods=["POST"])
    def edit() -> str:
        return "saved"

    @app.route("/queue")
    def queue() -> str:
        return f"queue {len(calls)}"

    yield app, cache, calls


def test_hits_skip_database_and_expire(cached_app: tuple) -> None:
    app, cache, calls = cached_app
    client = app.test_client()
    with patch("benchmarks.server.cache.monotonic", return_value=100):
        assert client.get("/results").data == b"results 1"
        assert client.get("/results").data == b"results 1"
        assert len(calls) == 1
    with patch("benchmarks.server.cache.monotonic", return_value=161):
        assert client.get("/results").data == b"results 2"


def test_writes_invalidate_and_queries_are_distinct(cached_app: tuple) -> None:
    app, cache, calls = cached_app
    client = app.test_client()
    client.get("/results?model=a")
    client.get("/results?model=b")
    assert len(calls) == 2
    client.post("/edit")
    assert client.get("/results?model=a").data == b"results 4"
    engine = create_engine("sqlite://")
    with Session(engine) as db:
        cache.watch_session(db)
        db.commit()
    assert client.get("/results?model=a").data == b"results 5"
    engine.dispose()


def test_flashes_and_queue_are_not_cached(cached_app: tuple) -> None:
    app, cache, calls = cached_app
    client = app.test_client()
    client.get("/results")
    with client.session_transaction() as browser_session:
        browser_session["_flashes"] = [("info", "saved")]
    assert client.get("/results").data == b"flash message"
    assert client.get("/results").data == b"results 1"
    assert client.get("/queue").data != client.get("/queue").data


def test_budget_and_disable(cached_app: tuple) -> None:
    app, cache, calls = cached_app
    client = app.test_client()
    cache.max_bytes = 10
    client.get("/results?a")
    client.get("/results?b")
    client.get("/results?a")
    assert len(calls) == 3
    cache.ttl = 0
    client.get("/results?a")
    client.get("/results?a")
    assert len(calls) == 5
