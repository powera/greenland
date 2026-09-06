#!/usr/bin/python3

"""The sentence release export is a rebuild: a category it no longer fills loses its file.

``export_sqlite_to_sentence_release`` writes one ``base.jsonl`` per
(collection, pos_type, pos_subtype), but it only ever wrote the categories that
had records -- a file for a category that emptied was left on disk. That is
worse here than on the lemma side, because a sentence's directory is derived
rather than stored: it comes from the sentence's collection and from
``_resolve_primary_lemma_category``, so re-categorizing a sentence (or losing
the word hints that resolve its category) moves the record to a new file and
strands the old one. The next import reads both, and the stale copy wins for
every field it still carries.

These tests run the real export twice against one temporary database, changing
the categorization in between, and assert the first run's file is gone.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Set

from storage.migrate import export_sqlite_to_sentence_release
from storage.models.schema import (
    Lemma,
    Sentence,
    SentenceTranslation,
    SentenceWordHint,
)
from storage.utils.session import create_database_session, ensure_tables_exist


def _seed(session: Any) -> None:
    """One sentence whose primary lemma is a noun in nouns/animal."""
    lemma = Lemma(
        guid="N08_001",
        lemma_text="bat",
        definition_text="a flying mammal",
        pos_type="noun",
        pos_subtype="animal",
    )
    session.add(lemma)
    session.flush()

    sentence = Sentence(guid="S_00001", sentence_collection="general")
    session.add(sentence)
    session.flush()

    session.add(
        SentenceTranslation(
            sentence_id=sentence.id,
            language_code="en",
            translation_text="The bat sleeps.",
        )
    )
    session.add(
        SentenceWordHint(
            sentence_id=sentence.id,
            lemma_id=lemma.id,
            position=0,
            slot_name="noun",
            english_text="bat",
        )
    )


class SentenceReleaseExportRebuildsTheTree(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.db_path = str(root / "linguistics.sqlite")
        self.release_dir = root / "sentences"

        session = create_database_session(self.db_path)
        ensure_tables_exist(session)
        _seed(session)
        session.commit()
        session.close()

        export_sqlite_to_sentence_release(self.db_path, str(self.release_dir))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _base_files(self) -> Set[str]:
        """Every base.jsonl on disk, as a path relative to the release dir."""
        return {
            str(path.relative_to(self.release_dir)) for path in self.release_dir.rglob("base.jsonl")
        }

    def _records(self) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        for path in sorted(self.release_dir.rglob("base.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    records.append(dict(json.loads(line)))
        return records

    def test_the_first_export_files_the_sentence_under_its_primary_lemma(self) -> None:
        self.assertEqual({"general/nouns/animal/base.jsonl"}, self._base_files())

    def test_recategorizing_a_sentence_does_not_strand_its_old_file(self) -> None:
        """The bug: the sentence moves, and the old category keeps a stale copy."""
        session = create_database_session(self.db_path)
        try:
            lemma = session.query(Lemma).filter(Lemma.guid == "N08_001").one()
            lemma.pos_subtype = "mammal"
            session.commit()
        finally:
            session.close()

        export_sqlite_to_sentence_release(self.db_path, str(self.release_dir))

        self.assertEqual({"general/nouns/mammal/base.jsonl"}, self._base_files())
        # And the sentence is present exactly once, not once per past category.
        self.assertEqual(["S_00001"], [record["guid"] for record in self._records()])

    def test_a_changed_collection_leaves_no_empty_directory_behind(self) -> None:
        session = create_database_session(self.db_path)
        try:
            sentence = session.query(Sentence).filter(Sentence.guid == "S_00001").one()
            sentence.sentence_collection = "travel"
            session.commit()
        finally:
            session.close()

        export_sqlite_to_sentence_release(self.db_path, str(self.release_dir))

        self.assertEqual({"travel/nouns/animal/base.jsonl"}, self._base_files())
        self.assertFalse((self.release_dir / "general").exists())

    def test_a_sentence_that_leaves_the_release_takes_its_file_with_it(self) -> None:
        """Rejecting the last sentence in a category empties the tree, not just the file."""
        session = create_database_session(self.db_path)
        try:
            sentence = session.query(Sentence).filter(Sentence.guid == "S_00001").one()
            sentence.rejected = True
            session.commit()
        finally:
            session.close()

        export_sqlite_to_sentence_release(self.db_path, str(self.release_dir))

        self.assertEqual(set(), self._base_files())

    def test_the_exported_record_carries_the_collection(self) -> None:
        """The import reads `collection` back; an export that omits it flattens the tree."""
        (record,) = self._records()
        self.assertEqual("general", record["collection"])


if __name__ == "__main__":
    unittest.main()
