"""Tests for the wireword CDN uploader."""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from clients.wireword.cdn_uploader import (
    WIREWORD_BUCKET,
    WIREWORD_CDN_BASE,
    WirewordCdnUploader,
    _file_md5,
)


@pytest.fixture()
def mock_boto3() -> Any:
    """Patch boto3 and return the mock S3 client."""
    with patch("clients.wireword.cdn_uploader.boto3") as mock_b3:
        mock_client = MagicMock()
        mock_b3.client.return_value = mock_client
        # head_object raises 404 by default (file doesn't exist). This must be
        # the same ClientError the uploader catches -- an ad-hoc exception class
        # is not a subclass of botocore's, so it would propagate instead.
        from clients.wireword.cdn_uploader import ClientError

        error_response: Dict[str, Any] = {"Error": {"Code": "404"}}
        exc = ClientError.__new__(ClientError)
        exc.response = error_response  # type: ignore[attr-defined]
        mock_client.head_object.side_effect = exc
        yield mock_client


def _make_uploader(mock_boto3: Any) -> WirewordCdnUploader:
    """Create an uploader with stubbed credentials."""
    with patch("clients.wireword.cdn_uploader.boto3") as mock_b3:
        mock_b3.client.return_value = mock_boto3
        return WirewordCdnUploader(access_key="test", secret_key="test")


def test_file_md5(tmp_path: Path) -> None:
    p = tmp_path / "a.json"
    p.write_text("hello", encoding="utf-8")
    assert _file_md5(p) == hashlib.md5(b"hello").hexdigest()


def test_upload_file_calls_s3(tmp_path: Path, mock_boto3: Any) -> None:
    uploader = _make_uploader(mock_boto3)
    f = tmp_path / "data.json"
    f.write_text("[]", encoding="utf-8")
    expected_md5 = _file_md5(f)

    ok, key, md5 = uploader.upload_file(f, "lt")

    assert ok
    assert key == f"lt/{expected_md5}.json"
    assert md5 == expected_md5
    mock_boto3.upload_file.assert_called_once()
    call_args = mock_boto3.upload_file.call_args
    assert call_args[0][2] == f"lt/{expected_md5}.json"


def test_upload_file_skips_existing(tmp_path: Path, mock_boto3: Any) -> None:
    uploader = _make_uploader(mock_boto3)
    f = tmp_path / "data.json"
    f.write_text("[]", encoding="utf-8")
    expected_md5 = _file_md5(f)

    # Simulate existing object with matching ETag
    mock_boto3.head_object.side_effect = None
    mock_boto3.head_object.return_value = {"ETag": f'"{expected_md5}"'}

    ok, key, md5 = uploader.upload_file(f, "lt")

    assert ok
    mock_boto3.upload_file.assert_not_called()


def test_upload_wireword_directory(tmp_path: Path, mock_boto3: Any) -> None:
    uploader = _make_uploader(mock_boto3)
    # Create some wireword files
    (tmp_path / "wireword_levels_1_5.json").write_text("[]", encoding="utf-8")
    (tmp_path / "wireword_levels_6_10.json").write_text("[{}]", encoding="utf-8")
    (tmp_path / "wireword_sentences.json").write_text("[]", encoding="utf-8")
    # This should NOT be uploaded
    (tmp_path / "wireword_manifest_v2.json").write_text("{}", encoding="utf-8")

    ok, uploaded = uploader.upload_wireword_directory(str(tmp_path), "zh")

    assert ok
    assert len(uploaded) == 3
    # Manifest should not be in the list
    uploaded_keys = [u["s3_key"] for u in uploaded]
    assert all(k.startswith("zh/") for k in uploaded_keys)
    assert not any("manifest" in k for k in uploaded_keys)


def test_constants() -> None:
    assert WIREWORD_BUCKET == "trakaido-wireword"
    assert "wireword.trakaido.com" in WIREWORD_CDN_BASE
