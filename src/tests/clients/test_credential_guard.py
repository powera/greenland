#!/usr/bin/python3

"""Tests for the credential-read guard behind GREENLAND_TEST_MODE.

Reading anything out of keys/ hands real secrets to code that may then reach a
real backend. Two things must never happen: a test doing it by accident, and an
operator run doing it when credentials were explicitly switched off. The guard
in clients.keys covers both, and these tests pin the precedence between them.

GREENLAND_TEST_MODE is the stricter of the project's two kill switches: it
blocks credential reads *and* implies GREENLAND_DISABLE_LLM, so keyless
backends such as a local Ollama are blocked too.
"""

from pathlib import Path

import pytest

from clients import keys as keys_module
from clients.keys import (
    CredentialReadBlockedError,
    assert_credential_reads_enabled,
    credential_reads_blocked,
)


def test_blocks_key_reads_under_pytest(monkeypatch: pytest.MonkeyPatch) -> None:
    """The suite always runs with PYTEST_CURRENT_TEST set, so this is the default."""
    monkeypatch.delenv("GREENLAND_TEST_MODE", raising=False)
    monkeypatch.delenv("GREENLAND_ALLOW_LIVE_KEYS", raising=False)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_credential_guard.py::test")

    with pytest.raises(CredentialReadBlockedError):
        assert_credential_reads_enabled("openai")


def test_allow_live_keys_opts_a_test_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GREENLAND_TEST_MODE", raising=False)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_credential_guard.py::test")
    monkeypatch.setenv("GREENLAND_ALLOW_LIVE_KEYS", "1")

    assert_credential_reads_enabled("openai")


def test_test_mode_blocks_outside_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """GREENLAND_TEST_MODE is for operator runs, not just the test suite."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("GREENLAND_ALLOW_LIVE_KEYS", raising=False)
    monkeypatch.setenv("GREENLAND_TEST_MODE", "1")

    with pytest.raises(CredentialReadBlockedError):
        assert_credential_reads_enabled("digitalocean")


def test_test_mode_overrides_the_opt_out(monkeypatch: pytest.MonkeyPatch) -> None:
    """TEST_MODE must win over ALLOW_LIVE_KEYS, matching GREENLAND_DISABLE_LLM.

    Otherwise a test that opts into live credentials would quietly re-enable a
    deliberately disabled path.
    """
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_credential_guard.py::test")
    monkeypatch.setenv("GREENLAND_ALLOW_LIVE_KEYS", "1")
    monkeypatch.setenv("GREENLAND_TEST_MODE", "1")

    with pytest.raises(CredentialReadBlockedError):
        assert_credential_reads_enabled("openai")


def test_permits_ordinary_non_test_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """With nothing set and no pytest marker, real runs are unaffected."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("GREENLAND_TEST_MODE", raising=False)
    monkeypatch.delenv("GREENLAND_ALLOW_LIVE_KEYS", raising=False)

    assert_credential_reads_enabled("openai")
    assert not credential_reads_blocked()
    assert not keys_module.test_mode_enabled()


def test_only_exactly_one_enables_test_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Match the LLM guard's strict "1" check rather than truthiness."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("GREENLAND_ALLOW_LIVE_KEYS", raising=False)

    for value in ("0", "", "true", "yes"):
        monkeypatch.setenv("GREENLAND_TEST_MODE", value)
        assert_credential_reads_enabled("openai")


def test_load_key_raises_when_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """load_key is the chokepoint most clients go through."""
    from clients import keys

    monkeypatch.setenv("GREENLAND_TEST_MODE", "1")

    with pytest.raises(CredentialReadBlockedError):
        keys.load_key("openai", required=True)


def test_load_key_degrades_when_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    """A blocked optional read looks like an absent key, not a crash.

    clients.audio constructs a default OpenAITTSClient at import time with
    required=False; raising here would break `import clients.audio` entirely.
    """
    from clients import keys

    monkeypatch.setenv("GREENLAND_TEST_MODE", "1")

    assert keys.load_key("openai") is None
    assert keys.load_key("openai", required=False) is None


def test_blocked_load_key_opens_no_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """A blocked run must not touch the key file at all."""
    import builtins

    from clients import keys

    monkeypatch.setenv("GREENLAND_TEST_MODE", "1")

    def refuse(*args: object, **kwargs: object) -> object:
        raise AssertionError("no file may be opened once the guard has tripped")

    monkeypatch.setattr(builtins, "open", refuse)

    with pytest.raises(CredentialReadBlockedError):
        keys.load_key("openai", required=True)
    assert keys.load_key("openai", required=False) is None


def test_test_mode_blocks_llm_calls_including_keyless(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test mode subsumes GREENLAND_DISABLE_LLM, Ollama included."""
    from clients.lib import LLMCallsDisabledError, assert_llm_calls_enabled

    monkeypatch.delenv("GREENLAND_DISABLE_LLM", raising=False)
    monkeypatch.setenv("GREENLAND_TEST_MODE", "1")

    for backend in ("openai", "ollama"):
        with pytest.raises(LLMCallsDisabledError):
            assert_llm_calls_enabled(backend)


def test_disable_llm_does_not_block_credential_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    """The two switches are distinct: DISABLE_LLM leaves keys/ readable.

    An agent may legitimately need an S3 or database credential while running
    with LLM calls switched off.
    """
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("GREENLAND_TEST_MODE", raising=False)
    monkeypatch.delenv("GREENLAND_ALLOW_LIVE_KEYS", raising=False)
    monkeypatch.setenv("GREENLAND_DISABLE_LLM", "1")

    assert_credential_reads_enabled("digitalocean")


def test_uploader_construction_is_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard sits in __init__, so the class itself is unusable in tests."""
    pytest.importorskip("boto3")

    from clients.audio.s3_uploader import S3AudioUploader

    monkeypatch.delenv("GREENLAND_ALLOW_LIVE_KEYS", raising=False)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_credential_guard.py::test")

    with pytest.raises(CredentialReadBlockedError):
        S3AudioUploader()


def test_blocked_construction_reads_no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """A blocked run must not load a secret it is not allowed to use.

    Credentials come from the environment before the key file, so if the
    guard ran after credential loading this key file read would have happened.
    """
    pytest.importorskip("boto3")

    from clients.audio import s3_uploader

    monkeypatch.delenv("GREENLAND_ALLOW_LIVE_KEYS", raising=False)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_credential_guard.py::test")

    loaded: list[str] = []
    monkeypatch.setattr(
        s3_uploader.S3AudioUploader,
        "_load_keys_from_file",
        lambda self: loaded.append("key-file"),
    )

    with pytest.raises(CredentialReadBlockedError):
        s3_uploader.S3AudioUploader()

    assert loaded == [], "key file must not be read once the guard has tripped"


def test_explicit_keys_are_not_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Passing both keys sources no credential, so the guard leaves it alone.

    This is the pattern the guard's own error message recommends, and what the
    cdn_uploader tests use; blocking it would leave no way to build the class.
    """
    pytest.importorskip("boto3")

    from unittest.mock import MagicMock, patch

    from clients.wireword.cdn_uploader import WirewordCdnUploader

    monkeypatch.setenv("GREENLAND_TEST_MODE", "1")

    with patch("clients.wireword.cdn_uploader.boto3") as mock_boto3:
        mock_boto3.client.return_value = MagicMock()
        uploader = WirewordCdnUploader(access_key="fake", secret_key="fake")

    assert uploader.access_key == "fake"


def test_partial_keys_still_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """One key alone means the other is sourced, so the guard must fire."""
    pytest.importorskip("boto3")

    from unittest.mock import MagicMock, patch

    from clients.wireword.cdn_uploader import WirewordCdnUploader

    monkeypatch.setenv("GREENLAND_TEST_MODE", "1")

    with patch("clients.wireword.cdn_uploader.boto3") as mock_boto3:
        mock_boto3.client.return_value = MagicMock()
        with pytest.raises(CredentialReadBlockedError):
            WirewordCdnUploader(access_key="fake")


def test_load_key_from_path_reads_an_explicit_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The --api-key-file style loader reads the path it is given."""

    from clients.keys import load_key_from_path

    monkeypatch.setenv("GREENLAND_ALLOW_LIVE_KEYS", "1")
    monkeypatch.delenv("GREENLAND_TEST_MODE", raising=False)

    key_file = tmp_path / "custom.key"
    key_file.write_text("  sk-not-a-real-key\n")

    assert load_key_from_path(key_file) == "sk-not-a-real-key"


def test_load_key_from_path_is_guarded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A custom path must not be a way around test mode."""

    from clients.keys import load_key_from_path

    monkeypatch.setenv("GREENLAND_TEST_MODE", "1")

    key_file = tmp_path / "custom.key"
    key_file.write_text("sk-not-a-real-key")

    assert load_key_from_path(key_file) is None
    with pytest.raises(CredentialReadBlockedError):
        load_key_from_path(key_file, required=True)


def test_load_key_from_path_names_the_path_in_the_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The message must show the real path, not a keys/<path>.key fiction."""

    from clients.keys import load_key_from_path

    monkeypatch.setenv("GREENLAND_TEST_MODE", "1")

    key_file = tmp_path / "custom.key"

    with pytest.raises(CredentialReadBlockedError) as excinfo:
        load_key_from_path(key_file, required=True)

    assert str(key_file) in str(excinfo.value)
    assert "keys/" not in str(excinfo.value).split("blocked")[0]


def test_load_key_from_path_missing_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:

    from clients.keys import load_key_from_path

    monkeypatch.setenv("GREENLAND_ALLOW_LIVE_KEYS", "1")
    monkeypatch.delenv("GREENLAND_TEST_MODE", raising=False)

    missing = tmp_path / "nope.key"

    assert load_key_from_path(missing) is None
    with pytest.raises(RuntimeError):
        load_key_from_path(missing, required=True)
