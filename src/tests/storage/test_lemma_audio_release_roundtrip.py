"""Round-trip tests for lemma audio between SQLite and data/release.

Lemma audio lives in per-category ``audio.jsonl`` files under
``data/release/lemmas``. Two transformations keep SQLite and the release tree in
sync:

  * Export:  SQLite -> ``audio.jsonl``  (``export_sqlite_to_lemma_audio_release``)
  * Sync:    ``audio.jsonl`` -> SQLite  (``import_lemma_audio_release_to_sqlite``)

These tests assert the exported records carry the English anchor word and that
the sync upserts (rather than duplicates) audio rows, links them to their lemma
by GUID, and prunes on request.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from typing import Dict, List

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import storage.models  # noqa: F401  (register every table for FK targets)
from storage.migrate import (
    export_sqlite_to_lemma_audio_release,
    import_lemma_audio_release_to_sqlite,
)
from storage.models.schema import AudioQualityReview, Base, Lemma

LEMMA_GUID = "V06_004"


def _build_lemma(db: Session) -> Lemma:
    lemma = Lemma(
        lemma_text="buy",
        definition_text="to acquire in exchange for money",
        pos_type="verb",
        pos_subtype="possession",
        guid=LEMMA_GUID,
    )
    db.add(lemma)
    db.flush()
    return lemma


def _build_source_db(sqlite_path: str) -> None:
    """SQLite database with one lemma and one approved audio review."""
    engine = create_engine(f"sqlite:///{sqlite_path}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        lemma = _build_lemma(db)
        db.add(
            AudioQualityReview(
                guid=LEMMA_GUID,
                lemma_id=lemma.id,
                language_code="lt",
                voice_name="jonas",
                grammatical_form=None,
                filename="V06_004_pirkti.mp3",
                expected_text="pirkti",
                manifest_md5="deadbeef",
                status="approved",
                s3_prod_url="https://example.test/prod/lt/jonas/deadbeef.mp3",
                s3_staging_url="https://example.test/staging/lt/jonas/deadbeef.mp3",
                staging_agent="vieversys",
            )
        )
        db.commit()


def _read_audio_records(release_dir: str) -> List[dict]:
    records: List[dict] = []
    audio_path = os.path.join(release_dir, "verbs", "possession", "audio.jsonl")
    with open(audio_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


class LemmaAudioReleaseRoundTripTest(unittest.TestCase):
    tmpdir: str
    source_db: str
    release_dir: str

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp(prefix="lemma_audio_roundtrip_")
        self.source_db = os.path.join(self.tmpdir, "source.sqlite")
        self.release_dir = os.path.join(self.tmpdir, "lemmas")
        _build_source_db(self.source_db)
        export_sqlite_to_lemma_audio_release(self.source_db, self.release_dir)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _fresh_db_with_lemma(self) -> str:
        """A target DB that has the lemma but no audio yet."""
        target = os.path.join(self.tmpdir, "target.sqlite")
        engine = create_engine(f"sqlite:///{target}")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            _build_lemma(db)
            db.commit()
        return target

    # ---- Export format ---------------------------------------------------

    def test_export_includes_english_anchor(self) -> None:
        records = _read_audio_records(self.release_dir)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["guid"], LEMMA_GUID)
        self.assertEqual(record["english"], "buy")
        self.assertEqual(record["audio"][0]["expected_text"], "pirkti")
        self.assertEqual(record["audio"][0]["voice_name"], "jonas")

    # ---- Sync (import) path ----------------------------------------------

    def test_sync_inserts_and_links_audio(self) -> None:
        target = self._fresh_db_with_lemma()
        import_lemma_audio_release_to_sqlite(target, self.release_dir)

        engine = create_engine(f"sqlite:///{target}")
        with Session(engine) as db:
            reviews = db.query(AudioQualityReview).all()
            self.assertEqual(len(reviews), 1)
            review = reviews[0]
            self.assertEqual(review.guid, LEMMA_GUID)
            self.assertEqual(review.language_code, "lt")
            self.assertEqual(review.voice_name, "jonas")
            self.assertEqual(review.expected_text, "pirkti")
            self.assertEqual(review.manifest_md5, "deadbeef")
            self.assertEqual(review.status, "approved")
            self.assertEqual(review.staging_agent, "vieversys")
            lemma = db.query(Lemma).filter(Lemma.guid == LEMMA_GUID).one()
            self.assertEqual(review.lemma_id, lemma.id)

    def test_sync_is_idempotent(self) -> None:
        target = self._fresh_db_with_lemma()
        import_lemma_audio_release_to_sqlite(target, self.release_dir)
        import_lemma_audio_release_to_sqlite(target, self.release_dir)

        engine = create_engine(f"sqlite:///{target}")
        with Session(engine) as db:
            self.assertEqual(db.query(AudioQualityReview).count(), 1)

    def test_sync_updates_changed_fields(self) -> None:
        target = self._fresh_db_with_lemma()
        import_lemma_audio_release_to_sqlite(target, self.release_dir)

        # Rewrite the release audio.jsonl with an updated md5 and prod URL.
        records = _read_audio_records(self.release_dir)
        records[0]["audio"][0]["manifest_md5"] = "cafef00d"
        records[0]["audio"][0]["s3_prod_url"] = "https://example.test/prod/new.mp3"
        audio_path = os.path.join(self.release_dir, "verbs", "possession", "audio.jsonl")
        with open(audio_path, "w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

        import_lemma_audio_release_to_sqlite(target, self.release_dir)

        engine = create_engine(f"sqlite:///{target}")
        with Session(engine) as db:
            review = db.query(AudioQualityReview).one()
            self.assertEqual(review.manifest_md5, "cafef00d")
            self.assertEqual(review.s3_prod_url, "https://example.test/prod/new.mp3")

    def test_sync_prune_removes_missing_audio(self) -> None:
        target = self._fresh_db_with_lemma()
        import_lemma_audio_release_to_sqlite(target, self.release_dir)

        # Empty the release audio, then sync with pruning enabled.
        audio_path = os.path.join(self.release_dir, "verbs", "possession", "audio.jsonl")
        open(audio_path, "w", encoding="utf-8").close()

        import_lemma_audio_release_to_sqlite(target, self.release_dir, prune=True)

        engine = create_engine(f"sqlite:///{target}")
        with Session(engine) as db:
            self.assertEqual(db.query(AudioQualityReview).count(), 0)

    def test_sync_without_prune_keeps_missing_audio(self) -> None:
        target = self._fresh_db_with_lemma()
        import_lemma_audio_release_to_sqlite(target, self.release_dir)

        audio_path = os.path.join(self.release_dir, "verbs", "possession", "audio.jsonl")
        open(audio_path, "w", encoding="utf-8").close()

        import_lemma_audio_release_to_sqlite(target, self.release_dir, prune=False)

        engine = create_engine(f"sqlite:///{target}")
        with Session(engine) as db:
            self.assertEqual(db.query(AudioQualityReview).count(), 1)


if __name__ == "__main__":
    unittest.main()
