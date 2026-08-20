#!/usr/bin/python3
"""Centralized API key management for all clients."""

import logging
import os
from pathlib import Path
from typing import Optional, Union

import constants

# Configure logging
logger = logging.getLogger(__name__)


class CredentialReadBlockedError(RuntimeError):
    """Raised when GREENLAND_TEST_MODE blocks a read of the keys/ directory."""


def test_mode_enabled() -> bool:
    """Return True if GREENLAND_TEST_MODE=1 is set.

    Test mode is the stricter of the project's two kill switches. It implies
    GREENLAND_DISABLE_LLM (see clients.lib.assert_llm_calls_enabled, which
    honours it), and additionally blocks every read of the keys/ directory, so
    a run cannot load a credential of any kind -- LLM, TTS, S3, or database.
    Keyless backends such as a local Ollama are blocked too, because test mode
    subsumes the LLM switch: the point is that no model runs, not merely that
    no key is spent.

    This is the env-only question. Credential reads are additionally blocked
    under pytest -- see credential_reads_blocked() -- but LLM calls are not,
    because the suite stubs LLM clients constantly and has its own pytest-time
    net in clients.unified_client._assert_not_under_test .
    """
    return os.environ.get("GREENLAND_TEST_MODE") == "1"


def credential_reads_blocked() -> bool:
    """Return True if reading anything out of keys/ is currently forbidden.

    True under GREENLAND_TEST_MODE=1, and also under pytest, so the suite
    cannot load a real credential by accident without every invocation having
    to remember the variable. A test that genuinely needs one opts out with
    GREENLAND_ALLOW_LIVE_KEYS=1 ; as with the LLM guard, an explicit
    GREENLAND_TEST_MODE=1 overrides that opt-out, so a test cannot re-enable
    something that was switched off on purpose.
    """
    if test_mode_enabled():
        return True
    if "PYTEST_CURRENT_TEST" not in os.environ:
        return False
    return os.environ.get("GREENLAND_ALLOW_LIVE_KEYS") != "1"


def assert_credential_reads_enabled(key_name: str) -> None:
    """Refuse to read a file out of keys/ when test mode is active.

    Call this immediately before opening a key file, and before any secret is
    read from the environment as a fallback, so a blocked run never loads a
    credential it is not allowed to use.

    Args:
        key_name: Name of the key being loaded, for the error message
            (e.g. "openai", "digitalocean").

    Raises:
        CredentialReadBlockedError: If GREENLAND_TEST_MODE=1, or if running
            under pytest without GREENLAND_ALLOW_LIVE_KEYS=1 .
    """
    if not credential_reads_blocked():
        return
    what = f"keys/{key_name}.key"
    if test_mode_enabled():
        raise CredentialReadBlockedError(
            f"Read of {what} blocked: GREENLAND_TEST_MODE=1 is set. "
            f"Test mode forbids loading any credential. Pass a double or an "
            f"explicit fake key instead, or unset GREENLAND_TEST_MODE for a "
            f"deliberate live run."
        )
    raise CredentialReadBlockedError(
        f"Read of {what} blocked: tests must not load real "
        f"credentials. Pass a double or an explicit fake key instead (the "
        f"audiotools.s3_ops helpers take the uploader as an argument for this "
        f"reason). Set GREENLAND_ALLOW_LIVE_KEYS=1 only for a deliberate live run."
    )


def _assert_path_reads_enabled(key_path: "Union[str, Path]") -> None:
    """assert_credential_reads_enabled for an explicit path rather than a name."""
    if not credential_reads_blocked():
        return
    if test_mode_enabled():
        raise CredentialReadBlockedError(
            f"Read of {key_path} blocked: GREENLAND_TEST_MODE=1 is set. "
            f"Test mode forbids loading any credential. Pass an explicit fake "
            f"key instead, or unset GREENLAND_TEST_MODE for a deliberate live run."
        )
    raise CredentialReadBlockedError(
        f"Read of {key_path} blocked: tests must not load real credentials. "
        f"Pass an explicit fake key instead, or set GREENLAND_ALLOW_LIVE_KEYS=1 "
        f"for a deliberate live run."
    )


def load_key(key_name: str, required: bool = False) -> Optional[str]:
    """Load API key from file.

    Args:
        key_name: Name of the key file without extension (e.g., 'openai', 'google', 'anthropic')
        required: If True, raises RuntimeError when key is missing

    Returns:
        API key string or None if not found (when required=False)

    Raises:
        RuntimeError: If required=True and key file is not found

    Example:
        # Graceful degradation
        api_key = load_key('openai', required=False)
        if not api_key:
            logger.warning("OpenAI key not available, some features disabled")

        # Fail fast
        api_key = load_key('anthropic', required=True)
    """
    # A blocked read behaves exactly like an absent key file: callers that pass
    # required=False already handle that and degrade gracefully, so test mode
    # must not turn their soft path into a hard failure. (clients.audio builds a
    # default OpenAITTSClient at import time this way -- raising here would make
    # `import clients.audio` fail outright.) required=True callers still raise,
    # because for them a missing key was never survivable.
    if credential_reads_blocked():
        if required:
            assert_credential_reads_enabled(key_name)
        logger.debug(f"Key {key_name!r} not loaded: credential reads are blocked")
        return None

    key_path = os.path.join(constants.KEY_DIR, f"{key_name}.key")

    try:
        with open(key_path) as f:
            key = f.read().strip()
            if key:
                logger.debug(f"Loaded API key from {key_path}")
                return key
            else:
                logger.warning(f"API key file {key_path} is empty")
                if required:
                    raise RuntimeError(f"API key file {key_path} is empty")
                return None
    except FileNotFoundError:
        logger.warning(f"API key file not found at {key_path}")
        if required:
            raise RuntimeError(
                f"API key file not found at {key_path}. "
                f"Please create this file with your {key_name} API key."
            )
        return None
    except Exception as e:
        logger.error(f"Error loading API key from {key_path}: {e}")
        if required:
            raise RuntimeError(f"Error loading API key from {key_path}: {e}")
        return None


def load_key_from_path(key_path: Union[str, Path], required: bool = False) -> Optional[str]:
    """Load an API key from an explicit file path.

    Prefer load_key(), which resolves a key by name under constants.KEY_DIR .
    This variant exists for CLI flags that let an operator point at a key file
    somewhere else (e.g. gen_lithuanian_word_audio.py --api-key-file); it honours the same
    test-mode guard, so such a flag cannot be used to route around it.

    Args:
        key_path: Path to the file containing the key.
        required: If True, raise instead of returning None when unreadable.

    Returns:
        The key, or None if it could not be read (when required=False).

    Raises:
        CredentialReadBlockedError: If credential reads are blocked.
        RuntimeError: If required=True and the key could not be read.
    """
    if credential_reads_blocked():
        if required:
            _assert_path_reads_enabled(key_path)
        logger.debug(f"Key at {key_path} not loaded: credential reads are blocked")
        return None

    resolved = Path(key_path)
    try:
        key = resolved.read_text(encoding="utf-8").strip()
    except OSError as e:
        logger.warning(f"Error reading API key file {resolved}: {e}")
        if required:
            raise RuntimeError(f"Error reading API key file {resolved}: {e}")
        return None

    if key:
        logger.debug(f"Loaded API key from {resolved}")
        return key

    logger.warning(f"API key file {resolved} is empty")
    if required:
        raise RuntimeError(f"API key file {resolved} is empty")
    return None
