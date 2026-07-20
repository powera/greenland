"""Tests for the guard that blocks live LLM calls from inside the test suite."""

import pytest

from clients import unified_client


def _fail_if_reached(*args, **kwargs):
    raise AssertionError("guard did not fire; a real backend was reached")


@pytest.mark.parametrize(
    "func_name, kwargs",
    [
        ("generate_chat", {"prompt": "hi", "model": "some-model"}),
        ("warm_model", {"model": "some-model"}),
        ("unload_model", {"model": "some-model"}),
    ],
)
def test_live_call_is_blocked_under_pytest(monkeypatch, func_name, kwargs):
    """Each module-level entry point refuses to reach a backend under pytest."""
    monkeypatch.setattr(unified_client, "_get_client", _fail_if_reached)

    with pytest.raises(unified_client.LiveLLMCallInTestError) as excinfo:
        getattr(unified_client, func_name)(**kwargs)

    # The message should name the function to patch, so the fix is obvious.
    assert func_name in str(excinfo.value)


def test_guard_can_be_bypassed_for_recording_runs(monkeypatch):
    """GREENLAND_ALLOW_LIVE_LLM=1 opts a deliberate recording run out of the guard."""
    monkeypatch.setenv("GREENLAND_ALLOW_LIVE_LLM", "1")

    sentinel = object()
    monkeypatch.setattr(unified_client, "_get_client", lambda: _StubClient(sentinel))

    assert unified_client.warm_model(model="some-model") is sentinel


def test_guard_is_inert_outside_pytest(monkeypatch):
    """Production calls (no PYTEST_CURRENT_TEST) pass straight through."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    sentinel = object()
    monkeypatch.setattr(unified_client, "_get_client", lambda: _StubClient(sentinel))

    assert unified_client.warm_model(model="some-model") is sentinel


class _StubClient:
    """Stands in for UnifiedLLMClient, returning a sentinel from warm_model."""

    def __init__(self, sentinel):
        self._sentinel = sentinel

    def warm_model(self, model, timeout=None):
        return self._sentinel
