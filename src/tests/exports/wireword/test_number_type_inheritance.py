"""WireWord resolves Spanish number facts even when regional words differ."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import storage.models  # noqa: F401
from exports.wireword.export_wireword import WirewordExporter
from storage.models import Base, Lemma, LemmaTranslation
from storage.models.grammar_fact import GrammarFact


@pytest.mark.parametrize("regional_value", [None, "regular"])
def test_export_inherits_number_only(tmp_path: Path, regional_value: str | None) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        lemma = Lemma(
            guid="N01_001",
            lemma_text="glasses",
            definition_text="eyewear",
            pos_type="noun",
            pos_subtype="clothing",
            difficulty_level=1,
        )
        session.add(lemma)
        session.flush()
        for language, word in (("es", "gafas"), ("es-419", "anteojos")):
            session.add(
                LemmaTranslation(lemma_id=lemma.id, language_code=language, translation=word)
            )
        for fact_type, value in (("number_type", "plurale_tantum"), ("plural", "gafas")):
            session.add(
                GrammarFact(
                    lemma_id=lemma.id, language_code="es", fact_type=fact_type, fact_value=value
                )
            )
        if regional_value:
            session.add(
                GrammarFact(
                    lemma_id=lemma.id,
                    language_code="es-419",
                    fact_type="number_type",
                    fact_value=regional_value,
                )
            )
        session.commit()
    exporter = WirewordExporter(language="es-419")
    output = tmp_path / "words.json"
    with patch.object(exporter, "get_session", side_effect=lambda: Session(engine)):
        success, _ = exporter.export_to_wireword_format(str(output))
    assert success
    rows = json.loads(output.read_text())
    assert rows[0]["base_target"] == "anteojos"
    assert rows[0]["grammar_metadata"] == {"number_type": regional_value or "plurale_tantum"}
    engine.dispose()
