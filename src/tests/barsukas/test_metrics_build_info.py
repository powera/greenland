#!/usr/bin/python3

"""Tests for git build-info resolution in barsukas.metrics.

These exercise the pure-stdlib ``.git`` reader (no git subprocess) across the
cases that matter for deploys: a normal branch checkout with a loose ref, a
checkout whose refs have been packed by ``git gc``, a detached HEAD, and the
graceful fallbacks (env overrides, missing ``.git``).
"""

import os
from pathlib import Path
from typing import Iterator

import pytest

from barsukas.metrics import read_build_info

_SHA = "2c90ee25d7f501e1eec330b546aa778ceb059475"


@pytest.fixture(autouse=True)
def _clear_build_env() -> Iterator[None]:
    """Ensure BARSUKAS_BUILD_* overrides don't leak between tests."""
    saved = {
        key: os.environ.pop(key, None)
        for key in ("BARSUKAS_BUILD_REVISION", "BARSUKAS_BUILD_BRANCH", "BARSUKAS_BUILD_VERSION")
    }
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is not None:
                os.environ[key] = value


def _make_git_dir(root: Path, head: str) -> Path:
    git_dir = root / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text(head, encoding="utf-8")
    return git_dir


def test_loose_ref_on_branch(tmp_path: Path) -> None:
    git_dir = _make_git_dir(tmp_path, "ref: refs/heads/main\n")
    ref = git_dir / "refs" / "heads" / "main"
    ref.parent.mkdir(parents=True)
    ref.write_text(_SHA + "\n", encoding="utf-8")

    info = read_build_info(str(tmp_path))
    assert info["revision"] == _SHA
    assert info["branch"] == "main"
    assert info["version"] == _SHA[:12]


def test_packed_ref_fallback(tmp_path: Path) -> None:
    """After git gc the loose ref is gone; the SHA lives in packed-refs."""
    git_dir = _make_git_dir(tmp_path, "ref: refs/heads/main\n")
    (git_dir / "packed-refs").write_text(
        "# pack-refs with: peeled fully-peeled sorted\n"
        f"{_SHA} refs/heads/main\n"
        "^0000000000000000000000000000000000000000\n",
        encoding="utf-8",
    )

    info = read_build_info(str(tmp_path))
    assert info["revision"] == _SHA
    assert info["branch"] == "main"


def test_detached_head(tmp_path: Path) -> None:
    _make_git_dir(tmp_path, _SHA + "\n")

    info = read_build_info(str(tmp_path))
    assert info["revision"] == _SHA
    assert info["branch"] == "detached"


def test_env_overrides_win(tmp_path: Path) -> None:
    _make_git_dir(tmp_path, "ref: refs/heads/main\n")
    os.environ["BARSUKAS_BUILD_REVISION"] = "deadbeef"
    os.environ["BARSUKAS_BUILD_BRANCH"] = "release"
    os.environ["BARSUKAS_BUILD_VERSION"] = "v1.2.3"

    info = read_build_info(str(tmp_path))
    assert info == {"revision": "deadbeef", "branch": "release", "version": "v1.2.3"}


def test_missing_git_dir_is_unknown(tmp_path: Path) -> None:
    info = read_build_info(str(tmp_path))
    assert info == {"revision": "unknown", "branch": "unknown", "version": "unknown"}
