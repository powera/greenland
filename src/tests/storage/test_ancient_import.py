#!/usr/bin/python3

"""Importing ancient-language translations out of the release tree.

The la/sa/grc/ar-classical/non translations and their ``translation_status``
judgements live only in ``ancient.jsonl`` group files. Nothing had ever read
them back into a SQL backend, so every ``translation_status`` in the database
was NULL. These tests pin the matching rules the importer inherits from
``jsonl.storage._merge_grouped_translation_file``: match by GUID, never create a
lemma, and leave an existing translation alone unless asked to overwrite.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import storage.models  # noqa: F401 -- register every model before create_all
from storage.models.schema import Base, Lemma, LemmaTranslation
from storage.release.ancient_import import (
    find_ancient_files,
    import_ancient_translations,
    iter_ancient_records,
)

SHIP_RECORD: Dict[str, Any] = {
    "guid": "N40_009",
    "translations": {"la": "navis", "sa": "नौः", "grc": "ναῦς"},
    "translation_metadata": {
        "la": {"translation_status": "conventional"},
        "sa": {"translation_status": "conventional"},
        "grc": {"translation_status": "conventional"},
    },
}

BICYCLE_RECORD: Dict[str, Any] = {
    "guid": "N40_007",
    "translations": {"la": "birota"},
    "translation_metadata": {
        "la": {
            "translation_status": "late_construction",
            "translation_status_note": "Neo-Latin term for a bicycle.",
        }
    },
}


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _write_release_tree(root: Path, records: list[Dict[str, Any]]) -> None:
    """Write records into a release-shaped ``lemmas/nouns/vehicle`` tree."""
    directory = root / "lemmas" / "nouns" / "vehicle"
    directory.mkdir(parents=True, exist_ok=True)
    with open(directory / "ancient.jsonl", "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _seed_lemma(session: Session, guid: str, lemma_text: str) -> Lemma:
    lemma = Lemma(
        guid=guid,
        lemma_text=lemma_text,
        definition_text=f"a {lemma_text}",
        pos_type="noun",
        pos_subtype="vehicle",
    )
    session.add(lemma)
    session.flush()
    return lemma


class TestAncientImport(unittest.TestCase):
    def setUp(self) -> None:
        self.session = _make_session()
        self._tempdir = TemporaryDirectory()
        self.root = Path(self._tempdir.name)

    def tearDown(self) -> None:
        self.session.close()
        self._tempdir.cleanup()

    def test_imports_translations_and_statuses(self) -> None:
        _seed_lemma(self.session, "N40_009", "ship")
        _write_release_tree(self.root, [SHIP_RECORD])

        result = import_ancient_translations(self.session, self.root)

        self.assertEqual(result.lemmas_matched, 1)
        self.assertEqual(result.translations_written, 3)
        self.assertEqual(result.statuses_written, 3)

        latin = (
            self.session.query(LemmaTranslation)
            .filter(LemmaTranslation.language_code == "la")
            .one()
        )
        self.assertEqual(latin.translation, "navis")
        self.assertEqual(latin.translation_status, "conventional")

    def test_status_note_is_carried_across(self) -> None:
        _seed_lemma(self.session, "N40_007", "bicycle")
        _write_release_tree(self.root, [BICYCLE_RECORD])

        import_ancient_translations(self.session, self.root)

        latin = (
            self.session.query(LemmaTranslation)
            .filter(LemmaTranslation.language_code == "la")
            .one()
        )
        self.assertEqual(latin.translation_status, "late_construction")
        self.assertEqual(latin.translation_status_note, "Neo-Latin term for a bicycle.")

    def test_unknown_guid_is_reported_not_created(self) -> None:
        _write_release_tree(self.root, [SHIP_RECORD])

        result = import_ancient_translations(self.session, self.root)

        self.assertEqual(result.lemmas_matched, 0)
        self.assertEqual(result.missing_guids, ["N40_009"])
        self.assertEqual(self.session.query(Lemma).count(), 0)

    def test_existing_translation_is_preserved_by_default(self) -> None:
        """base.jsonl is the primary record; a group file must not redefine it."""
        lemma = _seed_lemma(self.session, "N40_009", "ship")
        self.session.add(
            LemmaTranslation(
                lemma_id=lemma.id,
                language_code="la",
                translation="preexisting",
            )
        )
        self.session.flush()
        _write_release_tree(self.root, [SHIP_RECORD])

        result = import_ancient_translations(self.session, self.root)

        self.assertEqual(result.translations_skipped_existing, 1)
        latin = (
            self.session.query(LemmaTranslation)
            .filter(LemmaTranslation.language_code == "la")
            .one()
        )
        self.assertEqual(latin.translation, "preexisting")

    def test_overwrite_replaces_existing_translation(self) -> None:
        lemma = _seed_lemma(self.session, "N40_009", "ship")
        self.session.add(
            LemmaTranslation(
                lemma_id=lemma.id,
                language_code="la",
                translation="preexisting",
            )
        )
        self.session.flush()
        _write_release_tree(self.root, [SHIP_RECORD])

        import_ancient_translations(self.session, self.root, overwrite=True)

        latin = (
            self.session.query(LemmaTranslation)
            .filter(LemmaTranslation.language_code == "la")
            .one()
        )
        self.assertEqual(latin.translation, "navis")

    def test_rerun_is_idempotent(self) -> None:
        _seed_lemma(self.session, "N40_009", "ship")
        _write_release_tree(self.root, [SHIP_RECORD])

        import_ancient_translations(self.session, self.root)
        second = import_ancient_translations(self.session, self.root)

        self.assertEqual(second.translations_written, 0)
        self.assertEqual(second.translations_skipped_existing, 3)
        self.assertEqual(self.session.query(LemmaTranslation).count(), 3)

    def test_language_outside_the_group_is_rejected(self) -> None:
        """A stray code in a release file must not create a translation row."""
        _seed_lemma(self.session, "N40_009", "ship")
        _write_release_tree(
            self.root,
            [{"guid": "N40_009", "translations": {"de": "Schiff"}}],
        )

        result = import_ancient_translations(self.session, self.root)

        self.assertEqual(result.translations_written, 0)
        self.assertEqual(result.unexpected_languages, ["de"])
        self.assertEqual(self.session.query(LemmaTranslation).count(), 0)

    def test_malformed_line_is_skipped_not_fatal(self) -> None:
        _seed_lemma(self.session, "N40_009", "ship")
        directory = self.root / "lemmas" / "nouns" / "vehicle"
        directory.mkdir(parents=True)
        with open(directory / "ancient.jsonl", "w", encoding="utf-8") as handle:
            handle.write("{not json\n")
            handle.write(json.dumps(SHIP_RECORD) + "\n")

        result = import_ancient_translations(self.session, self.root)

        self.assertEqual(result.records_read, 1)
        self.assertEqual(result.lemmas_matched, 1)


class TestFileDiscovery(unittest.TestCase):
    def test_finds_nested_ancient_files(self) -> None:
        with TemporaryDirectory() as name:
            root = Path(name)
            _write_release_tree(root, [SHIP_RECORD])
            (root / "lemmas" / "nouns" / "vehicle" / "base.jsonl").write_text("", encoding="utf-8")

            found = find_ancient_files(root)

            self.assertEqual([path.name for path in found], ["ancient.jsonl"])

    def test_blank_lines_are_skipped(self) -> None:
        with TemporaryDirectory() as name:
            path = Path(name) / "ancient.jsonl"
            path.write_text(json.dumps(SHIP_RECORD) + "\n\n\n", encoding="utf-8")

            records = list(iter_ancient_records(path))

            self.assertEqual(len(records), 1)


if __name__ == "__main__":
    unittest.main()
