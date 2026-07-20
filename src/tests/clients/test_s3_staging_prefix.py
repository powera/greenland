#!/usr/bin/python3

"""Tests for the S3 staging prefix derivation.

The staging prefix separates audio staged against the PostgreSQL database
("staging-postgres") from audio staged against SQLite/JSONL ("staging"). It is
derived from the backend declared via storage.backend.configure_backend(), not
from the environment; a wrong prefix silently reads and writes audio at the
wrong S3 path, so the mapping is pinned here.
"""

from typing import Iterator

import pytest

import storage.backend.factory as factory
from clients.audio.s3_uploader import (
    get_staging_audio_key,
    get_staging_manifest_key,
    get_staging_prefix,
)
from storage.backend.config import BackendType, DataSourceConfig
from storage.backend.factory import configure_backend


@pytest.fixture(autouse=True)
def reset_global_backend() -> Iterator[None]:
    """Restore the factory's global config around each test."""
    saved = factory._global_config
    factory._global_config = None
    yield
    factory._global_config = saved


def test_unconfigured_process_uses_sqlite_prefix() -> None:
    assert get_staging_prefix() == "staging"


def test_sqlite_backend_uses_staging_prefix() -> None:
    configure_backend(
        DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path="/tmp/db.sqlite")
    )
    assert get_staging_prefix() == "staging"


def test_jsonl_backend_uses_staging_prefix() -> None:
    configure_backend(
        DataSourceConfig(backend_type=BackendType.JSONL, jsonl_data_dir="/tmp/release")
    )
    assert get_staging_prefix() == "staging"


def test_postgres_backend_uses_postgres_prefix() -> None:
    configure_backend(
        DataSourceConfig(
            backend_type=BackendType.POSTGRES, postgres_url="postgresql://u:p@h:5432/db"
        )
    )
    assert get_staging_prefix() == "staging-postgres"


def test_staging_keys_use_the_derived_prefix() -> None:
    configure_backend(
        DataSourceConfig(
            backend_type=BackendType.POSTGRES, postgres_url="postgresql://u:p@h:5432/db"
        )
    )
    assert get_staging_audio_key("lt", "ruta", "abc123") == "staging-postgres/lt/ruta/abc123.mp3"
    assert (
        get_staging_manifest_key("lt", "ruta", "abc123")
        == "staging-postgres/lt/ruta/abc123.manifest"
    )
