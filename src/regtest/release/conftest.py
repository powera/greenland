#!/usr/bin/python3

"""Shared fixtures for the release round-trip regression suite.

The expensive part is building a database from the checked-in release tree, so
that happens once per session and every test reads the same artifacts.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import constants  # noqa: E402

#: The entity exports that make up a full release write, as
#: (direction, dir-flag, subdirectory).
EXPORT_DIRECTIONS = (
    ("sqlite-to-release", "--release-dir", "lemmas"),
    ("sqlite-to-sentence-release", "--sentence-release-dir", "sentences"),
    ("sqlite-to-phrase-release", "--phrase-release-dir", "phrases"),
    ("sqlite-to-idiom-release", "--idiom-release-dir", "idioms"),
)


def read_release_sentences(release_root: Path) -> Dict[str, Dict[str, Any]]:
    """Return every sentence record under ``release_root``, keyed by GUID."""
    records: Dict[str, Dict[str, Any]] = {}
    for path in (release_root / "sentences").rglob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                record = json.loads(line)
                records[record["guid"]] = record
    return records


def jsonl_digest(release_root: Path) -> Dict[str, str]:
    """Map each JSONL file's relative path to a hash of its bytes."""
    import hashlib

    digest: Dict[str, str] = {}
    for path in sorted(release_root.rglob("*.jsonl")):
        relative = path.relative_to(release_root).as_posix()
        digest[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def build_database(database_path: Path, release_root: Path) -> None:
    """Build a SQLite database from a release tree, audio included."""
    subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "bootstrap_database.py"),
            "--db-path",
            str(database_path),
            "--release-path",
            str(release_root),
            "--release-only",
            "--force",
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    )
    # bootstrap_from_release does not carry sentence audio; it lives inline on
    # each sentence record rather than in the audio_reviews/ file the JSONL
    # backend reads.  Without this the round trip drops every sentence's audio.
    from storage.migrate import import_sentence_audio_release_to_sqlite

    import_sentence_audio_release_to_sqlite(str(database_path), str(release_root / "sentences"))


def export_release(database_path: Path, destination: Path, seed_from: Path) -> None:
    """Export a database over a copy of ``seed_from``.

    The destination is seeded first because each entity export rebuilds only
    its own subtree; starting from a copy keeps the untouched entities present
    so the result is a whole release tree rather than a partial one.
    """
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(seed_from, destination)
    for direction, dir_flag, subdirectory in EXPORT_DIRECTIONS:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "storage.migrate",
                "--sqlite-path",
                str(database_path),
                dir_flag,
                str(destination / subdirectory),
                direction,
            ],
            cwd=REPOSITORY_ROOT,
            env={"PYTHONPATH": str(SOURCE_ROOT), "GREENLAND_TEST_MODE": "1", "PATH": ""},
            check=True,
            capture_output=True,
        )


@pytest.fixture(scope="session")
def checked_in_release() -> Path:
    """The repository's committed ``data/release`` tree. Never written to."""
    return Path(constants.RELEASE_DIR)


@pytest.fixture(scope="session")
def first_pass_database(tmp_path_factory: Any, checked_in_release: Path) -> Path:
    """The database built from the committed release tree."""
    workspace = Path(tmp_path_factory.mktemp("release_roundtrip"))
    database = workspace / "pass1.sqlite"
    build_database(database, checked_in_release)
    return database


@pytest.fixture(scope="session")
def first_pass(first_pass_database: Path, checked_in_release: Path) -> Path:
    """``data/release`` -> database -> release, exported once."""
    destination = first_pass_database.parent / "export1"
    export_release(first_pass_database, destination, seed_from=checked_in_release)
    return destination


@pytest.fixture(scope="session")
def second_pass(tmp_path_factory: Any, first_pass: Path) -> Path:
    """The first pass's own output, run through the same cycle again."""
    workspace = Path(tmp_path_factory.mktemp("release_roundtrip2"))
    database = workspace / "pass2.sqlite"
    build_database(database, first_pass)
    destination = workspace / "export2"
    export_release(database, destination, seed_from=first_pass)
    return destination
