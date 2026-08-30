#!/usr/bin/python3

"""The CLI release export writes the same base record the UI sync writes.

``export_sqlite_to_release`` used to build the lemma base record inline, and its
version disagreed with the sync blueprint's: no ``qid``, no
the ``disambiguation`` map, and ``concept_label`` without the
disambiguation. Running it after any UI work therefore stripped those from the
tree -- and since the disambiguation was then recovered by parsing ``concept_label``,
re-importing then nulled it on every lemma.

Both now call ``storage.release.lemma.lemma_to_release_record``. This test runs
the real CLI export against a temporary database and compares its output to that
builder, so the two cannot drift apart again.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

from storage.backend.jsonl.storage import JSONLStorage
from storage.crud.concept import link_lemma_to_concept
from storage.crud.guid_tombstone import create_tombstone
from storage.migrate import export_sqlite_to_release
from storage.models.guid_tombstone import (
    TOMBSTONE_REASON_RELEASE_REMOVAL,
    TOMBSTONE_REASON_TYPE_AND_SUBTYPE_CHANGE,
)
from storage.models.schema import (
    Lemma,
    LemmaDifficultyOverride,
    LemmaTranslation,
)
from storage.release.lemma import lemma_to_release_record
from storage.utils.session import create_database_session, ensure_tables_exist


def _seed(session: Any) -> None:
    lemma = Lemma(
        guid="N08_001",
        lemma_text="bat",
        disambiguation="animal",
        definition_text="a flying mammal",
        pos_type="noun",
        pos_subtype="animal",
        difficulty_level=4,
        notes="not the cricket kind",
        emoji=json.dumps([{"type": "unicode", "value": "🦇"}]),
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
        )
    )
    session.add(LemmaDifficultyOverride(lemma_id=lemma.id, language_code="lt", difficulty_level=7))
    session.flush()
    link_lemma_to_concept(session, lemma.id, "Q28425", verified=True)
    session.commit()


class TestExportSqliteToRelease(unittest.TestCase):
    """The CLI export path, end to end."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.db_path = str(self.tmp_path / "test.sqlite")
        self.release_dir = self.tmp_path / "lemmas"
        # Note there is deliberately no mkdir for the sibling tombstones/
        # directory here: the exporter creates what it writes into, so exporting
        # to a fresh --release-dir works. It used to raise FileNotFoundError at
        # the very end of the run, after every lemma file had been written.

        session = create_database_session(self.db_path)
        ensure_tables_exist(session)
        _seed(session)
        session.close()

        export_sqlite_to_release(self.db_path, str(self.release_dir))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _exported_record(self) -> Dict[str, Any]:
        path = self.release_dir / "noun" / "animal" / "base.jsonl"
        if not path.exists():
            # The exporter picks the directory from pos_type/pos_subtype; find it
            # rather than hardcoding the pluralization rule under test elsewhere.
            candidates = list(self.release_dir.rglob("base.jsonl"))
            self.assertEqual(1, len(candidates), f"expected one base.jsonl, got {candidates}")
            path = candidates[0]
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(1, len(lines))
        return dict(json.loads(lines[0]))

    def test_export_matches_the_shared_builder(self) -> None:
        session = create_database_session(self.db_path)
        try:
            lemma = session.query(Lemma).filter(Lemma.guid == "N08_001").one()
            expected = lemma_to_release_record(lemma, qid="Q28425")
        finally:
            session.close()

        self.assertEqual(expected, self._exported_record())

    def test_export_keeps_what_it_used_to_drop(self) -> None:
        """The three fields the CLI version omitted, named explicitly."""
        record = self._exported_record()
        self.assertEqual("bat (animal)", record["concept_label"])
        self.assertEqual("Q28425", record["qid"])
        self.assertEqual({"lt": "gyvūnas", "en": "animal"}, record["disambiguation"])

    def test_export_still_carries_what_only_it_had(self) -> None:
        """difficulty_overrides was CLI-only; unifying must not have lost it."""
        self.assertEqual({"lt": 7}, self._exported_record()["difficulty_overrides"])


if __name__ == "__main__":
    unittest.main()


def _seed_tombstones(session: Any) -> None:
    """One tombstone of each interesting shape: replaced, and plainly deleted."""
    lemma = session.query(Lemma).one()
    create_tombstone(
        session=session,
        guid="A03_001",
        original_lemma_text="bat",
        original_pos_type="adjective",
        original_pos_subtype="quality",
        replacement_guid="N08_001",
        lemma_id=lemma.id,
        reason=TOMBSTONE_REASON_TYPE_AND_SUBTYPE_CHANGE,
        notes="was miscategorised",
        changed_by="tests",
    )
    create_tombstone(
        session=session,
        guid="N08_002",
        original_lemma_text="wyvern",
        original_pos_type="noun",
        original_pos_subtype="animal",
        replacement_guid=None,
        lemma_id=None,
        reason=TOMBSTONE_REASON_RELEASE_REMOVAL,
    )
    session.commit()


class TestTombstoneExport(unittest.TestCase):
    """The tombstone file the lemma export writes as a side effect.

    Nothing asserted its contents before; the only existing reference created
    the directory so the exporter would not crash.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.db_path = str(self.tmp_path / "test.sqlite")
        self.release_dir = self.tmp_path / "lemmas"

        session = create_database_session(self.db_path)
        ensure_tables_exist(session)
        _seed(session)
        _seed_tombstones(session)
        session.close()

        export_sqlite_to_release(self.db_path, str(self.release_dir))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _records(self) -> list[Dict[str, Any]]:
        path = self.tmp_path / "tombstones" / "guid_tombstones.jsonl"
        self.assertTrue(path.exists(), "the exporter must create the tombstones directory")
        return [
            dict(json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_every_tombstone_is_written_sorted_by_guid(self) -> None:
        records = self._records()

        self.assertEqual(["A03_001", "N08_002"], [record["guid"] for record in records])

    def test_the_recorded_fields_survive_the_export(self) -> None:
        replaced = self._records()[0]

        self.assertEqual("bat", replaced["original_lemma_text"])
        self.assertEqual("adjective", replaced["original_pos_type"])
        self.assertEqual("quality", replaced["original_pos_subtype"])
        self.assertEqual("N08_001", replaced["replacement_guid"])
        self.assertEqual("type_and_subtype_change", replaced["reason"])
        self.assertEqual("was miscategorised", replaced["notes"])
        self.assertEqual("tests", replaced["changed_by"])
        self.assertIn("tombstoned_at", replaced)

    def test_empty_optional_fields_are_omitted_rather_than_written_as_null(self) -> None:
        deleted = self._records()[1]

        self.assertNotIn("replacement_guid", deleted)
        self.assertNotIn("notes", deleted)
        self.assertNotIn("changed_by", deleted)

    def test_the_local_lemma_id_is_never_exported(self) -> None:
        """lemma_id is a SQLite primary key, not a portable identifier.

        It differs after every bootstrap, and on the synonym-merge path it names
        a row that is deleted moments later, so writing it into release data
        produces churn that means nothing to a reader.
        """
        for record in self._records():
            self.assertNotIn("lemma_id", record)

    def test_the_export_reloads_into_a_database(self) -> None:
        """Round-trip: what the exporter wrote is what the JSONL backend reads."""
        storage = JSONLStorage(str(self.tmp_path))
        storage.ensure_initialized()  # the backend loads lazily

        self.assertEqual(
            {"A03_001", "N08_002"}, {tombstone.guid for tombstone in storage.tombstones}
        )
        replaced = next(t for t in storage.tombstones if t.guid == "A03_001")
        self.assertEqual("N08_001", replaced.replacement_guid)
        self.assertEqual("type_and_subtype_change", replaced.reason)
