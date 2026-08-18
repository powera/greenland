"""Functional test for the phrase translation sync, driven through HTTP.

``set_phrase_translation`` assigns the status fields unconditionally, and the
sync called it positionally with only the text -- so pulling one language from
release nulled that translation's ``translation_status`` and
``translation_status_note``, both of which the exporter ships and the additions
path imports.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest
from flask.testing import FlaskClient
from sqlalchemy.orm import Session

from barsukas.routes.sync import sync_phrase_release
from storage.crud.phrase import set_phrase_translation
from storage.models.schema import Phrase, PhraseTranslation


@pytest.fixture()
def phrase_release_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the phrase sync at a scratch release tree."""
    directory = tmp_path / "phrases"
    directory.mkdir(parents=True)
    monkeypatch.setattr(sync_phrase_release, "DEFAULT_PHRASE_RELEASE_DIR", directory)
    yield directory


def _write_phrases(release_dir: Path, subtype: str, records: List[Dict[str, Any]]) -> Path:
    target = release_dir / subtype
    target.mkdir(parents=True, exist_ok=True)
    path = target / "base.jsonl"
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    return path


def _seed_phrase(db_session: Session) -> int:
    phrase = Phrase(guid="F01_001", phrase_subtype="greeting", label="See you later")
    db_session.add(phrase)
    db_session.flush()
    set_phrase_translation(
        db_session,
        phrase,
        "lt",
        "Iki",
        translation_status="needs_review",
        translation_status_note="too informal",
    )
    db_session.commit()
    return int(phrase.id)


def _translation(db_session: Session, phrase_id: int, lang: str) -> PhraseTranslation:
    db_session.expire_all()
    return (
        db_session.query(PhraseTranslation)
        .filter(
            PhraseTranslation.phrase_id == phrase_id,
            PhraseTranslation.language_code == lang,
        )
        .one()
    )


class TestApplyTranslations:
    def test_use_release_keeps_the_status_metadata(
        self, client: FlaskClient, phrase_release_dir: Path, db_session: Session
    ) -> None:
        phrase_id = _seed_phrase(db_session)
        _write_phrases(
            phrase_release_dir,
            "greeting",
            [
                {
                    "guid": "F01_001",
                    "concept_label": "See you later",
                    "translations": {"lt": "Iki pasimatymo"},
                    "translation_metadata": {
                        "lt": {
                            "translation_status": "approved",
                            "translation_status_note": "confirmed by reviewer",
                        }
                    },
                }
            ],
        )

        response = client.post(
            "/sync/phrases/translations/apply",
            data={f"action_{phrase_id}_lt": "use_release"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        updated = _translation(db_session, phrase_id, "lt")
        assert updated.translation == "Iki pasimatymo"
        assert updated.translation_status == "approved"
        assert updated.translation_status_note == "confirmed by reviewer"

    def test_release_without_metadata_clears_the_status(
        self, client: FlaskClient, phrase_release_dir: Path, db_session: Session
    ) -> None:
        """The release record is authoritative: no metadata means no metadata."""
        phrase_id = _seed_phrase(db_session)
        _write_phrases(
            phrase_release_dir,
            "greeting",
            [
                {
                    "guid": "F01_001",
                    "concept_label": "See you later",
                    "translations": {"lt": "Iki pasimatymo"},
                }
            ],
        )

        response = client.post(
            "/sync/phrases/translations/apply",
            data={f"action_{phrase_id}_lt": "use_release"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        updated = _translation(db_session, phrase_id, "lt")
        assert updated.translation == "Iki pasimatymo"
        assert updated.translation_status is None
