"""WireWord ships the zh measure-word lists as lists, and omits unchecked ones."""

import json
from pathlib import Path
from typing import Dict
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import storage.models  # noqa: F401
from exports.wireword.export_wireword import WirewordExporter
from storage.models import Base, Lemma, LemmaTranslation
from storage.models.grammar_fact import GrammarFact


def test_measure_word_lists_export_as_lists(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    facts: Dict[str, Dict[str, str]] = {
        "chair": {"measure_words": "把", "measure_words_alternates": "张, 个"},
        "soup": {
            "measure_words": "碗",
            "measure_words_alternates": "none",
            "measure_words_portions": "杯, 锅",
        },
    }
    translations = {"chair": "椅子", "soup": "汤"}
    with Session(engine) as session:
        for index, (text, lemma_facts) in enumerate(facts.items(), start=1):
            lemma = Lemma(
                guid=f"N01_00{index}",
                lemma_text=text,
                definition_text=text,
                pos_type="noun",
                pos_subtype="furniture",
                difficulty_level=1,
            )
            session.add(lemma)
            session.flush()
            session.add(
                LemmaTranslation(
                    lemma_id=lemma.id, language_code="zh", translation=translations[text]
                )
            )
            for fact_type, value in lemma_facts.items():
                session.add(
                    GrammarFact(
                        lemma_id=lemma.id,
                        language_code="zh",
                        fact_type=fact_type,
                        fact_value=value,
                    )
                )
        session.commit()
    exporter = WirewordExporter(language="zh")
    output = tmp_path / "words.json"
    with patch.object(exporter, "get_session", side_effect=lambda: Session(engine)):
        success, _ = exporter.export_to_wireword_format(str(output))
    assert success
    metadata = {
        row["base_target"]: row["grammar_metadata"] for row in json.loads(output.read_text())
    }
    assert metadata["椅子"] == {"measure_words": "把", "measure_words_alternates": ["张", "个"]}
    assert metadata["汤"] == {
        "measure_words": "碗",
        "measure_words_alternates": [],
        "measure_words_portions": ["杯", "锅"],
    }
    engine.dispose()
