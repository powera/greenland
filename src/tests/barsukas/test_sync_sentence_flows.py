"""Functional tests for the sentence sync apply routes, driven through HTTP.

Covers the three round-trip holes the sentence sync had: approved audio rows
were exported and diffed but never imported, a word or hint resolving to a
proper name serialized as an unresolved gap, and the removals page offered
rejected sentences that the export would never write.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest
from flask.testing import FlaskClient
from sqlalchemy.orm import Session

from barsukas.routes.sync import sync_sentence_release
from storage.crud.name_entity import assign_name_guid, create_name
from storage.migrate import _sentence_to_release_record
from storage.models.schema import (
    AudioQualityReview,
    Sentence,
    SentenceWord,
    SentenceWordHint,
)


@pytest.fixture()
def sentence_release_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the sentence sync at a scratch release tree."""
    directory = tmp_path / "sentences"
    directory.mkdir(parents=True)
    monkeypatch.setattr(sync_sentence_release, "DEFAULT_SENTENCE_RELEASE_DIR", directory)
    yield directory


def _write_sentences(release_dir: Path, records: List[Dict[str, Any]]) -> Path:
    target = release_dir / "general" / "verbs" / "transitive"
    target.mkdir(parents=True, exist_ok=True)
    path = target / "base.jsonl"
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    return path


def _sentence(db_session: Session, guid: str) -> Sentence:
    db_session.expire_all()
    return db_session.query(Sentence).filter(Sentence.guid == guid).one()


class TestAudioRoundTrip:
    """Approved audio rows ride in the release record and must come back."""

    def test_import_creates_the_audio_rows(
        self, client: FlaskClient, sentence_release_dir: Path, db_session: Session
    ) -> None:
        _write_sentences(
            sentence_release_dir,
            [
                {
                    "guid": "S_00002",
                    "collection": "general",
                    "pattern_type": "SVO",
                    "minimum_level": 2,
                    "translations": {"en": "She reads", "lt": "Ji skaito"},
                    "audio": [
                        {
                            "language_code": "lt",
                            "voice_name": "alloy",
                            "filename": "S_00002_lt_alloy.mp3",
                            "status": "approved",
                            "expected_text": "Ji skaito",
                            "manifest_md5": "abc123",
                            "s3_prod_url": "https://example.invalid/prod.mp3",
                            "s3_staging_url": "https://example.invalid/staging.mp3",
                            "staging_agent": "vieversys",
                        }
                    ],
                }
            ],
        )

        response = client.post(
            "/sync/sentences/additions/apply",
            data={"selected_guids": "S_00002"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        imported = _sentence(db_session, "S_00002")
        reviews = (
            db_session.query(AudioQualityReview)
            .filter(AudioQualityReview.sentence_id == imported.id)
            .all()
        )
        assert len(reviews) == 1
        review = reviews[0]
        assert review.language_code == "lt"
        assert review.voice_name == "alloy"
        assert review.filename == "S_00002_lt_alloy.mp3"
        assert review.expected_text == "Ji skaito"
        assert review.manifest_md5 == "abc123"
        assert review.s3_prod_url == "https://example.invalid/prod.mp3"
        assert review.staging_agent == "vieversys"
        # Sentence audio is keyed by sentence_id; guid is the lemma-side key.
        assert review.guid is None

    def test_exported_audio_survives_a_reimport(
        self, client: FlaskClient, sentence_release_dir: Path, db_session: Session
    ) -> None:
        """Export -> import -> export must be a fixed point for the audio array."""
        original = {
            "guid": "S_00003",
            "collection": "general",
            "minimum_level": 1,
            "translations": {"en": "He runs"},
            "audio": [
                {
                    "language_code": "lt",
                    "voice_name": "echo",
                    "filename": "S_00003_lt_echo.mp3",
                    "status": "approved",
                    "expected_text": "Jis bėga",
                    "manifest_md5": "def456",
                    "s3_prod_url": None,
                    "s3_staging_url": None,
                    "staging_agent": None,
                }
            ],
        }
        _write_sentences(sentence_release_dir, [original])

        client.post(
            "/sync/sentences/additions/apply",
            data={"selected_guids": "S_00003"},
            follow_redirects=True,
        )

        reexported = _sentence_to_release_record(_sentence(db_session, "S_00003"))
        assert reexported["audio"] == original["audio"]


class TestNameGuidRoundTrip:
    """A slot filled by a proper name is not an unresolved gap."""

    def test_word_and_hint_resolve_their_name(
        self, client: FlaskClient, sentence_release_dir: Path, db_session: Session
    ) -> None:
        name = create_name(db_session, name_text="George", kind="given_name")
        assign_name_guid(db_session, name)
        db_session.commit()
        name_guid = name.guid

        _write_sentences(
            sentence_release_dir,
            [
                {
                    "guid": "S_00004",
                    "collection": "general",
                    "minimum_level": 1,
                    "translations": {"en": "George eats"},
                    "word_hints": [
                        {
                            "position": 0,
                            "slot_name": "subject",
                            "lemma_guid": None,
                            "name_guid": name_guid,
                            "english_text": "George",
                        }
                    ],
                    "words": [
                        {
                            "language_code": "en",
                            "position": 0,
                            "word_role": "propn",
                            "lemma_guid": None,
                            "name_guid": name_guid,
                            "english_text": "George",
                            "target_language_text": "George",
                        }
                    ],
                }
            ],
        )

        response = client.post(
            "/sync/sentences/additions/apply",
            data={"selected_guids": "S_00004"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        imported = _sentence(db_session, "S_00004")
        hint = (
            db_session.query(SentenceWordHint)
            .filter(SentenceWordHint.sentence_id == imported.id)
            .one()
        )
        assert hint.name_id == name.id
        assert hint.lemma_id is None

        word = db_session.query(SentenceWord).filter(SentenceWord.sentence_id == imported.id).one()
        assert word.name_id == name.id
        assert word.lemma_id is None

    def test_export_emits_the_name_guid(
        self, client: FlaskClient, sentence_release_dir: Path, db_session: Session
    ) -> None:
        name = create_name(db_session, name_text="Maria", kind="given_name")
        assign_name_guid(db_session, name)
        sentence = db_session.query(Sentence).filter(Sentence.guid == "S_00001").one()
        db_session.add(
            SentenceWord(
                sentence_id=sentence.id,
                name_id=name.id,
                language_code="en",
                position=0,
                part_of_speech="propn",
                english_text="Maria",
            )
        )
        db_session.commit()

        record = _sentence_to_release_record(_sentence(db_session, "S_00001"))
        assert record["words"][0]["name_guid"] == name.guid
        assert record["words"][0]["lemma_guid"] is None

    def test_unknown_name_guid_blocks_the_import(
        self, client: FlaskClient, sentence_release_dir: Path, db_session: Session
    ) -> None:
        """Importing the slot as unresolved would lose what name_guid records."""
        _write_sentences(
            sentence_release_dir,
            [
                {
                    "guid": "S_00005",
                    "collection": "general",
                    "minimum_level": 1,
                    "translations": {"en": "Nobody knows"},
                    "words": [
                        {
                            "language_code": "en",
                            "position": 0,
                            "word_role": "propn",
                            "lemma_guid": None,
                            "name_guid": "E01_999",
                            "english_text": "Nobody",
                        }
                    ],
                }
            ],
        )

        response = client.post(
            "/sync/sentences/additions/apply",
            data={"selected_guids": "S_00005"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "missing name GUIDs" in response.get_data(as_text=True)

        db_session.expire_all()
        assert db_session.query(Sentence).filter(Sentence.guid == "S_00005").one_or_none() is None


class TestRemovalsExcludesRejected:
    """The removals page and the export must agree about the same row."""

    def test_rejected_sentence_is_not_offered_for_deletion(
        self, client: FlaskClient, sentence_release_dir: Path, db_session: Session
    ) -> None:
        rejected = Sentence(
            guid="S_09999", pattern_type="SVO", minimum_level=1, verified=False, rejected=True
        )
        db_session.add(rejected)
        db_session.commit()

        response = client.get("/sync/sentences/removals")

        assert response.status_code == 200
        assert "S_09999" not in response.get_data(as_text=True)

    def test_unrejected_sentence_is_still_offered(
        self, client: FlaskClient, sentence_release_dir: Path, db_session: Session
    ) -> None:
        """Guard against the filter swallowing everything."""
        response = client.get("/sync/sentences/removals")

        assert response.status_code == 200
        # S_00001 is seeded, not rejected, and absent from the empty release tree.
        assert "S_00001" in response.get_data(as_text=True)
