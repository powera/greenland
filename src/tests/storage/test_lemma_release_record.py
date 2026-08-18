#!/usr/bin/python3

"""The lemma base.jsonl record: one builder, both directions.

There used to be two builders for this record -- one in the Barsukas sync
blueprint, one inline in ``migrate.export_sqlite_to_release`` -- and they
disagreed. The CLI wrote ``concept_label`` without the disambiguation and
omitted ``qid`` and ``translation_disambiguations``, so a CLI export after any
UI work stripped those from the tree; and because the disambiguation is
recovered *by parsing concept_label*, re-importing then nulled it on every
lemma.

These tests pin the record shape and the round trip, so the two exports cannot
drift apart again.
"""

from __future__ import annotations

import unittest
from typing import Any, Dict

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import storage.models  # noqa: F401 -- register every model before create_all
from storage.models.schema import (
    Base,
    Lemma,
    LemmaDifficultyOverride,
    LemmaTranslation,
)
from storage.release.lemma import (
    build_concept_label,
    decode_db_emoji,
    import_release_record,
    lemma_to_release_record,
    parse_concept_label,
    release_disambiguation,
    release_emoji,
    release_lemma_text,
)


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_full_lemma(session: Session) -> Lemma:
    """A lemma exercising every optional key the record can carry."""
    lemma = Lemma(
        guid="N08_001",
        lemma_text="bat",
        disambiguation="animal",
        definition_text="a flying mammal",
        pos_type="noun",
        pos_subtype="animal",
        difficulty_level=4,
        notes="not the cricket kind",
        lexical_gap_reason=None,
        emoji='[{"type": "unicode", "value": "\\ud83e\\udd87"}]',
    )
    session.add(lemma)
    session.flush()

    session.add(
        LemmaTranslation(
            lemma_id=lemma.id,
            language_code="lt",
            translation="šikšnosparnis",
            disambiguation="gyvūnas",
            translation_status="needs_review",
            translation_status_note="checked against LKŽ",
        )
    )
    session.add(
        LemmaTranslation(lemma_id=lemma.id, language_code="fr", translation="chauve-souris")
    )
    session.add(LemmaDifficultyOverride(lemma_id=lemma.id, language_code="lt", difficulty_level=7))
    session.commit()
    session.refresh(lemma)
    return lemma


class TestConceptLabel(unittest.TestCase):
    """concept_label carries the disambiguation, so it has to round-trip."""

    def test_label_round_trips_through_parse(self) -> None:
        for text, disambiguation in (
            ("bat", "animal"),
            ("bat", None),
            ("light bulb", "electric"),
        ):
            with self.subTest(text=text, disambiguation=disambiguation):
                label = build_concept_label(text, disambiguation)
                self.assertEqual((text, disambiguation), parse_concept_label(label))

    def test_label_without_parens_has_no_disambiguation(self) -> None:
        self.assertEqual(("dog", None), parse_concept_label("dog"))

    def test_only_the_trailing_group_is_the_disambiguation(self) -> None:
        self.assertEqual(("a (b)", "c"), parse_concept_label("a (b) (c)"))


class TestReleaseReaders(unittest.TestCase):
    """Reading a record back."""

    def test_lemma_text_prefers_translations_en(self) -> None:
        record = {"translations": {"en": "bat"}, "concept_label": "bat (animal)"}
        self.assertEqual("bat", release_lemma_text(record))

    def test_lemma_text_falls_back_to_the_label_without_its_sense(self) -> None:
        """An older record has no translations.en; the label must still not leak its sense."""
        self.assertEqual("bat", release_lemma_text({"concept_label": "bat (animal)"}))

    def test_disambiguation_comes_from_the_label(self) -> None:
        self.assertEqual("animal", release_disambiguation({"concept_label": "bat (animal)"}))
        self.assertIsNone(release_disambiguation({"concept_label": "bat"}))
        self.assertIsNone(release_disambiguation({}))

    def test_emoji_shapes_normalize(self) -> None:
        self.assertEqual([{"type": "unicode", "value": "🦇"}], release_emoji({"emoji": ["🦇"]}))
        self.assertEqual([], release_emoji({}))
        self.assertEqual([], decode_db_emoji(None))
        self.assertEqual([], decode_db_emoji("not json"))


class TestLemmaToReleaseRecord(unittest.TestCase):
    """Database -> release."""

    def setUp(self) -> None:
        self.session = _make_session()
        self.lemma = _seed_full_lemma(self.session)

    def tearDown(self) -> None:
        self.session.close()

    def test_record_carries_every_field(self) -> None:
        record = lemma_to_release_record(self.lemma, qid="Q28425")
        self.assertEqual(
            {
                "guid": "N08_001",
                "pos_type": "noun",
                "pos_subtype": "animal",
                "concept_label": "bat (animal)",
                "concept_definition": "a flying mammal",
                "translations": {"en": "bat", "lt": "šikšnosparnis", "fr": "chauve-souris"},
                "difficulty_level": 4,
                "translation_disambiguations": {"lt": "gyvūnas"},
                "translation_metadata": {
                    "lt": {
                        "translation_status": "needs_review",
                        "translation_status_note": "checked against LKŽ",
                    }
                },
                "difficulty_overrides": {"lt": 7},
                "notes": "not the cricket kind",
                "emoji": [{"type": "unicode", "value": "🦇"}],
                "qid": "Q28425",
            },
            record,
        )

    def test_english_is_first_and_order_is_stable(self) -> None:
        """Byte-stability matters: re-exporting an unchanged DB must not churn the file."""
        record = lemma_to_release_record(self.lemma)
        self.assertEqual("en", next(iter(record["translations"])))
        self.assertEqual(
            list(record["translations"]),
            list(lemma_to_release_record(self.lemma)["translations"]),
        )

    def test_unpaired_lemma_has_no_qid_key(self) -> None:
        self.assertNotIn("qid", lemma_to_release_record(self.lemma, qid=None))

    def test_unlevelled_lemma_exports_minus_one(self) -> None:
        self.lemma.difficulty_level = None
        self.assertEqual(-1, lemma_to_release_record(self.lemma)["difficulty_level"])

    def test_empty_optionals_are_omitted_not_nulled(self) -> None:
        """A hand-edited file should not fill up with null-valued keys."""
        self.lemma.notes = None
        self.lemma.emoji = None
        self.lemma.disambiguation = None
        record = lemma_to_release_record(self.lemma)
        self.assertNotIn("notes", record)
        self.assertNotIn("emoji", record)
        self.assertEqual("bat", record["concept_label"])


class TestRoundTrip(unittest.TestCase):
    """release -> database -> release must be a fixed point."""

    def test_import_then_export_reproduces_the_record(self) -> None:
        session = _make_session()
        try:
            original: Dict[str, Any] = {
                "guid": "N08_002",
                "pos_type": "noun",
                "pos_subtype": "animal",
                "concept_label": "crane (bird)",
                "concept_definition": "a long-legged wading bird",
                "translations": {"en": "crane", "lt": "gervė"},
                "difficulty_level": 5,
                "translation_disambiguations": {"lt": "paukštis"},
                "translation_metadata": {"lt": {"translation_status": "verified"}},
                "notes": "not the machine",
                "emoji": [{"type": "unicode", "value": "🐦"}],
            }
            lemma = import_release_record(session, original)
            session.commit()
            session.refresh(lemma)

            # qid is passed in rather than stored on the lemma, and the original
            # record carries none, so nothing to thread through here.
            self.assertEqual(original, lemma_to_release_record(lemma))
        finally:
            session.close()

    def test_import_keeps_the_disambiguation_off_the_headword(self) -> None:
        session = _make_session()
        try:
            lemma = import_release_record(
                session,
                {
                    "guid": "N08_003",
                    "pos_type": "noun",
                    "pos_subtype": "animal",
                    "concept_label": "seal (animal)",
                    "concept_definition": "a marine mammal",
                    "translations": {"en": "seal"},
                    "difficulty_level": 3,
                },
            )
            session.commit()
            self.assertEqual("seal", lemma.lemma_text)
            self.assertEqual("animal", lemma.disambiguation)
        finally:
            session.close()


class TestCliAndUiAgree(unittest.TestCase):
    """The regression that let the two builders drift.

    Both exports now call lemma_to_release_record, so this asserts the shared
    builder emits the keys each side used to emit alone -- qid and
    translation_disambiguations (UI only) and difficulty_overrides (CLI only) --
    and that concept_label keeps its disambiguation, which the CLI dropped.
    """

    def test_shared_builder_emits_both_sides_keys(self) -> None:
        session = _make_session()
        try:
            lemma = _seed_full_lemma(session)
            record = lemma_to_release_record(lemma, qid="Q28425")

            # Formerly UI-only.
            self.assertEqual("Q28425", record["qid"])
            self.assertEqual({"lt": "gyvūnas"}, record["translation_disambiguations"])
            self.assertEqual("bat (animal)", record["concept_label"])

            # Formerly CLI-only.
            self.assertEqual({"lt": 7}, record["difficulty_overrides"])
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
