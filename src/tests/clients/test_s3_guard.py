#!/usr/bin/python3

"""Tests for the S3 credential/upload guard.

Building an S3AudioUploader reads real Digital Ocean credentials from the
environment or keys/digitalocean.key and opens a client against a real
bucket. Two things must never happen: a test doing it by accident, and an
operator run doing it when S3 was explicitly switched off. The guard covers
both, and these tests pin the precedence between them.

Mirrors the LLM guards: GREENLAND_DISABLE_S3 is the operator kill switch
(clients.lib.assert_llm_calls_enabled), and the pytest block is the
test-safety net (clients.unified_client._assert_not_under_test).
"""

import pytest

from clients.audio.s3_uploader import (
    LiveS3CallInTestError,
    S3CallsDisabledError,
    assert_s3_calls_enabled,
)


def test_blocks_construction_under_pytest(monkeypatch: pytest.MonkeyPatch) -> None:
    """The suite always runs with PYTEST_CURRENT_TEST set, so this is the default."""
    monkeypatch.delenv("GREENLAND_DISABLE_S3", raising=False)
    monkeypatch.delenv("GREENLAND_ALLOW_LIVE_S3", raising=False)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_s3_guard.py::test")

    with pytest.raises(LiveS3CallInTestError):
        assert_s3_calls_enabled()


def test_allow_live_opts_a_test_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GREENLAND_DISABLE_S3", raising=False)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_s3_guard.py::test")
    monkeypatch.setenv("GREENLAND_ALLOW_LIVE_S3", "1")

    assert_s3_calls_enabled()


def test_kill_switch_blocks_outside_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """GREENLAND_DISABLE_S3 is for operator runs, not just the test suite."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("GREENLAND_ALLOW_LIVE_S3", raising=False)
    monkeypatch.setenv("GREENLAND_DISABLE_S3", "1")

    with pytest.raises(S3CallsDisabledError):
        assert_s3_calls_enabled()


def test_kill_switch_overrides_the_test_opt_out(monkeypatch: pytest.MonkeyPatch) -> None:
    """DISABLE must win over ALLOW_LIVE, matching GREENLAND_DISABLE_LLM.

    Otherwise a test that opts into live S3 would quietly re-enable a
    deliberately disabled backend.
    """
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_s3_guard.py::test")
    monkeypatch.setenv("GREENLAND_ALLOW_LIVE_S3", "1")
    monkeypatch.setenv("GREENLAND_DISABLE_S3", "1")

    with pytest.raises(S3CallsDisabledError):
        assert_s3_calls_enabled()


def test_permits_ordinary_non_test_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """With nothing set and no pytest marker, real runs are unaffected."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("GREENLAND_DISABLE_S3", raising=False)
    monkeypatch.delenv("GREENLAND_ALLOW_LIVE_S3", raising=False)

    assert_s3_calls_enabled()


def test_only_exactly_one_disables(monkeypatch: pytest.MonkeyPatch) -> None:
    """Match the LLM guard's strict "1" check rather than truthiness."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("GREENLAND_ALLOW_LIVE_S3", raising=False)

    for value in ("0", "", "true", "yes"):
        monkeypatch.setenv("GREENLAND_DISABLE_S3", value)
        assert_s3_calls_enabled()


def test_uploader_construction_is_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard sits in __init__, so the class itself is unusable in tests."""
    boto3 = pytest.importorskip("boto3")  # noqa: F841

    from clients.audio.s3_uploader import S3AudioUploader

    monkeypatch.delenv("GREENLAND_DISABLE_S3", raising=False)
    monkeypatch.delenv("GREENLAND_ALLOW_LIVE_S3", raising=False)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_s3_guard.py::test")

    with pytest.raises(LiveS3CallInTestError):
        S3AudioUploader()


def test_blocked_construction_reads_no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """A blocked run must not load a secret it is not allowed to use.

    Credentials come from the environment before the key file, so if the
    guard ran after credential loading this env var would have been read.
    """
    pytest.importorskip("boto3")

    from clients.audio import s3_uploader

    monkeypatch.delenv("GREENLAND_ALLOW_LIVE_S3", raising=False)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_s3_guard.py::test")

    loaded: list[str] = []
    monkeypatch.setattr(
        s3_uploader.S3AudioUploader,
        "_load_keys_from_file",
        lambda self: loaded.append("key-file"),
    )

    with pytest.raises(LiveS3CallInTestError):
        s3_uploader.S3AudioUploader()

    assert loaded == [], "key file must not be read once the guard has tripped"
