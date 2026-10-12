"""Lemma facts in the release base.jsonl record and its round trip."""

from __future__ import annotations

from typing import Any, Dict

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import storage.models  # noqa: F401 -- register every model before create_all
from storage.models.lemma_fact import LemmaFact
from storage.models.schema import Base, Lemma
from storage.release.lemma import (
    apply_lemma_facts,
    import_release_record,
    lemma_to_release_record,
)


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _lemma(session: Session, guid: str = "N06_012", text: str = "sugar") -> Lemma:
    lemma = Lemma(
        guid=guid,
        lemma_text=text,
        definition_text=f"{text} definition",
        pos_type="noun",
        pos_subtype="food",
        difficulty_level=1,
    )
    session.add(lemma)
    session.commit()
    return lemma


def _record(lemma: Lemma) -> Dict[str, Any]:
    return lemma_to_release_record(lemma)


def test_record_omits_facts_when_none() -> None:
    session = _make_session()
    lemma = _lemma(session)

    assert "facts" not in _record(lemma)


def test_record_carries_facts_dict() -> None:
    session = _make_session()
    lemma = _lemma(session)
    lemma.lemma_facts.append(LemmaFact(fact_type="individuation", fact_value="non_individuated"))
    session.commit()

    assert _record(lemma)["facts"] == {"individuation": "non_individuated"}


def test_retired_fact_is_not_exported() -> None:
    session = _make_session()
    lemma = _lemma(session)
    lemma.lemma_facts.append(LemmaFact(fact_type="quantifiable", fact_value="true"))
    session.commit()
    assert "facts" not in _record(lemma)


@pytest.mark.parametrize("fact_type", ["quantifiable", "has_individual_instances"])
def test_retired_release_fact_is_rejected_before_mutation(fact_type: str) -> None:
    session = _make_session()
    lemma = _lemma(session)
    lemma.lemma_facts.append(LemmaFact(fact_type="concreteness", fact_value="physical"))
    with pytest.raises(ValueError, match="Retired lemma fact"):
        apply_lemma_facts(lemma, {"facts": {fact_type: "false"}})
    assert lemma.lemma_facts[0].fact_type == "concreteness"


def test_import_creates_facts() -> None:
    session = _make_session()
    record = {
        "guid": "N06_013",
        "pos_type": "noun",
        "pos_subtype": "food",
        "concept_label": "salt",
        "concept_definition": "a seasoning",
        "translations": {"en": "salt"},
        "difficulty_level": 1,
        "facts": {"individuation": "non_individuated"},
    }

    lemma = import_release_record(session, record)
    session.commit()

    assert {fact.fact_type: fact.fact_value for fact in lemma.lemma_facts} == {
        "individuation": "non_individuated"
    }


def test_apply_replaces_and_removes_facts() -> None:
    session = _make_session()
    lemma = _lemma(session)
    lemma.lemma_facts.append(LemmaFact(fact_type="individuation", fact_value="non_individuated"))
    session.commit()

    apply_lemma_facts(lemma, {"facts": {"individuation": "individual"}})
    session.commit()
    assert {fact.fact_type: fact.fact_value for fact in lemma.lemma_facts} == {
        "individuation": "individual"
    }

    apply_lemma_facts(lemma, {})
    session.commit()
    assert lemma.lemma_facts == []
    assert session.query(LemmaFact).count() == 0


def test_export_then_import_is_stable() -> None:
    source = _make_session()
    lemma = _lemma(source)
    lemma.lemma_facts.append(LemmaFact(fact_type="individuation", fact_value="individual"))
    lemma.lemma_facts.append(LemmaFact(fact_type="concreteness", fact_value="physical"))
    source.commit()
    record = _record(lemma)

    target = _make_session()
    imported = import_release_record(target, record)
    target.commit()

    assert _record(imported)["facts"] == record["facts"]


def test_noun_dimensions_reject_invalid_values_and_other_parts_of_speech() -> None:
    session = _make_session()
    lemma = _lemma(session)
    with pytest.raises(ValueError, match="Invalid value"):
        apply_lemma_facts(lemma, {"facts": {"concreteness": "mixed"}})
    assert lemma.lemma_facts == []
    lemma.pos_type = "verb"
    with pytest.raises(ValueError, match="only to noun"):
        apply_lemma_facts(lemma, {"facts": {"individuation": "individual"}})
    assert lemma.lemma_facts == []
