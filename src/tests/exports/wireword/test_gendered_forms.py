"""Gender counterparts are explicit cards, never spelling alternatives."""

import json
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import storage.models  # noqa: F401
from exports.wireword.export_wireword import WirewordExporter
from storage.crud.variant_form import add_variant_form
from storage.models.grammar_fact import GrammarFact
from storage.models.schema import AudioQualityReview, Base, Lemma, LemmaTranslation
from storage.variant_audio import gender_audio_slot


def test_gendered_export_keeps_three_entries_and_variant_audio(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        lemma = Lemma(
            guid="N35_076",
            lemma_text="cousin",
            definition_text="A cousin.",
            pos_type="noun",
            pos_subtype="family_relation",
            difficulty_level=18,
        )
        session.add(lemma)
        session.flush()
        session.add(LemmaTranslation(lemma_id=lemma.id, language_code="es", translation="primo"))
        # Deliberately different from the male form: never infer the default's gender.
        session.add(
            GrammarFact(
                lemma_id=lemma.id,
                language_code="es",
                fact_type="grammatical_gender",
                fact_value="common",
            )
        )
        for gender, text in (("male", "primo"), ("female", "prima")):
            for slot, form_text in (("singular", text), ("plural", text + "s")):
                add_variant_form(
                    session,
                    lemma,
                    form_text,
                    "es",
                    gender,
                    f"noun/es_{slot}",
                    variant_kind="gender",
                    is_base_form=slot == "singular",
                    grammatical_gender="masculine" if gender == "male" else "feminine",
                    link_word_token=False,
                )
        session.add(
            AudioQualityReview(
                guid=lemma.guid,
                language_code="es",
                voice_name="test",
                grammatical_form=gender_audio_slot("female"),
                filename="prima.mp3",
                expected_text="prima",
                manifest_md5="female-md5",
                status="approved",
                s3_prod_url="https://example.com/prima.mp3",
            )
        )
        session.commit()
    exporter = WirewordExporter(language="es")
    output = tmp_path / "words.json"
    with patch.object(exporter, "get_session", side_effect=lambda: Session(engine)):
        success, _ = exporter.export_to_wireword_format(str(output))
    assert success
    rows = json.loads(output.read_text())
    assert len(rows) == 1
    word = rows[0]
    assert word.get("target_alternatives", []) == []
    forms = word["gendered_forms"]
    assert [entry["referent_gender"] for entry in forms] == ["unspecified", "male", "female"]
    assert [entry["base_target"] for entry in forms] == ["primo", "primo", "prima"]
    assert [entry["grammar_metadata"]["grammatical_gender"] for entry in forms] == [
        "common",
        "masculine",
        "feminine",
    ]
    assert "audio" not in forms[0]
    assert "audio" not in forms[1]
    assert forms[2]["audio"] == {"test": "female-md5"}
    assert {form["text"] for form in forms[2]["grammatical_forms"]} == {"prima", "primas"}
    engine.dispose()


def test_source_counterpart_and_absent_target_are_not_inferred() -> None:
    from exports.wireword.gendered_forms import build_gendered_forms

    word = {"guid": "N36_047", "base_target": "actor", "base_english": "actor"}
    counterparts = {
        "en": [{"key": "female", "forms": [{"text": "actress", "is_base_form": True}]}],
        "es": [
            {
                "key": "female",
                "grammatical_gender": "feminine",
                "forms": [
                    {"text": "actriz", "grammatical_form": "noun/es_singular", "is_base_form": True}
                ],
            }
        ],
    }
    forms = build_gendered_forms(word, counterparts, "es", "en", {})
    assert [form["referent_gender"] for form in forms] == ["unspecified", "female"]
    assert forms[1]["base_english"] == "actress"
    assert forms[1]["base_target"] == "actriz"
    assert build_gendered_forms(word, {"en": counterparts["en"]}, "es", "en", {}) == []
