"""Targeted SQLite imports preserve other data and require reviewed replacements."""

import importlib.util
import json
from pathlib import Path
from typing import Any, Dict


import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import storage.models  # noqa: F401
from storage.models.lemma_fact import LemmaFact
from storage.models.schema import Base, Lemma

SCRIPT = Path(__file__).resolve().parents[3] / "migrations/20261012_import_noun_concept_facts.py"
_spec = importlib.util.spec_from_file_location("noun_concept_fact_import", SCRIPT)
assert _spec is not None and _spec.loader is not None
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)


@pytest.mark.parametrize("legacy_type", ["quantifiable", "has_individual_instances"])
def test_targeted_import_and_rerun(tmp_path: Path, legacy_type: str) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        lemma = Lemma(
            guid="N02_001",
            lemma_text="dog",
            definition_text="Keep this definition",
            pos_type="noun",
            pos_subtype="animal",
            difficulty_level=2,
        )
        lemma.lemma_facts.extend(
            [
                LemmaFact(fact_type=legacy_type, fact_value="true"),
                LemmaFact(
                    fact_type="unrelated", fact_value="keep", notes="Keep notes", verified=True
                ),
            ]
        )
        session.add(lemma)
        session.commit()
        record: Dict[str, Any] = {
            "guid": lemma.guid,
            "concept_label": "dog",
            "pos_type": "noun",
            "facts": {"individuation": "individual", "concreteness": "physical"},
        }
        path = tmp_path / "base.jsonl"
        path.write_text(json.dumps(record) + "\n")
        assert migration.stage_import(session, tmp_path) == (2, 1)
        session.commit()
        assert migration.stage_import(session, tmp_path) == (0, 0)
        assert {fact.fact_type: fact.fact_value for fact in lemma.lemma_facts} == {
            "unrelated": "keep",
            "individuation": "individual",
            "concreteness": "physical",
        }
        assert lemma.definition_text == "Keep this definition"
        assert lemma.lemma_facts[0].notes == "Keep notes"
        assert lemma.lemma_facts[0].verified
        # An unmigrated legacy sense blocks the entire operation before staging changes.
        extra = Lemma(guid="N02_002", lemma_text="cat", definition_text="cat", pos_type="noun")
        extra.lemma_facts.append(LemmaFact(fact_type=legacy_type, fact_value="false"))
        session.add(extra)
        session.commit()
        record["facts"]["concreteness"] = "abstract"
        path.write_text(json.dumps(record) + "\n")
        with pytest.raises(ValueError, match="no reviewed release replacement"):
            migration.stage_import(session, tmp_path)
        assert (
            next(f.fact_value for f in lemma.lemma_facts if f.fact_type == "concreteness")
            == "physical"
        )
