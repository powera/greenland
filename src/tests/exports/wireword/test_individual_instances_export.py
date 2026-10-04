"""The noun instance fact is shared by exports for every target language."""

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


def test_individual_instances_export_is_language_independent(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        for index, (text, value, fact_type) in enumerate(
            (
                ("horse", "true", "quantifiable"),
                ("salt", "false", "has_individual_instances"),
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
            for language_code in ("fr", "es"):
                session.add(
                    LemmaTranslation(
                        lemma_id=lemma.id,
                        language_code=language_code,
                        translation=f"{text}_{language_code}",
                    )
                )
            if fact_type is not None and value is not None:
                session.add(LemmaFact(lemma_id=lemma.id, fact_type=fact_type, fact_value=value))
        session.commit()

        session.close()
        for language_code in ("fr", "es"):
            exporter = WirewordExporter(language=language_code)
            output_path = tmp_path / f"{language_code}.json"
            with patch.object(exporter, "get_session", side_effect=lambda: Session(engine)):
                success, _ = exporter.export_to_wireword_format(str(output_path))
            assert success
            rows: List[Dict[str, Any]] = json.loads(output_path.read_text(encoding="utf-8"))
            by_guid = {row["guid"]: row for row in rows}
            assert by_guid["N01_001"]["has_individual_instances"] is True
            assert by_guid["N01_001"]["quantifiable"] is True
            assert by_guid["N01_002"]["has_individual_instances"] is False
            assert by_guid["N01_002"]["quantifiable"] is False
            assert "has_individual_instances" not in by_guid["N01_003"]
