"""Concurrent golden startup must keep generated data in the serving database."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from storage.backend import factory
from storage.backend.config import BackendType, DataSourceConfig
from storage.backend.jsonl.session import JSONLSession
from storage.backend.jsonl.storage import JSONLStorage
from storage.models.schema import Lemma, WordToken


@pytest.mark.parametrize("reader_action", ["commit", "rollback", "close"])
def test_reader_cannot_finish_writer_transaction(tmp_path: Path, reader_action: str) -> None:
    storage = JSONLStorage(str(tmp_path))
    storage.ensure_initialized()
    warm = storage.create_session()
    warm.query(Lemma).count()
    warm.close()
    engine = storage._cached_sqlite_engine
    assert engine is not None
    with Session(engine) as writer, Session(engine) as reader:
        assert reader.query(WordToken).count() == 0
        writer.add(WordToken(token="dog", language_code="en"))
        writer.flush()
        # Independent connections see only committed data, even during a write.
        assert reader.query(WordToken).count() == 0
        getattr(reader, reader_action)()
        writer.commit()
    with Session(engine) as check:
        assert check.query(WordToken).count() == 1
        assert check.execute(text("PRAGMA journal_mode")).scalar() == "wal"
    engine.dispose()


def test_concurrent_sessions_share_populated_engine(tmp_path: Path) -> None:
    storage = JSONLStorage(str(tmp_path))
    storage.ensure_initialized()
    callers_ready = Barrier(2)
    populating = Event()
    release_population = Event()
    original_populate = JSONLSession._populate_sqlite

    def populate(session: JSONLSession) -> None:
        populating.set()
        assert release_population.wait(timeout=10)
        original_populate(session)

    def get_engine() -> Any:
        session = JSONLSession(storage)
        callers_ready.wait(timeout=10)
        try:
            return session._get_or_create_cached_engine()
        finally:
            session.close()

    with patch.object(JSONLSession, "_populate_sqlite", populate):
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(get_engine) for _ in range(2)]
            try:
                assert populating.wait(timeout=10)
            finally:
                release_population.set()
            engines = [future.result(timeout=10) for future in futures]
    assert engines[0] is engines[1] is storage._cached_sqlite_engine


def test_concurrent_sessions_share_storage(tmp_path: Path) -> None:
    config = DataSourceConfig(backend_type=BackendType.JSONL, jsonl_data_dir=str(tmp_path))
    callers_ready = Barrier(2)

    def get_storage() -> Any:
        callers_ready.wait(timeout=10)
        session = factory.create_session(config)
        try:
            return session.get_bind()
        finally:
            session.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            storages = list(executor.map(lambda _: get_storage(), range(2)))
        assert storages[0] is storages[1] is factory._jsonl_storage_cache[str(tmp_path)]
    finally:
        factory._jsonl_storage_cache.pop(str(tmp_path), None)
