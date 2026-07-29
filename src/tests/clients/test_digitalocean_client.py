"""Tests for the DigitalOcean Gradient (Chat Completions) client.

Every test stubs ``_create_completion``, the single outbound-request method, so
nothing here can reach the network.
"""

from typing import Any

import pytest

import clients.lib
from clients.digitalocean_client import API_BASE, DigitalOceanClient
from clients.types import Schema, SchemaProperty


def _make_client(**kwargs):
    """Build a client with an injected key so no key file is read."""
    return DigitalOceanClient(api_key="sk-do-test", **kwargs)


def _stub_response(
    content="hello",
    finish_reason="stop",
    prompt_tokens=11,
    completion_tokens=7,
):
    return {
        "choices": [
            {
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    }


class _Recorder:
    """Stands in for _create_completion, capturing the request kwargs."""

    def __init__(self, payload=None):
        self.payload = payload if payload is not None else _stub_response()
        # Annotated so the assertions below can index it; assigning None alone
        # would narrow the attribute type to Optional and fail strict mypy.
        self.kwargs: Any = {}

    def __call__(self, **kwargs):
        self.kwargs = kwargs
        return self.payload, 42.0


def test_endpoint_constants():
    """The wire contract: base URL is DigitalOcean's inference host."""
    assert API_BASE == "https://inference.do-ai.run/v1"


def test_auth_header_uses_bearer_key():
    client = _make_client()
    assert client.headers["Authorization"] == "Bearer sk-do-test"
    assert client.headers["Content-Type"] == "application/json"


def test_missing_key_yields_no_headers_and_a_clear_error(monkeypatch):
    monkeypatch.setattr("clients.digitalocean_client.load_key", lambda *a, **k: None)
    client = DigitalOceanClient()

    assert client.headers == {}
    with pytest.raises(RuntimeError, match="DigitalOcean API key not available"):
        client.generate_chat(prompt="hi", model="llama-4-maverick")


def test_warm_model_is_a_noop():
    assert _make_client().warm_model("llama-4-maverick") is True


def test_request_body_shape(monkeypatch):
    """Model, messages and a token limit are sent; no response_format without a schema."""
    client = _make_client()
    recorder = _Recorder()
    monkeypatch.setattr(client, "_create_completion", recorder)

    client.generate_chat(prompt="Say hi", model="anthropic-claude-fable-5")

    assert recorder.kwargs["model"] == "anthropic-claude-fable-5"
    assert recorder.kwargs["messages"] == [{"role": "user", "content": "Say hi"}]
    assert recorder.kwargs["stream"] is False
    assert isinstance(recorder.kwargs["max_tokens"], int)
    assert "response_format" not in recorder.kwargs


def test_context_becomes_a_system_message(monkeypatch):
    client = _make_client()
    recorder = _Recorder()
    monkeypatch.setattr(client, "_create_completion", recorder)

    client.generate_chat(prompt="Say hi", model="llama-4-maverick", context="Be terse.")

    assert recorder.kwargs["messages"] == [
        {"role": "system", "content": "Be terse."},
        {"role": "user", "content": "Say hi"},
    ]


def test_messages_pass_through_without_alternation_fixups(monkeypatch):
    """Chat Completions tolerates consecutive same-role turns, so nothing is inserted."""
    client = _make_client()
    recorder = _Recorder()
    monkeypatch.setattr(client, "_create_completion", recorder)

    conversation = [
        {"role": "user", "content": "one"},
        {"role": "user", "content": "two"},
        {"role": "assistant", "content": "ok"},
    ]
    client.generate_chat(prompt="ignored", model="llama-4-maverick", messages=conversation)

    assert recorder.kwargs["messages"] == conversation


def test_messages_are_prefixed_by_context(monkeypatch):
    client = _make_client()
    recorder = _Recorder()
    monkeypatch.setattr(client, "_create_completion", recorder)

    client.generate_chat(
        prompt="ignored",
        model="llama-4-maverick",
        context="System.",
        messages=[{"role": "user", "content": "one"}],
    )

    assert recorder.kwargs["messages"][0] == {"role": "system", "content": "System."}
    assert recorder.kwargs["messages"][1] == {"role": "user", "content": "one"}


def test_max_tokens_is_forwarded_and_clamped_to_the_model_ceiling(monkeypatch):
    client = _make_client()
    recorder = _Recorder()
    monkeypatch.setattr(client, "_create_completion", recorder)

    client.generate_chat(prompt="hi", model="llama-4-maverick", max_tokens=256)
    assert recorder.kwargs["max_tokens"] == 256

    ceiling = clients.lib.ceiling_for_model("llama-4-maverick")
    client.generate_chat(prompt="hi", model="llama-4-maverick", max_tokens=ceiling + 5000)
    assert recorder.kwargs["max_tokens"] == ceiling


def test_do_model_ids_get_their_own_ceilings():
    """The bare "claude"/"gpt-5" keys do not match vendor-embedded DO ids."""
    assert clients.lib.ceiling_for_model("anthropic-claude-fable-5") == 16384
    assert clients.lib.ceiling_for_model("openai-gpt-5.6-sol") == 32768
    assert clients.lib.ceiling_for_model("llama-4-maverick") == 8192


def test_schema_translation_uses_openai_json_schema_shape(monkeypatch):
    client = _make_client()
    recorder = _Recorder(_stub_response(content='{"translation": "bonjour"}'))
    monkeypatch.setattr(client, "_create_completion", recorder)

    schema = Schema(
        name="Translation",
        description="A translation",
        properties={"translation": SchemaProperty(type="string", description="The word")},
    )
    response = client.generate_chat(prompt="hi", model="llama-4-maverick", json_schema=schema)

    response_format = recorder.kwargs["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "Details"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"]["properties"]["translation"] == {
        "type": "string",
        "description": "The word",
    }
    assert response.structured_data == {"translation": "bonjour"}
    assert response.response_text == ""


def test_schema_accepts_a_plain_dict(monkeypatch):
    client = _make_client()
    recorder = _Recorder(_stub_response(content='{"n": 3}'))
    monkeypatch.setattr(client, "_create_completion", recorder)

    schema_dict = {
        "title": "Count",
        "properties": {"n": {"type": "integer", "description": "A count"}},
        "required": ["n"],
    }
    response = client.generate_chat(prompt="hi", model="llama-4-maverick", json_schema=schema_dict)

    assert "n" in recorder.kwargs["response_format"]["json_schema"]["schema"]["properties"]
    assert response.structured_data == {"n": 3}


def test_text_response_and_usage_extraction(monkeypatch):
    client = _make_client()
    recorder = _Recorder(_stub_response(content="Bonjour", prompt_tokens=31, completion_tokens=5))
    monkeypatch.setattr(client, "_create_completion", recorder)

    response = client.generate_chat(prompt="hi", model="llama-4-maverick")

    assert response.response_text == "Bonjour"
    assert response.structured_data == {}
    assert response.usage is not None
    assert response.usage.tokens_in == 31
    assert response.usage.tokens_out == 5
    assert response.usage.total_msec == 42.0


def test_usage_cost_is_priced_for_a_known_do_model(monkeypatch):
    """The telemetry tier wiring produces a non-zero cost for a priced DO model."""
    client = _make_client()
    recorder = _Recorder(
        _stub_response(content="ok", prompt_tokens=10_000, completion_tokens=2_000)
    )
    monkeypatch.setattr(client, "_create_completion", recorder)

    response = client.generate_chat(prompt="hi", model="anthropic-claude-fable-5", max_tokens=8192)

    assert response.usage is not None
    assert response.usage.cost > 0


def test_think_blocks_are_split_into_additional_thought(monkeypatch):
    client = _make_client()
    recorder = _Recorder(_stub_response(content="<think>weighing it up</think>Bonjour"))
    monkeypatch.setattr(client, "_create_completion", recorder)

    response = client.generate_chat(prompt="hi", model="llama-4-maverick")

    assert response.response_text == "Bonjour"
    assert response.additional_thought == "weighing it up"


def test_think_blocks_are_stripped_before_json_parsing(monkeypatch):
    client = _make_client()
    recorder = _Recorder(_stub_response(content='<think>hmm</think>{"n": 1}'))
    monkeypatch.setattr(client, "_create_completion", recorder)

    schema_dict = {"title": "Count", "properties": {"n": {"type": "integer"}}, "required": ["n"]}
    response = client.generate_chat(prompt="hi", model="llama-4-maverick", json_schema=schema_dict)

    assert response.structured_data == {"n": 1}
    assert response.additional_thought == "hmm"


def test_markdown_code_fence_is_stripped(monkeypatch):
    client = _make_client()
    recorder = _Recorder(_stub_response(content='```json\n{"n": 2}\n```'))
    monkeypatch.setattr(client, "_create_completion", recorder)

    schema_dict = {"title": "Count", "properties": {"n": {"type": "integer"}}, "required": ["n"]}
    response = client.generate_chat(prompt="hi", model="llama-4-maverick", json_schema=schema_dict)

    assert response.structured_data == {"n": 2}


def test_finish_reason_length_raises_truncated(monkeypatch):
    client = _make_client()
    recorder = _Recorder(
        _stub_response(content='{"partial": tru', finish_reason="length", completion_tokens=3)
    )
    monkeypatch.setattr(client, "_create_completion", recorder)

    with pytest.raises(clients.lib.TruncatedResponseError) as excinfo:
        client.generate_chat(prompt="hi", model="llama-4-maverick", max_tokens=1024)

    assert "llama-4-maverick" in str(excinfo.value)


def test_spending_the_whole_budget_raises_truncated(monkeypatch):
    """Even without finish_reason, landing on the cap means the cap did the stopping."""
    client = _make_client()
    recorder = _Recorder(
        _stub_response(content="a lot of text", finish_reason=None, completion_tokens=512)
    )
    monkeypatch.setattr(client, "_create_completion", recorder)

    with pytest.raises(clients.lib.TruncatedResponseError):
        client.generate_chat(prompt="hi", model="llama-4-maverick", max_tokens=512)


def test_unparsable_json_raises_value_error_not_an_error_payload(monkeypatch):
    """structured_data is merged into caller result dicts, so an error dict is wrong."""
    client = _make_client()
    recorder = _Recorder(_stub_response(content="I'm afraid I can't do that."))
    monkeypatch.setattr(client, "_create_completion", recorder)

    schema_dict = {"title": "Count", "properties": {"n": {"type": "integer"}}, "required": ["n"]}
    with pytest.raises(ValueError, match="Failed to parse JSON response"):
        client.generate_chat(prompt="hi", model="llama-4-maverick", json_schema=schema_dict)


def test_empty_choices_yield_empty_text(monkeypatch):
    client = _make_client()
    recorder = _Recorder({"choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 0}})
    monkeypatch.setattr(client, "_create_completion", recorder)

    response = client.generate_chat(prompt="hi", model="llama-4-maverick")

    assert response.response_text == ""
    assert response.additional_thought is None


def test_disable_env_blocks_the_request(monkeypatch):
    """The kill switch sits on _create_completion, before any HTTP call."""

    def _blow_up(*args, **kwargs):
        raise AssertionError("kill switch did not fire; an HTTP request was attempted")

    import clients.digitalocean_client as do_module

    monkeypatch.setenv("GREENLAND_DISABLE_LLM", "1")
    monkeypatch.setattr(do_module.requests, "post", _blow_up)

    client = _make_client()
    with pytest.raises(clients.lib.LLMCallsDisabledError) as excinfo:
        client.generate_chat(prompt="hi", model="llama-4-maverick")

    assert "digitalocean" in str(excinfo.value)
