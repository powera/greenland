#!/usr/bin/env python3
"""Tests for the shared AudioQualityReview helpers.

find_existing_review is the lookup that three separate call sites had each
implemented for themselves (agents.gandras, agents.vieversys,
workqueue.handlers.vieversys). It has to mirror both unique constraints on the
table, including the NULL grammatical_form case that SQL will not catch.
"""

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from audiotools.review_records import clear_review_verdict, find_existing_review
from storage.models.schema import AudioQualityReview, Base, Lemma, Sentence


class ReviewRecordTestCase(unittest.TestCase):
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
        self.sentence = Sentence()
        self.session.add(self.sentence)
        self.session.flush()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def add_review(self, **kwargs: object) -> AudioQualityReview:
        kwargs.setdefault("manifest_md5", "abc123")  # NOT NULL on the table
        review = AudioQualityReview(**kwargs)  # type: ignore[arg-type]
        self.session.add(review)
        self.session.flush()
        return review


class TestFindExistingReview(ReviewRecordTestCase):
    def test_finds_lemma_row_with_null_grammatical_form(self) -> None:
        """The base-form case: NULL grammatical_form must still be found.

        This is the one SQL cannot enforce, because it compares NULLs as
        distinct -- so a lookup that misses here silently duplicates rows.
        """
        self.add_review(
            guid="N01_001",
            language_code="lt",
            voice_name="ruta",
            grammatical_form=None,
            filename="a.mp3",
            expected_text="labas",
            status="pending_review",
        )

        found = find_existing_review(
            self.session,
            language_code="lt",
            voice_name="ruta",
            guid="N01_001",
            grammatical_form=None,
        )
        self.assertIsNotNone(found)

    def test_grammatical_form_distinguishes_rows(self) -> None:
        """A different form is a different row, not a collision."""
        self.add_review(
            guid="N01_001",
            language_code="lt",
            voice_name="ruta",
            grammatical_form="plural",
            filename="a.mp3",
            expected_text="labai",
            status="pending_review",
        )

        self.assertIsNone(
            find_existing_review(
                self.session,
                language_code="lt",
                voice_name="ruta",
                guid="N01_001",
                grammatical_form=None,
            )
        )

    def test_finds_sentence_row(self) -> None:
        self.add_review(
            guid=f"S_{self.sentence.id:05d}",
            sentence_id=self.sentence.id,
            language_code="lt",
            voice_name="ruta",
            filename="a.mp3",
            expected_text="labas ten",
            status="pending_review",
        )

        found = find_existing_review(
            self.session,
            language_code="lt",
            voice_name="ruta",
            sentence_id=self.sentence.id,
        )
        self.assertIsNotNone(found)

    def test_voice_and_language_are_part_of_the_key(self) -> None:
        self.add_review(
            guid="N01_001",
            language_code="lt",
            voice_name="ruta",
            grammatical_form=None,
            filename="a.mp3",
            expected_text="labas",
            status="pending_review",
        )

        for language_code, voice_name in (("zh", "ruta"), ("lt", "jonas")):
            self.assertIsNone(
                find_existing_review(
                    self.session,
                    language_code=language_code,
                    voice_name=voice_name,
                    guid="N01_001",
                    grammatical_form=None,
                ),
                f"{language_code}/{voice_name} must not collide",
            )

    def test_returns_none_when_absent(self) -> None:
        self.assertIsNone(
            find_existing_review(
                self.session,
                language_code="lt",
                voice_name="ruta",
                guid="N01_001",
            )
        )

    def test_requires_an_identifier(self) -> None:
        with self.assertRaises(ValueError):
            find_existing_review(self.session, language_code="lt", voice_name="ruta")


class TestClearReviewVerdict(ReviewRecordTestCase):
    def test_clears_every_verdict_field(self) -> None:
        """A row pointed at new audio must not keep an old human judgement."""
        review = self.add_review(
            guid="N01_001",
            language_code="lt",
            voice_name="ruta",
            filename="a.mp3",
            expected_text="labas",
            status="needs_replacement",
            quality_issues="breath noise",
            notes="retake this",
            reviewed_by="alex",
        )

        clear_review_verdict(review)

        self.assertIsNone(review.quality_issues)
        self.assertIsNone(review.notes)
        self.assertIsNone(review.reviewed_at)
        self.assertIsNone(review.reviewed_by)

    def test_leaves_status_alone(self) -> None:
        """Status is the caller's call: pending_review or auto-approved."""
        review = self.add_review(
            guid="N01_001",
            language_code="lt",
            voice_name="ruta",
            filename="a.mp3",
            expected_text="labas",
            status="needs_replacement",
        )

        clear_review_verdict(review)

        self.assertEqual(review.status, "needs_replacement")


if __name__ == "__main__":
    unittest.main()
