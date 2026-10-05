"""Tests for DeferringClient: it hands back the call instead of making it."""

import pytest

from clients.deferring_client import DeferLLMCall, DeferringClient
from clients.types import LLMCall, Schema, SchemaProperty

_SCHEMA = Schema("Answer", "An answer", {"value": SchemaProperty("string", "The value")})


def test_generate_chat_raises_with_the_call() -> None:
    client = DeferringClient("gpt-6-luna")
    with pytest.raises(DeferLLMCall) as raised:
        client.generate_chat(
            prompt="p", model="ignored", json_schema=_SCHEMA, context="c", max_tokens=200
        )
    assert raised.value.call == LLMCall(prompt="p", schema=_SCHEMA, context="c", max_tokens=200)


def test_dict_schema_is_converted() -> None:
    schema_dict = {
        "type": "object",
        "properties": {"value": {"type": "string", "description": "The value"}},
        "required": ["value"],
    }
    with pytest.raises(DeferLLMCall) as raised:
        DeferringClient("m").generate_chat(prompt="p", json_schema=schema_dict)
    assert isinstance(raised.value.call.schema, Schema)
    assert "value" in raised.value.call.schema.properties


def test_unstructured_and_message_calls_are_refused() -> None:
    client = DeferringClient("m")
    with pytest.raises(ValueError, match="structured"):
        client.generate_chat(prompt="p")
    with pytest.raises(ValueError, match="Message-list"):
        client.generate_chat(prompt="p", json_schema=_SCHEMA, messages=[{"role": "user"}])


def test_default_model_and_warm_model() -> None:
    client = DeferringClient("gpt-6-luna")
    assert client.default_model == "gpt-6-luna"
    assert client.warm_model("gpt-6-luna") is True
