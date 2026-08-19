#!/usr/bin/env python3
"""Tests for the AudioQualityReview upsert used by the audio workqueue handlers.

Regression coverage for the handlers inserting a fresh row on every run. The two
unique constraints on the table fail differently, so both paths are covered:

* Sentence audio hits uq_audio_review_sentence (sentence_id, language_code,
  voice_name) - every column is non-NULL, so regenerating raised IntegrityError
  and the task failed.
* Lemma audio is covered by uq_audio_review_lemma (guid, language_code,
  voice_name, grammatical_form), and these handlers always leave
  grammatical_form NULL. SQL compares NULLs as distinct, so the constraint never
  fired and duplicate rows accumulated silently instead - one more per
  regeneration, all shown in the review UI.
"""

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models.schema import AudioQualityReview, Base, Lemma, Sentence
from workqueue.handlers.vieversys import _upsert_review_record


class AudioReviewUpsertTestCase(unittest.TestCase):
    """Shared in-memory database for the upsert tests."""

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

        self.lemma = Lemma(
            lemma_text="hello",
            definition_text="a greeting",
            pos_type="noun",
            guid="N01_001",
        )
        self.session.add(self.lemma)
        self.session.flush()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def rows(self) -> list[AudioQualityReview]:
        return self.session.query(AudioQualityReview).all()


class TestLemmaUpsert(AudioReviewUpsertTestCase):
    """Upserting review rows for lemma audio."""

    def upsert(self, filename: str, md5_hash: str, text: str = "labas") -> None:
        _upsert_review_record(
            self.session,
            lemma=self.lemma,
            language_code="lt",
            voice_name="ruta",
            filename=filename,
            expected_text=text,
            md5_hash=md5_hash,
        )

    def test_creates_row_on_first_generation(self) -> None:
        self.upsert("a.mp3", "aaa")
        self.session.commit()

        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].guid, "N01_001")
        self.assertEqual(rows[0].lemma_id, self.lemma.id)
        self.assertIsNone(rows[0].sentence_id)
        self.assertEqual(rows[0].status, "pending_review")

    def test_regeneration_updates_in_place(self) -> None:
        self.upsert("a.mp3", "aaa")
        self.session.commit()
        original_id = self.rows()[0].id

        # Same lemma/language/voice, new audio. This used to add a second row
        # rather than replace the first: uq_audio_review_lemma covers
        # grammatical_form, which is NULL here, so it never caught the duplicate.
        self.upsert("b.mp3", "bbb", text="labas rytas")
        self.session.commit()

        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].id, original_id)
        self.assertEqual(rows[0].filename, "b.mp3")
        self.assertEqual(rows[0].manifest_md5, "bbb")
        self.assertEqual(rows[0].expected_text, "labas rytas")

    def test_regeneration_resets_review_and_s3_state(self) -> None:
        self.upsert("a.mp3", "aaa")
        self.session.commit()

        row = self.rows()[0]
        row.status = "approved"
        row.s3_staging_url = "https://cdn.example/staging/lt/ruta/aaa.mp3"
        row.s3_staging_manifest_url = "https://cdn.example/staging/lt/ruta/aaa.manifest"
        row.s3_prod_url = "https://cdn.example/prod/lt/ruta/aaa.mp3"
        row.staging_agent = "vieversys"
        row.accepted_by = "someone"
        row.quality_issues = '["echo_effect"]'
        row.reviewed_by = "someone"
        self.session.commit()

        self.upsert("b.mp3", "bbb")
        self.session.commit()

        # The new audio only exists locally, so nothing may keep pointing at the
        # S3 objects for the audio it replaced.
        row = self.rows()[0]
        self.assertEqual(row.status, "pending_review")
        self.assertIsNone(row.s3_staging_url)
        self.assertIsNone(row.s3_staging_manifest_url)
        self.assertIsNone(row.s3_prod_url)
        self.assertIsNone(row.staging_agent)
        self.assertIsNone(row.accepted_by)
        self.assertIsNone(row.quality_issues)
        self.assertIsNone(row.reviewed_by)

    def test_separate_voices_get_separate_rows(self) -> None:
        self.upsert("a.mp3", "aaa")
        _upsert_review_record(
            self.session,
            lemma=self.lemma,
            language_code="lt",
            voice_name="jonas",
            filename="c.mp3",
            expected_text="labas",
            md5_hash="ccc",
        )
        self.session.commit()

        self.assertEqual(len(self.rows()), 2)


class TestSentenceUpsert(AudioReviewUpsertTestCase):
    """Upserting review rows for sentence audio."""

    def setUp(self) -> None:
        super().setUp()
        self.sentence = Sentence()
        self.session.add(self.sentence)
        self.session.flush()

    def upsert(self, filename: str, md5_hash: str) -> None:
        _upsert_review_record(
            self.session,
            sentence_id=self.sentence.id,
            language_code="lt",
            voice_name="ruta",
            filename=filename,
            expected_text="Labas rytas.",
            md5_hash=md5_hash,
        )

    def test_creates_row_with_synthetic_guid(self) -> None:
        self.upsert("a.mp3", "aaa")
        self.session.commit()

        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].sentence_id, self.sentence.id)
        self.assertEqual(rows[0].guid, f"S_{self.sentence.id:05d}")
        self.assertIsNone(rows[0].lemma_id)

    def test_regeneration_updates_in_place(self) -> None:
        self.upsert("a.mp3", "aaa")
        self.session.commit()
        original_id = self.rows()[0].id

        # Used to violate uq_audio_review_sentence.
        self.upsert("b.mp3", "bbb")
        self.session.commit()

        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].id, original_id)
        self.assertEqual(rows[0].manifest_md5, "bbb")


class TestUpsertTargetValidation(AudioReviewUpsertTestCase):
    """The helper takes exactly one of lemma or sentence_id."""

    def call(self, **kwargs: object) -> None:
        _upsert_review_record(
            self.session,
            language_code="lt",
            voice_name="ruta",
            filename="a.mp3",
            expected_text="labas",
            md5_hash="aaa",
            **kwargs,  # type: ignore[arg-type]
        )

    def test_rejects_neither(self) -> None:
        with self.assertRaises(ValueError):
            self.call()

    def test_rejects_both(self) -> None:
        sentence = Sentence()
        self.session.add(sentence)
        self.session.flush()

        with self.assertRaises(ValueError):
            self.call(lemma=self.lemma, sentence_id=sentence.id)


if __name__ == "__main__":
    unittest.main()
