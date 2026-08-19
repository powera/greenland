#!/usr/bin/python3

"""Tests for audiotools.manifests.

This is the rebuild path: it reconstructs a manifest from MP3s already on
disk, so everything it records is derived from the filename convention
"{GUID}_{text}.mp3" and the file bytes. The GUID/text split is the fragile
part and is pinned here.
"""

import hashlib
import json
from pathlib import Path

import pytest

from audiotools.manifests import (
    MANIFEST_FILENAME,
    UNKNOWN_GUID,
    build_manifest_for_directory,
    write_manifest_for_directory,
)


def _write_mp3(directory: Path, name: str, data: bytes = b"audio") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(data)
    return path


def test_records_md5_of_file_bytes(tmp_path: Path) -> None:
    _write_mp3(tmp_path, "N01_labas.mp3", b"some-audio-bytes")

    manifest = build_manifest_for_directory(tmp_path, "lt", "ruta")

    entry = manifest["files"]["N01_labas.mp3"]
    assert entry["md5"] == hashlib.md5(b"some-audio-bytes").hexdigest()


def test_splits_guid_from_text_on_first_underscore(tmp_path: Path) -> None:
    """Text may itself contain underscores, so only the first one splits."""
    _write_mp3(tmp_path, "N01_001_labas_rytas.mp3")

    manifest = build_manifest_for_directory(tmp_path, "lt", "ruta")

    entry = manifest["files"]["N01_001_labas_rytas.mp3"]
    assert entry["guid"] == "N01"
    assert entry["text"] == "001_labas_rytas"


def test_filename_without_underscore_uses_stem_for_both(tmp_path: Path) -> None:
    _write_mp3(tmp_path, "N01.mp3")

    entry = build_manifest_for_directory(tmp_path, "lt", "ruta")["files"]["N01.mp3"]
    assert entry["guid"] == "N01"
    assert entry["text"] == "N01"


def test_leading_underscore_yields_unknown_guid(tmp_path: Path) -> None:
    """A missing GUID must be labeled, not recorded as an empty string."""
    _write_mp3(tmp_path, "_labas.mp3")

    entry = build_manifest_for_directory(tmp_path, "lt", "ruta")["files"]["_labas.mp3"]
    assert entry["guid"] == UNKNOWN_GUID
    assert entry["text"] == "labas"


def test_records_language_and_voice(tmp_path: Path) -> None:
    _write_mp3(tmp_path, "N01_labas.mp3")

    manifest = build_manifest_for_directory(tmp_path, "zh", "meiling")

    assert manifest["language"] == "zh"
    assert manifest["voice"] == "meiling"


def test_ignores_non_mp3_files(tmp_path: Path) -> None:
    _write_mp3(tmp_path, "N01_labas.mp3")
    (tmp_path / "notes.txt").write_text("not audio")
    (tmp_path / "N02_x.wav").write_bytes(b"wav")

    manifest = build_manifest_for_directory(tmp_path, "lt", "ruta")

    assert list(manifest["files"]) == ["N01_labas.mp3"]


def test_empty_directory_yields_empty_files_map(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest_for_directory(tmp_path, "lt", "ruta")

    assert manifest["files"] == {}


def test_missing_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Voice directory not found"):
        build_manifest_for_directory(tmp_path / "nope", "lt", "ruta")


def test_write_produces_readable_json_at_expected_path(tmp_path: Path) -> None:
    _write_mp3(tmp_path, "N01_labas.mp3")

    manifest_path = write_manifest_for_directory(tmp_path, "lt", "ruta")

    assert manifest_path == tmp_path / MANIFEST_FILENAME
    written = json.loads(manifest_path.read_text())
    assert written["files"]["N01_labas.mp3"]["guid"] == "N01"


def test_write_preserves_non_ascii_text(tmp_path: Path) -> None:
    """ensure_ascii=False, so Lithuanian/Chinese text stays readable on disk."""
    _write_mp3(tmp_path, "N01_ačiū.mp3")

    manifest_path = write_manifest_for_directory(tmp_path, "lt", "ruta")

    assert "ačiū" in manifest_path.read_text()


def test_manifest_file_is_not_itself_listed(tmp_path: Path) -> None:
    """Rebuilding twice must not fold the manifest into its own file list."""
    _write_mp3(tmp_path, "N01_labas.mp3")
    write_manifest_for_directory(tmp_path, "lt", "ruta")

    manifest_path = write_manifest_for_directory(tmp_path, "lt", "ruta")

    written = json.loads(manifest_path.read_text())
    assert list(written["files"]) == ["N01_labas.mp3"]
