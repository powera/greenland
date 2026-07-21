"""Round-trip tests for variant forms (alternate spellings) across storage layers.

A variant is the same lexeme spelled differently -- "grey" for "gray", "donut"
for "doughnut" -- and unlike a synonym it carries its own full paradigm
("grey"/"greyer"/"greyest").  That paradigm has to survive the same three
transformations the rest of the release data does:

  * Export:  SQLite -> JSONL release dir   (``storage.migrate``)
  * Import:  JSONL release dir -> SQLite   (``storage.migrate.import_jsonl_to_sqlite``)
  * Golden:  JSONL release dir -> ephemeral in-memory SQLite (``storage.backend.jsonl``)

Two properties matter beyond field completeness, and both are asserted here:

  * Variants must NOT leak into ``derivative_forms``.  An unfiltered read of a
    lemma's forms must return "gray"/"grayer"/"grayest" and never "grey" --
    that separation is the whole reason variants live in their own table.
  * Variants must NOT be routed into the synonyms bucket.  The release loader
    sorts anything in ``NON_INFLECTION_GRAMMATICAL_FORMS`` out of the "forms"
    array and into synonyms; variants arrive under their own "variants" key
    specifically so they bypass that path.  "grey" is not a synonym of "gray".
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from typing import Any, Dict, List

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Import the full model registry so every table (FK targets included) is created.
import storage.models  # noqa: F401
from storage.backend.config import BackendType, DataSourceConfig
from storage.backend.factory import create_session as create_backend_session
from storage.migrate import export_sqlite_to_jsonl, import_jsonl_to_sqlite
from storage.models.schema import Base, DerivativeForm, Lemma, LemmaTranslation
from storage.models.variant_form import VARIANT_KIND_SPELLING, VariantForm

LEMMA_GUID = "A02_008"
LEMMA_TEXT = "gray"
VARIANT_KEY = "grey"

# The lemma's own paradigm (US spelling) and the variant's parallel paradigm.
# Keyed by grammatical form so a dropped or misfiled row is easy to spot.
LEMMA_FORMS: Dict[str, str] = {
    "adjective/en_positive": "gray",
    "adjective/en_comparative": "grayer",
    "adjective/en_superlative": "grayest",
}
VARIANT_FORMS: Dict[str, str] = {
    "adjective/en_positive": "grey",
    "adjective/en_comparative": "greyer",
    "adjective/en_superlative": "greyest",
}


def _build_source_db(sqlite_path: str) -> None:
    """Create a SQLite database with one lemma carrying a spelling variant."""
    engine = create_engine(f"sqlite:///{sqlite_path}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        lemma = Lemma(
            lemma_text=LEMMA_TEXT,
            definition_text="Of a color between black and white.",
            pos_type="adjective",
            pos_subtype="color",
            guid=LEMMA_GUID,
            difficulty_level=3,
        )
        db.add(lemma)
        db.flush()

        db.add(
            LemmaTranslation(
                lemma_id=lemma.id,
                language_code="en",
                translation=LEMMA_TEXT,
            )
        )

        for grammatical_form, text in LEMMA_FORMS.items():
            db.add(
                DerivativeForm(
                    lemma_id=lemma.id,
                    language_code="en",
                    grammatical_form=grammatical_form,
                    derivative_form_text=text,
                    is_base_form=(grammatical_form == "adjective/en_positive"),
                )
            )

        for grammatical_form, text in VARIANT_FORMS.items():
            db.add(
                VariantForm(
                    lemma_id=lemma.id,
                    language_code="en",
                    variant_kind=VARIANT_KIND_SPELLING,
                    variant_key=VARIANT_KEY,
                    grammatical_form=grammatical_form,
                    variant_form_text=text,
                    # Base form of the *variant*; the lemma keeps its own base
                    # form in derivative_forms, so these do not compete.
                    is_base_form=(grammatical_form == "adjective/en_positive"),
                )
            )

        db.commit()


def _read_release_en_record(release_dir: str) -> Dict[str, Any]:
    """Return the single exported en.jsonl record for the fixture lemma."""
    en_file = os.path.join(release_dir, "lemmas", "adjectives", "color", "en.jsonl")
    with open(en_file, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record: Dict[str, Any] = json.loads(line)
            if record.get("guid") == LEMMA_GUID:
                return record
    raise AssertionError(f"no en.jsonl record for {LEMMA_GUID} in {release_dir}")


class VariantFormRoundTripTest(unittest.TestCase):
    """Export + both import paths against one fixture database."""

    tmpdir: str
    source_db: str
    release_dir: str
    imported_db: str

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmpdir = tempfile.mkdtemp(prefix="variant_roundtrip_")
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

    def test_export_writes_variants_key(self) -> None:
        """en.jsonl carries the variant under its own top-level "variants" key."""
        record = _read_release_en_record(self.release_dir)
        self.assertIn("variants", record, "export dropped the variants key")
        variants: List[Dict[str, Any]] = record["variants"]
        self.assertEqual(len(variants), 1)
        self.assertEqual(variants[0]["kind"], VARIANT_KIND_SPELLING)
        self.assertEqual(variants[0]["key"], VARIANT_KEY)

    def test_export_preserves_full_variant_paradigm(self) -> None:
        """Every form of the variant survives export, not just its base form."""
        record = _read_release_en_record(self.release_dir)
        exported = {
            form["grammatical_form"]: form["text"] for form in record["variants"][0]["forms"]
        }
        self.assertEqual(exported, VARIANT_FORMS)

    def test_export_marks_variant_base_form(self) -> None:
        """The variant's own base form is flagged within its paradigm."""
        record = _read_release_en_record(self.release_dir)
        base_forms = [
            form["grammatical_form"]
            for form in record["variants"][0]["forms"]
            if form.get("is_base_form")
        ]
        self.assertEqual(base_forms, ["adjective/en_positive"])

    def test_export_keeps_variants_out_of_forms_and_synonyms(self) -> None:
        """ "grey" is neither an inflection of "gray" nor a synonym of it."""
        record = _read_release_en_record(self.release_dir)
        inflection_texts = set(record.get("derivative_forms", {}).keys())
        for text in VARIANT_FORMS.values():
            self.assertNotIn(text, inflection_texts)
        for synonym in record.get("synonyms", []):
            self.assertNotIn(synonym.get("text"), set(VARIANT_FORMS.values()))

    # ---- SQLite import ---------------------------------------------------

    def test_sqlite_import_restores_variant_paradigm(self) -> None:
        """Importing the release rebuilds every variant row with its metadata."""
        engine = create_engine(f"sqlite:///{self.imported_db}")
        with Session(engine) as db:
            rows = (
                db.query(VariantForm)
                .join(Lemma, VariantForm.lemma_id == Lemma.id)
                .filter(Lemma.guid == LEMMA_GUID)
                .all()
            )
            restored = {row.grammatical_form: row.variant_form_text for row in rows}
            self.assertEqual(restored, VARIANT_FORMS)
            for row in rows:
                self.assertEqual(row.variant_kind, VARIANT_KIND_SPELLING)
                self.assertEqual(row.variant_key, VARIANT_KEY)
                self.assertEqual(row.language_code, "en")

    def test_sqlite_import_keeps_variants_out_of_derivative_forms(self) -> None:
        """An unfiltered read of the lemma's forms must not return "grey"."""
        engine = create_engine(f"sqlite:///{self.imported_db}")
        with Session(engine) as db:
            texts = {
                row.derivative_form_text
                for row in db.query(DerivativeForm)
                .join(Lemma, DerivativeForm.lemma_id == Lemma.id)
                .filter(Lemma.guid == LEMMA_GUID)
                .all()
            }
            self.assertEqual(texts, set(LEMMA_FORMS.values()))
            for variant_text in VARIANT_FORMS.values():
                self.assertNotIn(variant_text, texts)

    def test_sqlite_import_preserves_single_lemma(self) -> None:
        """A variant is the same lexeme: it must not become a second lemma."""
        engine = create_engine(f"sqlite:///{self.imported_db}")
        with Session(engine) as db:
            lemma_texts = [row.lemma_text for row in db.query(Lemma).all()]
            self.assertEqual(lemma_texts, [LEMMA_TEXT])

    # ---- Golden (JSONL-backed read-only) mode ----------------------------

    def test_golden_mode_exposes_variant_forms(self) -> None:
        """The JSONL backend's ephemeral SQLite also carries the variants."""
        config = DataSourceConfig(
            backend_type=BackendType.JSONL,
            jsonl_data_dir=self.release_dir,
        )
        with create_backend_session(config) as session:
            rows = (
                session.query(VariantForm)
                .join(Lemma, VariantForm.lemma_id == Lemma.id)
                .filter(Lemma.guid == LEMMA_GUID)
                .all()
            )
            restored = {row.grammatical_form: row.variant_form_text for row in rows}
            self.assertEqual(restored, VARIANT_FORMS)


if __name__ == "__main__":
    unittest.main()
