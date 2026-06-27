"""Round-trip tests for the SQLite <-> data/release (JSONL) storage code.

Production relies on three transformations between a writable SQLAlchemy
database and the on-disk JSONL release directory:

  * Export:  SQLite/Postgres  -> JSONL release dir  (``storage.migrate``)
  * Import:  JSONL release dir -> SQLite            (``storage.migrate.import_jsonl_to_sqlite``)
  * Golden:  JSONL release dir -> ephemeral in-memory SQLite served read-only
             by the JSONL backend (``storage.backend.jsonl``), used by hosted
             "golden" personas.

These tests exercise all three with the emphasis on *field completeness*:
every data-bearing column on a sentence, its words, and its lemmas must
survive the trip. A regression here previously dropped the sentence-word text
columns in golden mode, which made the Trakaido sentence-comparison view
render every word as a placeholder dash, and also exported sentence words by
ephemeral integer ``lemma_id`` instead of the stable ``lemma_guid``, breaking
lemma links across a reload.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import tempfile
import unittest
from typing import Dict, List

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Import the full model registry so every table (FK targets included) is created.
import storage.models  # noqa: F401
from storage.backend.config import BackendType, DataSourceConfig
from storage.backend.factory import create_session as create_backend_session
from storage.migrate import export_sqlite_to_jsonl, import_jsonl_to_sqlite
from storage.models import GrammarFact
from storage.models.schema import (
    Base,
    DerivativeForm,
    Lemma,
    LemmaDifficultyOverride,
    LemmaTranslation,
    Sentence,
    SentenceTranslation,
    SentenceWord,
)

# SentenceWord columns that carry persistent data and must survive a round
# trip. ``id``/``sentence_id`` are surrogate keys, ``added_at`` is a timestamp
# Git versioning replaces, and ``lemma_id`` is verified separately (it is an
# ephemeral integer that the release files reference by GUID instead).
SENTENCE_WORD_DATA_COLUMNS = [
    "language_code",
    "position",
    "word_role",
    "english_text",
    "target_language_text",
    "grammatical_form",
    "grammatical_case",
    "declined_form",
]

# The one fully-populated word we assert on: every data column set non-null so a
# dropped field shows up as a mismatch in any of the three transformations.
EXPECTED_WORD: Dict[str, object] = {
    "language_code": "lt",
    "position": 0,
    "word_role": "verb",
    "english_text": "bought",
    "target_language_text": "pirkome",
    "grammatical_form": "verb/lt_1p_past",
    "grammatical_case": "accusative",
    "declined_form": "pirkome",
}

LEMMA_GUID = "V06_004"


def _build_source_db(sqlite_path: str) -> None:
    """Create a SQLite database with one richly-populated lemma and sentence."""
    engine = create_engine(f"sqlite:///{sqlite_path}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        lemma = Lemma(
            lemma_text="buy",
            definition_text="to acquire in exchange for money",
            pos_type="verb",
            guid=LEMMA_GUID,
            difficulty_level=3,
            disambiguation="acquire",
        )
        db.add(lemma)
        db.flush()

        db.add(
            LemmaTranslation(
                lemma_id=lemma.id,
                language_code="lt",
                translation="pirkti",
                disambiguation="įsigyti",
            )
        )
        db.add(LemmaDifficultyOverride(lemma_id=lemma.id, language_code="lt", difficulty_level=2))
        db.add(
            DerivativeForm(
                lemma_id=lemma.id,
                language_code="lt",
                grammatical_form="verb/lt_infinitive",
                derivative_form_text="pirkti",
                is_base_form=True,
            )
        )
        db.add(
            DerivativeForm(
                lemma_id=lemma.id,
                language_code="lt",
                grammatical_form="verb/lt_1p_past",
                derivative_form_text="pirkome",
                is_base_form=False,
            )
        )
        db.add(
            GrammarFact(
                lemma_id=lemma.id,
                language_code="lt",
                fact_type="aspect",
                fact_value="imperfective",
            )
        )

        sentence = Sentence(
            pattern_type="guided",
            minimum_level=2,
            source_filename="roundtrip_fixture",
            tense="past",
        )
        db.add(sentence)
        db.flush()

        db.add(
            SentenceTranslation(
                sentence_id=sentence.id,
                language_code="en",
                translation_text="We bought a printer.",
            )
        )
        db.add(
            SentenceTranslation(
                sentence_id=sentence.id,
                language_code="lt",
                translation_text="Mes pirkome spausdintuvą.",
            )
        )

        # Fully-populated, lemma-linked word.
        db.add(
            SentenceWord(
                sentence_id=sentence.id,
                lemma_id=lemma.id,
                **EXPECTED_WORD,  # type: ignore[arg-type]
            )
        )
        # A second word in another language and without a lemma, so ordering and
        # null-lemma handling are exercised too.
        db.add(
            SentenceWord(
                sentence_id=sentence.id,
                lemma_id=None,
                language_code="en",
                position=1,
                word_role="object",
                english_text="printer",
                target_language_text="printer",
                grammatical_form="noun/en_singular",
                grammatical_case=None,
                declined_form="printer",
            )
        )
        db.commit()


def _iter_release_word_dicts(release_dir: str) -> List[dict]:
    """Return every sentence-word dict written to the release directory."""
    words: List[dict] = []
    pattern = os.path.join(release_dir, "sentences", "**", "*.jsonl")
    for file_path in glob.glob(pattern, recursive=True):
        with open(file_path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                words.extend(record.get("words", []))
    return words


class ReleaseRoundTripTest(unittest.TestCase):
    """Export + both import paths against one fixture database."""

    tmpdir: str
    source_db: str
    release_dir: str
    imported_db: str

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmpdir = tempfile.mkdtemp(prefix="release_roundtrip_")
        cls.source_db = os.path.join(cls.tmpdir, "source.sqlite")
        cls.release_dir = os.path.join(cls.tmpdir, "release")
        cls.imported_db = os.path.join(cls.tmpdir, "imported.sqlite")

        _build_source_db(cls.source_db)
        export_sqlite_to_jsonl(cls.source_db, cls.release_dir)
        import_jsonl_to_sqlite(cls.release_dir, cls.imported_db, force=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    # ---- Export format ---------------------------------------------------

    def test_export_words_reference_lemma_by_guid(self) -> None:
        """Exported words use the stable lemma_guid, never the ephemeral id."""
        words = _iter_release_word_dicts(self.release_dir)
        self.assertTrue(words, "export produced no sentence words")
        linked = [w for w in words if w.get("word_role") == "verb"]
        self.assertEqual(len(linked), 1)
        word = linked[0]
        self.assertEqual(word.get("lemma_guid"), LEMMA_GUID)
        self.assertNotIn(
            "lemma_id",
            word,
            "release files must not carry ephemeral integer lemma_id",
        )

    def test_export_words_preserve_all_data_columns(self) -> None:
        """Every populated data column is present and non-null in the export."""
        words = _iter_release_word_dicts(self.release_dir)
        verb_word = next(w for w in words if w.get("word_role") == "verb")
        for column in SENTENCE_WORD_DATA_COLUMNS:
            self.assertIn(column, verb_word, f"export dropped column {column!r}")
            self.assertEqual(
                verb_word[column],
                EXPECTED_WORD[column],
                f"export changed column {column!r}",
            )

    # ---- SQLite import path (migrate.import_jsonl_to_sqlite) --------------

    def test_sqlite_import_preserves_word_fields(self) -> None:
        engine = create_engine(f"sqlite:///{self.imported_db}")
        with Session(engine) as db:
            self._assert_word_fields(db)

    def test_sqlite_import_resolves_lemma_link_by_guid(self) -> None:
        engine = create_engine(f"sqlite:///{self.imported_db}")
        with Session(engine) as db:
            self._assert_lemma_link(db)

    def test_sqlite_import_preserves_lemma_fields(self) -> None:
        engine = create_engine(f"sqlite:///{self.imported_db}")
        with Session(engine) as db:
            lemma = db.query(Lemma).filter(Lemma.guid == LEMMA_GUID).one()
            self.assertEqual(lemma.lemma_text, "buy")
            self.assertEqual(lemma.pos_type, "verb")
            self.assertEqual(lemma.difficulty_level, 3)
            self.assertEqual(lemma.disambiguation, "acquire")
            self.assertIn("to acquire", (lemma.definition_text or ""))

            translations = {
                t.language_code: t
                for t in db.query(LemmaTranslation)
                .filter(LemmaTranslation.lemma_id == lemma.id)
                .all()
            }
            self.assertIn("lt", translations)
            self.assertEqual(translations["lt"].translation, "pirkti")
            self.assertEqual(translations["lt"].disambiguation, "įsigyti")

            forms = {
                f.grammatical_form: f
                for f in db.query(DerivativeForm).filter(DerivativeForm.lemma_id == lemma.id).all()
            }
            self.assertEqual(forms["verb/lt_infinitive"].derivative_form_text, "pirkti")
            self.assertTrue(forms["verb/lt_infinitive"].is_base_form)
            self.assertEqual(forms["verb/lt_1p_past"].derivative_form_text, "pirkome")
            self.assertFalse(forms["verb/lt_1p_past"].is_base_form)

            facts = db.query(GrammarFact).filter(GrammarFact.lemma_id == lemma.id).all()
            self.assertEqual(len(facts), 1)
            self.assertEqual(facts[0].fact_type, "aspect")
            self.assertEqual(facts[0].fact_value, "imperfective")

            overrides = {
                o.language_code: o.difficulty_level
                for o in db.query(LemmaDifficultyOverride)
                .filter(LemmaDifficultyOverride.lemma_id == lemma.id)
                .all()
            }
            self.assertEqual(overrides.get("lt"), 2)

    def test_sqlite_import_preserves_sentence_meta(self) -> None:
        engine = create_engine(f"sqlite:///{self.imported_db}")
        with Session(engine) as db:
            sentence = db.query(Sentence).one()
            self.assertEqual(sentence.pattern_type, "guided")
            self.assertEqual(sentence.minimum_level, 2)
            self.assertEqual(sentence.source_filename, "roundtrip_fixture")
            self.assertEqual(sentence.tense, "past")
            translations = {
                t.language_code: t.translation_text
                for t in db.query(SentenceTranslation)
                .filter(SentenceTranslation.sentence_id == sentence.id)
                .all()
            }
            self.assertEqual(translations["en"], "We bought a printer.")
            self.assertEqual(translations["lt"], "Mes pirkome spausdintuvą.")

    # ---- Golden mode (JSONL backend in-memory SQLite) --------------------

    def test_golden_mode_preserves_word_fields(self) -> None:
        config = DataSourceConfig(backend_type=BackendType.JSONL, jsonl_data_dir=self.release_dir)
        session = create_backend_session(config)
        try:
            self._assert_word_fields(session)
            self._assert_lemma_link(session)
        finally:
            session.close()

    # ---- Shared assertions ----------------------------------------------

    def _assert_word_fields(self, db: Session) -> None:
        verb_word = db.query(SentenceWord).filter(SentenceWord.word_role == "verb").one()
        for column in SENTENCE_WORD_DATA_COLUMNS:
            actual = getattr(verb_word, column)
            self.assertEqual(
                actual,
                EXPECTED_WORD[column],
                f"column {column!r} round-tripped as {actual!r}",
            )

    def _assert_lemma_link(self, db: Session) -> None:
        verb_word = db.query(SentenceWord).filter(SentenceWord.word_role == "verb").one()
        self.assertIsNotNone(verb_word.lemma_id, "lemma link lost across round trip")
        lemma = db.query(Lemma).filter(Lemma.id == verb_word.lemma_id).one()
        self.assertEqual(lemma.guid, LEMMA_GUID)


@unittest.skipUnless(
    os.path.isdir(os.path.join("data", "release", "sentences")),
    "data/release not present",
)
class RealReleaseGoldenModeTest(unittest.TestCase):
    """Golden-mode regression check against the committed data/release."""

    def test_real_release_words_have_text(self) -> None:
        config = DataSourceConfig(
            backend_type=BackendType.JSONL, jsonl_data_dir=os.path.join("data", "release")
        )
        session = create_backend_session(config)
        try:
            words_with_text = (
                session.query(SentenceWord)
                .filter(SentenceWord.target_language_text.isnot(None))
                .limit(1)
                .all()
            )
            total_words = session.query(SentenceWord).count()
        finally:
            session.close()

        if total_words == 0:
            self.skipTest("data/release has no sentence words")
        self.assertTrue(
            words_with_text,
            "golden mode loaded sentence words but none had target_language_text "
            "(the field was dropped during the JSONL -> in-memory SQLite load)",
        )
