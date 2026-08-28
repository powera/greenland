"""Tests for the sense-definition prompt and structured response schema."""

from types import SimpleNamespace
from typing import Any, Dict, Optional

import pytest

from clients.types import Schema
from wordfreq.translation.definitions import (
    DEFINITIONS_PROMPT_LANGUAGES,
    query_definitions,
)


class _CapturingClient:
    def __init__(self) -> None:
        self.context: Optional[str] = None
        self.schema: Optional[Schema] = None

    def generate_chat(self, **kwargs: Any) -> SimpleNamespace:
        self.context = kwargs.get("context")
        self.schema = kwargs.get("json_schema")
        return SimpleNamespace(structured_data={"definitions": []})


def test_definitions_prompt_uses_registered_subtypes_and_five_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "wordfreq.translation.definitions.linguistic_db.log_query",
        lambda *args, **kwargs: None,
    )
    client = _CapturingClient()

    definitions, success = query_definitions(
        client,
        "country",
        lambda: object(),
        model="test-model",
    )

    assert success is True
    assert definitions == []
    assert DEFINITIONS_PROMPT_LANGUAGES == ("lt", "es", "es-419", "fr", "zh")
    assert client.context is not None
    assert "region" in client.context
    assert "electronic_device" in client.context
    assert "{noun_subtypes}" not in client.context

    assert client.schema is not None
    definitions_property = client.schema.properties["definitions"]
    assert definitions_property.array_items_schema is not None
    sense_properties: Dict[str, Any] = definitions_property.array_items_schema.properties
    assert "spanish_translation" in sense_properties
    assert "spanish_latam_translation" in sense_properties
