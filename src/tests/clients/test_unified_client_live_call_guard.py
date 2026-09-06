"""Tests for the guard that blocks live LLM calls from inside the test suite."""

import pytest

from clients import lib, unified_client


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


def _blow_up_on_post(*args, **kwargs):
    raise AssertionError("kill switch did not fire; an HTTP request was attempted")


# Each backend's single outbound-request method. The guard lives here rather
# than on a wrapper: every backend defines its own generate_chat/warm_model and
# callers hold client objects directly, so a guard on UnifiedLLMClient (or on
# the module-level helpers) can be routed around. These are the methods that
# actually reach the network.
_REQUEST_BOUNDARIES = [
    ("clients.openai.client", "OpenAIClient", "_create_response", "openai"),
    ("clients.anthropic.client", "AnthropicClient", "_create_message", "anthropic"),
    ("clients.gemini_client", "GeminiClient", "_create_completion", "gemini"),
    (
        "clients.digitalocean_client",
        "DigitalOceanClient",
        "_create_completion",
        "digitalocean",
    ),
    ("clients.lmstudio_client", "LMStudioClient", "_make_request", "lmstudio"),
    ("clients.ollama_client", "OllamaClient", "_make_request", "ollama"),
    (
        "clients.translategemma_client",
        "TranslateGemmaClient",
        "_make_request",
        "translategemma",
    ),
]


@pytest.mark.parametrize("module_name, class_name, method_name, backend", _REQUEST_BOUNDARIES)
def test_disable_env_blocks_every_backend(
    monkeypatch, module_name, class_name, method_name, backend
):
    """GREENLAND_DISABLE_LLM=1 blocks the outbound request in every backend.

    requests.post is replaced with a raiser, so reaching the network fails the
    test rather than silently succeeding.
    """
    import importlib

    module = importlib.import_module(module_name)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("GREENLAND_DISABLE_LLM", "1")
    monkeypatch.setattr(module.requests, "post", _blow_up_on_post)

    client = object.__new__(getattr(module, class_name))
    method = getattr(client, method_name)

    with pytest.raises(lib.LLMCallsDisabledError) as excinfo:
        if method_name == "_create_completion":
            # Gemini takes model positionally; DigitalOcean takes it as one of
            # the request kwargs it forwards to the endpoint.
            method(model="some-model")
        elif method_name == "_make_request":
            method("chat/completions", {"model": "some-model"})
        else:
            method()

    assert backend in str(excinfo.value)


def test_disable_env_blocks_calls_made_through_a_client_object(monkeypatch):
    """A caller holding a UnifiedLLMClient cannot route around the kill switch.

    This is the path the form-generation agents take: they construct a client
    and call its generate_chat method, never the module-level wrapper. Guarding
    only the wrapper left this path live.
    """
    from clients.openai import client as openai_client

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("GREENLAND_DISABLE_LLM", "1")
    monkeypatch.setattr(openai_client.requests, "post", _blow_up_on_post)

    # A fake key, injected rather than read from keys/openai.key: the backend
    # rejects a missing key before it reaches the guarded request boundary, so
    # without this the test would assert the kill switch only on machines that
    # happen to have credentials on disk.
    client = unified_client.UnifiedLLMClient(openai_api_key="sk-test-not-a-real-key")

    with pytest.raises(lib.LLMCallsDisabledError):
        client.generate_chat(prompt="hi", model="gpt-5.4-mini")


def test_disable_env_takes_priority_over_recording_opt_out(monkeypatch):
    """The kill switch still fires when GREENLAND_ALLOW_LIVE_LLM=1 is also set.

    The two variables mean different things: the allow-flag only opts a test out
    of the pytest guard, and must not re-enable a deliberately disabled backend.
    """
    from clients.openai import client as openai_client

    monkeypatch.setenv("GREENLAND_ALLOW_LIVE_LLM", "1")
    monkeypatch.setenv("GREENLAND_DISABLE_LLM", "1")
    monkeypatch.setattr(openai_client.requests, "post", _blow_up_on_post)

    client = object.__new__(openai_client.OpenAIClient)

    with pytest.raises(lib.LLMCallsDisabledError):
        client._create_response()


def test_disable_env_is_inert_when_unset(monkeypatch):
    """With both kill switches unset, assert_llm_calls_enabled does nothing.

    TEST_MODE has to be cleared too, not just DISABLE_LLM: the guard honours
    both, so leaving it set made this test fail whenever the suite was run with
    GREENLAND_TEST_MODE=1 in the environment -- which is how it is normally run.
    """
    monkeypatch.delenv("GREENLAND_DISABLE_LLM", raising=False)
    monkeypatch.delenv("GREENLAND_TEST_MODE", raising=False)

    lib.assert_llm_calls_enabled("openai")


class _StubClient:
    """Stands in for UnifiedLLMClient, returning a sentinel from warm_model."""

    def __init__(self, sentinel):
        self._sentinel = sentinel

    def warm_model(self, model, timeout=None):
        return self._sentinel
