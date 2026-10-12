"""The concept dimensions is shared by exports for every target language."""

import json
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import storage.models  # noqa: F401 -- register all tables
from exports.wireword.export_wireword import WirewordExporter
from storage.models.lemma_fact import LemmaFact
from storage.models.schema import Base, Lemma, LemmaTranslation


def test_concept_facts_export_is_language_independent(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        for index, (text, value, concreteness) in enumerate(
            (
                ("horse", "individual", "physical"),
                ("justice", "non_individuated", "abstract"),
                ("unknown", None, None),
            ),
            start=1,
        ):
            lemma = Lemma(
                guid=f"N01_{index:03d}",
                lemma_text=text,
                definition_text=text,
                pos_type="noun",
                pos_subtype="animal",
                difficulty_level=1,
            )
            session.add(lemma)
            session.flush()
            for language_code in ("fr", "es", "zh"):
                session.add(
                    LemmaTranslation(
                        lemma_id=lemma.id,
                        language_code=language_code,
                        translation=f"{text}_{language_code}",
                    )
                )
            if value is not None and concreteness is not None:
                session.add(
                    LemmaFact(lemma_id=lemma.id, fact_type="individuation", fact_value=value)
                )
                session.add(
                    LemmaFact(lemma_id=lemma.id, fact_type="concreteness", fact_value=concreteness)
                )
        session.commit()

        session.close()
        for language_code in ("fr", "es", "zh"):
            exporter = WirewordExporter(language=language_code)
            output_path = tmp_path / f"{language_code}.json"
            with patch.object(exporter, "get_session", side_effect=lambda: Session(engine)):
                success, _ = exporter.export_to_wireword_format(str(output_path))
            assert success
            rows: List[Dict[str, Any]] = json.loads(output_path.read_text(encoding="utf-8"))
            by_guid = {row["guid"]: row for row in rows}
            assert by_guid["N01_001"]["individuation"] == "individual"
            assert by_guid["N01_001"]["concreteness"] == "physical"
            assert by_guid["N01_002"]["individuation"] == "non_individuated"
            assert by_guid["N01_002"]["concreteness"] == "abstract"
            assert "individuation" not in by_guid["N01_003"]
            assert "concreteness" not in by_guid["N01_003"]
            assert all(
                "quantifiable" not in row and "has_individual_instances" not in row for row in rows
            )
