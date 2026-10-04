"""The lemma fact query asks about the sense, not English noun grammar."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from storage.models.schema import Lemma
from words.lemma_fact_generation import generate_has_individual_instances


def test_instance_query_uses_the_new_schema_and_sense_definition() -> None:
    lemma = Lemma(
        lemma_text="furniture",
        definition_text="movable objects collectively used to furnish a room",
        pos_type="noun",
        pos_subtype="furniture",
    )
    client: Any = MagicMock()
    client.generate_chat.return_value = SimpleNamespace(
        structured_data={"has_individual_instances": False, "confidence": 0.9}
    )

    value, _, confidence = generate_has_individual_instances(client, lemma)

    assert value == "false"
    assert confidence == 0.9
    kwargs = client.generate_chat.call_args.kwargs
    assert "movable objects collectively" in kwargs["prompt"]
    assert "English countability" not in kwargs["prompt"]
    assert "has_individual_instances" in kwargs["json_schema"].properties
