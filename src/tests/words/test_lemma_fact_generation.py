"""Concept fact generation identifies a sense independently of noun grammar."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from storage.models.schema import Lemma
from words.lemma_fact_generation import generate_noun_concept_fact


@pytest.mark.parametrize(
    "fact_type,value",
    [("individuation", "collection"), ("concreteness", "physical")],
)
def test_concept_query_uses_enum_and_sense_definition(fact_type: str, value: str) -> None:
    lemma = Lemma(
        lemma_text="furniture",
        definition_text="movable objects collectively used to furnish a room",
        disambiguation="collective furnishings",
        pos_type="noun",
        pos_subtype="furniture",
    )
    client: Any = MagicMock()
    client.generate_chat.return_value = SimpleNamespace(
        structured_data={fact_type: value, "confidence": 0.9}
    )
    result, _, confidence = generate_noun_concept_fact(client, lemma, fact_type)
    assert result == value
    assert confidence == 0.9
    kwargs = client.generate_chat.call_args.kwargs
    assert "movable objects collectively" in kwargs["prompt"]
    assert "collective furnishings" in kwargs["prompt"]
    assert "independently of language" in kwargs["prompt"]
    assert kwargs["json_schema"].properties[fact_type].type == "string"
    assert value in kwargs["json_schema"].properties[fact_type].enum


@pytest.mark.parametrize("value", [True, "true", "substance", "mixed", None])
def test_invalid_or_obsolete_classifications_are_rejected(value: Any) -> None:
    lemma = Lemma(lemma_text="water", definition_text="water", pos_type="noun")
    client: Any = MagicMock()
    client.generate_chat.return_value = SimpleNamespace(
        structured_data={"individuation": value, "confidence": 0.9}
    )
    assert generate_noun_concept_fact(client, lemma, "individuation") == (None, None, 0.0)


def test_non_noun_and_retired_fact_do_not_call_model() -> None:
    lemma = Lemma(lemma_text="run", definition_text="to move", pos_type="verb")
    client: Any = MagicMock()
    assert generate_noun_concept_fact(client, lemma, "individuation") == (None, None, 0.0)
    assert generate_noun_concept_fact(client, lemma, "has_individual_instances") == (
        None,
        None,
        0.0,
    )
    client.generate_chat.assert_not_called()


def test_both_dimensions_persist_independently() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    import storage.models
    from storage.backend.config import DataSourceConfig
    from storage.crud.lemma_fact import get_lemma_facts_dict
    from storage.models.schema import Base
    from words.lemma_fact_generation import generate_lemma_fact_for_lemma

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        lemma = Lemma(lemma_text="idea", definition_text="a particular thought", pos_type="noun")
        session.add(lemma)
        session.flush()
        client: Any = MagicMock()
        client.generate_chat.side_effect = [
            SimpleNamespace(structured_data={"individuation": "individual", "confidence": 0.9}),
            SimpleNamespace(structured_data={"concreteness": "abstract", "confidence": 0.9}),
        ]
        for dimension in ("individuation", "concreteness"):
            result = generate_lemma_fact_for_lemma(
                session, client, DataSourceConfig(), lemma, dimension
            )
            assert result["success"]
        assert get_lemma_facts_dict(session, lemma.id) == {
            "individuation": "individual",
            "concreteness": "abstract",
        }
        skipped = generate_lemma_fact_for_lemma(
            session, client, DataSourceConfig(), lemma, "individuation"
        )
        assert skipped["skipped"]
        assert client.generate_chat.call_count == 2
    engine.dispose()
