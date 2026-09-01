#!/usr/bin/python3

"""Tests for audiotools.s3_ops.

These helpers were private methods on the audio agents (vieversys, gandras)
before they moved here. The behavior worth pinning is the part that was easy
to get wrong in the agent copies:

* the staging prefix comes from get_staging_prefix(), not a hardcoded
  "staging/", so the PostgreSQL-vs-SQLite split is honored;
* the manifest -> audio key derivation only rewrites the trailing suffix, so
  a key containing ".manifest" elsewhere is not mangled;
* listing propagates S3 errors instead of reporting an empty bucket.

Everything here uses a fake uploader; nothing touches real credentials.
"""

import json
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import pytest

import storage.backend.factory as factory
from audiotools import s3_ops
from storage.backend.config import BackendType, DataSourceConfig
from storage.backend.factory import configure_backend


@pytest.fixture(autouse=True)
def reset_global_backend() -> Iterator[None]:
    """Restore the factory's global config around each test."""
    saved = factory._global_config
    factory._global_config = None
    yield
    factory._global_config = saved


class FakeS3:
    """Minimal stand-in for the boto3 client surface s3_ops touches."""

    def __init__(
        self,
        pages: Optional[List[Dict[str, Any]]] = None,
        body: bytes = b"{}",
        list_error: Optional[Exception] = None,
    ) -> None:
        self._pages = pages if pages is not None else []
        self._body = body
        self._list_error = list_error
        self.downloaded: List[str] = []
        self.put_objects: List[Dict[str, Any]] = []
        self.put_error: Optional[Exception] = None

    def get_paginator(self, _operation: str) -> "FakeS3":
        return self

    def paginate(self, **_kwargs: Any) -> Iterator[Dict[str, Any]]:
        if self._list_error is not None:
            raise self._list_error
        yield from self._pages

    def get_object(self, **_kwargs: Any) -> Dict[str, Any]:
        class _Body:
            def __init__(self, data: bytes) -> None:
                self._data = data

            def read(self) -> bytes:
                return self._data

        return {"Body": _Body(self._body)}

    def download_file(self, _bucket: str, key: str, dest: str) -> None:
        self.downloaded.append(key)
        Path(dest).write_bytes(b"audio-bytes")

    def put_object(self, **kwargs: Any) -> Dict[str, Any]:
        if self.put_error is not None:
            raise self.put_error
        self.put_objects.append(kwargs)
        return {}


class FakeUploader:
    """Stands in for S3AudioUploader without constructing a real client."""

    def __init__(self, s3: FakeS3) -> None:
        self.s3 = s3
        self.bucket_name: Optional[str] = "test-bucket"


def _page(*keys: str) -> Dict[str, Any]:
    return {"Contents": [{"Key": k} for k in keys]}


# ---------- prefix construction ----------


def test_prefix_uses_backend_derived_staging_root() -> None:
    """The prefix must track get_staging_prefix(), not a hardcoded literal."""
    configure_backend(
        DataSourceConfig(
            backend_type=BackendType.POSTGRES, postgres_url="postgresql://u:p@h:5432/db"
        )
    )
    prefix = s3_ops.staging_manifest_prefix(language_code="lt", voice_name="ruta")
    assert prefix.startswith("staging-postgres/")
    assert prefix == "staging-postgres/lt/ruta/"


def test_prefix_narrows_by_language_then_voice() -> None:
    assert s3_ops.staging_manifest_prefix() == "staging/"
    assert s3_ops.staging_manifest_prefix(language_code="lt") == "staging/lt/"
    assert (
        s3_ops.staging_manifest_prefix(language_code="lt", voice_name="ruta") == "staging/lt/ruta/"
    )


def test_prefix_voice_without_language_is_ignored() -> None:
    """Voice alone cannot form a valid prefix, since voice nests under language."""
    assert s3_ops.staging_manifest_prefix(voice_name="ruta") == "staging/"


def test_prefix_supports_legacy_agent_layout() -> None:
    assert s3_ops.staging_manifest_prefix(agent_filter="vieversys") == "staging/vieversys/"


# ---------- listing ----------


def test_list_returns_audio_and_manifest_pairs() -> None:
    s3 = FakeS3(pages=[_page("staging/lt/ruta/abc.manifest", "staging/lt/ruta/abc.mp3")])
    result = s3_ops.list_staging_manifests(FakeUploader(s3))
    assert result == [("staging/lt/ruta/abc.mp3", "staging/lt/ruta/abc.manifest")]


def test_list_only_rewrites_the_trailing_suffix() -> None:
    """A key with ".manifest" inside it must keep that text intact.

    str.replace() would corrupt this key; the suffix-slice must not.
    """
    key = "staging/lt/ruta/my.manifest.backup.manifest"
    s3 = FakeS3(pages=[_page(key)])
    (audio_key, manifest_key) = s3_ops.list_staging_manifests(FakeUploader(s3))[0]
    assert manifest_key == key
    assert audio_key == "staging/lt/ruta/my.manifest.backup.mp3"


def test_list_skips_non_manifest_keys() -> None:
    s3 = FakeS3(pages=[_page("staging/lt/ruta/abc.mp3", "staging/lt/ruta/notes.txt")])
    assert s3_ops.list_staging_manifests(FakeUploader(s3)) == []


def test_list_honors_limit_across_pages() -> None:
    s3 = FakeS3(
        pages=[
            _page("staging/lt/a.manifest", "staging/lt/b.manifest"),
            _page("staging/lt/c.manifest"),
        ]
    )
    result = s3_ops.list_staging_manifests(FakeUploader(s3), limit=2)
    assert len(result) == 2


def test_list_tolerates_pages_without_contents() -> None:
    s3 = FakeS3(pages=[{}, _page("staging/lt/a.manifest")])
    assert len(s3_ops.list_staging_manifests(FakeUploader(s3))) == 1


def test_list_propagates_s3_errors() -> None:
    """A credentials/connectivity failure must not look like an empty bucket."""
    s3 = FakeS3(list_error=RuntimeError("AccessDenied"))
    with pytest.raises(RuntimeError, match="AccessDenied"):
        s3_ops.list_staging_manifests(FakeUploader(s3))


# ---------- manifest download ----------


def test_download_manifest_parses_json() -> None:
    s3 = FakeS3(body=b'{"guid": "abc", "voice": "ruta"}')
    assert s3_ops.download_manifest(FakeUploader(s3), "k.manifest") == {
        "guid": "abc",
        "voice": "ruta",
    }


def test_download_manifest_returns_none_on_bad_json() -> None:
    s3 = FakeS3(body=b"not json{")
    assert s3_ops.download_manifest(FakeUploader(s3), "k.manifest") is None


# ---------- audio download ----------


def test_download_audio_returns_md5_of_written_bytes(tmp_path: Path) -> None:
    import hashlib

    s3 = FakeS3()
    dest = tmp_path / "nested" / "out.mp3"
    (success, md5_hash) = s3_ops.download_audio_file(FakeUploader(s3), "k.mp3", dest)

    assert success
    assert dest.exists(), "parent directory should be created"
    assert md5_hash == hashlib.md5(b"audio-bytes").hexdigest()


def test_download_audio_reports_failure(tmp_path: Path) -> None:
    class ExplodingS3(FakeS3):
        def download_file(self, _bucket: str, key: str, dest: str) -> None:
            raise RuntimeError("NoSuchKey")

    result = s3_ops.download_audio_file(
        FakeUploader(ExplodingS3()), "missing.mp3", tmp_path / "out.mp3"
    )
    assert result == (False, None)


# ---------- manifest rejection ----------


def test_reject_adds_block_and_preserves_manifest() -> None:
    s3 = FakeS3(body=b'{"md5": "abc", "guid": "N01_001", "voice_name": "ruta"}')

    assert s3_ops.mark_manifest_rejected(
        FakeUploader(s3),
        "staging/lt/ruta/abc.manifest",
        reason="wrong word spoken",
        rejected_by="reviewer",
        quality_issues='["translation_mismatch"]',
    )

    (put,) = s3.put_objects
    assert put["Key"] == "staging/lt/ruta/abc.manifest"
    written = json.loads(put["Body"].decode("utf-8"))

    # Provenance survives the rewrite.
    assert written["md5"] == "abc"
    assert written["guid"] == "N01_001"

    rejection = written["rejected"]
    assert rejection["reason"] == "wrong word spoken"
    assert rejection["rejected_by"] == "reviewer"
    assert rejection["quality_issues"] == '["translation_mismatch"]'
    assert rejection["rejected_at"].endswith("+00:00"), "timestamp must be UTC-explicit"


def test_reject_writes_public_json() -> None:
    s3 = FakeS3()
    s3_ops.mark_manifest_rejected(FakeUploader(s3), "k.manifest", "bad", "reviewer")

    (put,) = s3.put_objects
    assert put["ContentType"] == "application/json"
    assert put["ACL"] == "public-read"


def test_reject_is_idempotent() -> None:
    """Re-rejecting refreshes the block rather than nesting or duplicating it."""
    s3 = FakeS3(body=b'{"md5": "abc", "rejected": {"reason": "old", "rejected_by": "x"}}')
    s3_ops.mark_manifest_rejected(FakeUploader(s3), "k.manifest", "new reason", "reviewer")

    written = json.loads(s3.put_objects[0]["Body"].decode("utf-8"))
    assert written["rejected"]["reason"] == "new reason"
    assert "rejected" not in written["rejected"], "block must not nest"


def test_reject_preserves_non_ascii_reason() -> None:
    s3 = FakeS3()
    s3_ops.mark_manifest_rejected(FakeUploader(s3), "k.manifest", "sakė 'ačiū'", "reviewer")

    written = json.loads(s3.put_objects[0]["Body"].decode("utf-8"))
    assert written["rejected"]["reason"] == "sakė 'ačiū'"


def test_reject_reports_unreadable_manifest() -> None:
    s3 = FakeS3(body=b"not json")
    assert not s3_ops.mark_manifest_rejected(FakeUploader(s3), "k.manifest", "bad", "reviewer")
    assert s3.put_objects == [], "must not write when the original could not be read"


def test_reject_reports_write_failure() -> None:
    s3 = FakeS3()
    s3.put_error = RuntimeError("AccessDenied")
    assert not s3_ops.mark_manifest_rejected(FakeUploader(s3), "k.manifest", "bad", "reviewer")


def test_clear_rejection_removes_block() -> None:
    s3 = FakeS3(body=b'{"md5": "abc", "rejected": {"reason": "mistake"}}')

    assert s3_ops.clear_manifest_rejection(FakeUploader(s3), "k.manifest")

    written = json.loads(s3.put_objects[0]["Body"].decode("utf-8"))
    assert "rejected" not in written
    assert written["md5"] == "abc"


def test_clear_rejection_on_clean_manifest_writes_nothing() -> None:
    s3 = FakeS3(body=b'{"md5": "abc"}')

    assert s3_ops.clear_manifest_rejection(FakeUploader(s3), "k.manifest")
    assert s3.put_objects == [], "no rewrite when there was no rejection"
