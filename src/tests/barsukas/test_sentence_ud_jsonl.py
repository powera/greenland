"""Regression tests for UD data in sentence release sync and display."""

import json
from pathlib import Path

from flask.testing import FlaskClient
from sqlalchemy.orm import Session

from storage.models.schema import Sentence, SentenceWord


def test_sentence_release_import_preserves_ud_fields(
    client: FlaskClient, db_engine, tmp_path: Path, monkeypatch
) -> None:
    """Barsukas additions import restores decomposition and its UD annotation."""
    release_dir = tmp_path / "sentences"
    release_file = release_dir / "general" / "verbs" / "transitive" / "base.jsonl"
    release_file.parent.mkdir(parents=True)
    record = {
        "guid": "S_UD_IMPORT",
        "translations": {"en": "I eat"},
        "words": [
            {
                "language_code": "en",
                "position": 0,
                "word_role": "verb",
                "lemma_guid": "V01_001",
                "english_text": "eat",
                "target_language_text": "eat",
                "grammatical_form": "verb/en_base",
                "grammatical_case": None,
                "declined_form": "eat",
                "ud_relation": "root",
                "ud_head_position": -1,
            }
        ],
    }
    release_file.write_text(json.dumps(record) + "\n", encoding="utf-8")

    monkeypatch.setattr(
        "barsukas.routes.sync.sync_sentence_release.DEFAULT_SENTENCE_RELEASE_DIR",
        release_dir,
    )
    response = client.post(
        "/sync/sentences/additions/apply",
        data={"selected_guids": "S_UD_IMPORT"},
    )
    assert response.status_code == 302

    with Session(db_engine) as db:
        sentence = db.query(Sentence).filter_by(guid="S_UD_IMPORT").one()
        word = db.query(SentenceWord).filter_by(sentence_id=sentence.id).one()
        assert word.lemma_id == 1
        assert word.ud_relation == "root"
        assert word.ud_head_position == -1
        assert word.target_language_text == "eat"


def test_sentence_view_hides_ud_columns_for_unannotated_language(
    client: FlaskClient, db_engine
) -> None:
    with Session(db_engine) as db:
        db.add(
            SentenceWord(
                sentence_id=1,
                language_code="lt",
                position=0,
                part_of_speech="pronoun",
                target_language_text="Aš",
            )
        )
        db.commit()

    response = client.get("/sentences/1")
    assert response.status_code == 200
    assert b"UD Relation" not in response.data
    assert b"UD Head" not in response.data


def test_sentence_view_shows_ud_columns_for_annotated_language(
    client: FlaskClient, db_engine
) -> None:
    with Session(db_engine) as db:
        db.add(
            SentenceWord(
                sentence_id=1,
                language_code="en",
                position=0,
                part_of_speech="verb",
                target_language_text="eat",
                ud_relation="root",
                ud_head_position=-1,
            )
        )
        db.commit()

    response = client.get("/sentences/1")
    assert response.status_code == 200
    assert b"UD Relation" in response.data
    assert b"UD Head" in response.data
