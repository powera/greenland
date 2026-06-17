from sqlalchemy.orm import Session, sessionmaker

from storage.models.schema import Lemma, LemmaDifficultyOverride


def test_single_translation_reports_not_populated(client) -> None:
    response = client.get("/api/v1/lemma/V01_001/translations?language=sa")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"] == {}
    absence = payload["metadata"]["translation_absence"]["sa"]
    assert absence["reason"] == "not_populated"
    assert absence["reason_codes"] == ["not_populated"]
    assert absence["effective_difficulty_level"] == 3


def test_single_translation_reports_language_exclusion(client, db_engine) -> None:
    factory = sessionmaker(bind=db_engine)
    session: Session = factory()
    session.add(
        LemmaDifficultyOverride(
            lemma_id=1,
            language_code="la",
            difficulty_level=-1,
            notes="No ordinary Classical Latin learner cue.",
        )
    )
    session.commit()
    session.close()

    response = client.get("/api/v1/lemma/V01_001/translations?language=la")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"] == {}
    absence = payload["metadata"]["translation_absence"]["la"]
    assert absence["reason"] == "excluded"
    assert absence["reason_codes"] == ["excluded"]
    assert absence["effective_difficulty_level"] == -1
    assert absence["difficulty_override"] == {
        "difficulty_level": -1,
        "notes": "No ordinary Classical Latin learner cue.",
    }


def test_single_translation_reports_lexical_gap(client, db_engine) -> None:
    factory = sessionmaker(bind=db_engine)
    session: Session = factory()
    lemma = session.query(Lemma).filter(Lemma.guid == "N01_001").one()
    lemma.lexical_gap_reason = "post-classical domestic architecture sense"
    session.commit()
    session.close()

    response = client.get("/api/v1/lemma/N01_001/translations?language=la")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"] == {}
    absence = payload["metadata"]["translation_absence"]["la"]
    assert absence["reason"] == "lexical_gap"
    assert absence["reason_codes"] == ["lexical_gap"]
    assert absence["lexical_gap_reason"] == "post-classical domestic architecture sense"


def test_bulk_translation_absence_is_keyed_by_guid_and_language(client, db_engine) -> None:
    factory = sessionmaker(bind=db_engine)
    session: Session = factory()
    lemma = session.query(Lemma).filter(Lemma.guid == "N01_001").one()
    lemma.lexical_gap_reason = "post-classical domestic architecture sense"
    session.commit()
    session.close()

    response = client.get("/api/v1/lemmas/translations?guids=V01_001,N01_001&language=la")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"] == {"N01_001": {}, "V01_001": {}}
    absence = payload["metadata"]["translation_absence"]
    assert absence["V01_001"]["la"]["reason"] == "not_populated"
    assert absence["N01_001"]["la"]["reason"] == "lexical_gap"


def test_lemma_summaries_include_lexical_gap_reason(client, db_engine) -> None:
    factory = sessionmaker(bind=db_engine)
    session: Session = factory()
    lemma = session.query(Lemma).filter(Lemma.guid == "N01_001").one()
    lemma.lexical_gap_reason = "post-classical domestic architecture sense"
    session.commit()
    session.close()

    detail_response = client.get("/api/v1/lemma/N01_001")
    list_response = client.get("/api/v1/lemmas/by-difficulty?difficulty=2")

    assert detail_response.status_code == 200
    assert list_response.status_code == 200
    assert (
        detail_response.get_json()["data"]["lexical_gap_reason"]
        == "post-classical domestic architecture sense"
    )
    listed = list_response.get_json()["data"][0]
    assert listed["guid"] == "N01_001"
    assert listed["lexical_gap_reason"] == "post-classical domestic architecture sense"


def test_by_difficulty_missing_translation_includes_absence_reason(client, db_engine) -> None:
    factory = sessionmaker(bind=db_engine)
    session: Session = factory()
    session.add(
        LemmaDifficultyOverride(
            lemma_id=1,
            language_code="la",
            difficulty_level=-1,
            notes="No ordinary Classical Latin learner cue.",
        )
    )
    session.commit()
    session.close()

    response = client.get("/api/v1/lemmas/by-difficulty?difficulty=3&missing_translation=la")

    assert response.status_code == 200
    payload = response.get_json()
    listed = payload["data"][0]
    assert listed["guid"] == "V01_001"
    absence = listed["translation_absence"]["la"]
    assert absence["reason"] == "excluded"
    assert absence["difficulty_override"]["notes"] == "No ordinary Classical Latin learner cue."


def test_translation_metadata_marks_late_construction(client) -> None:
    response = client.patch(
        "/api/v1/lemma/V01_001/translations/fr/metadata",
        json={
            "translation_status": "late_construction",
            "translation_status_note": "Modern learner cue, not classical usage.",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["translation_status"] == "late_construction"
    assert payload["data"]["translation_status_note"] == "Modern learner cue, not classical usage."

    single_response = client.get("/api/v1/lemma/V01_001/translations?language=fr")
    bulk_response = client.get("/api/v1/lemmas/translations?guids=V01_001&language=fr")

    assert single_response.status_code == 200
    assert bulk_response.status_code == 200
    assert single_response.get_json()["metadata"]["translation_metadata"]["fr"] == {
        "translation_status": "late_construction",
        "translation_status_note": "Modern learner cue, not classical usage.",
    }
    assert bulk_response.get_json()["metadata"]["translation_metadata"]["V01_001"]["fr"] == {
        "translation_status": "late_construction",
        "translation_status_note": "Modern learner cue, not classical usage.",
    }


def test_translation_metadata_rejects_unknown_status(client) -> None:
    response = client.patch(
        "/api/v1/lemma/V01_001/translations/fr/metadata",
        json={"translation_status": "ancient-ish"},
    )

    assert response.status_code == 400
    assert "translation_status must be one of" in response.get_json()["error"]
