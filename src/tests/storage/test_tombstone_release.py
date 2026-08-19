"""Round-trip for ``data/release/tombstones``, and the record it ships.

The tombstone file is the only surviving evidence that a GUID was spent once its
lemma row is gone, and ``storage.utils.guid`` refuses to reissue exactly the
GUIDs it names. So this covers the two ways it can go wrong: the record losing a
field on the way out, and the import failing to bring one back.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from storage.crud.guid_tombstone import create_tombstone, get_tombstone_by_guid
from storage.models.guid_tombstone import (
    TOMBSTONE_REASON_RELEASE_REMOVAL,
    TOMBSTONE_REASON_TYPE_AND_SUBTYPE_CHANGE,
    TOMBSTONE_REASON_TYPE_CHANGE,
    GuidTombstone,
)
from storage.release.tombstone import (
    export_tombstones_to_release,
    import_release_record,
    import_tombstones_from_release,
    read_release_records,
    read_release_records_by_guid,
    tombstone_to_release_record,
    write_release_records,
)
from storage.utils.guid import generate_guid
from storage.utils.session import create_database_session, ensure_tables_exist


def _seed(session: Any) -> None:
    create_tombstone(
        session=session,
        guid="A03_001",
        original_lemma_text="triangle",
        original_pos_type="adjective",
        original_pos_subtype="quality",
        replacement_guid="N08_001",
        lemma_id=42,
        reason=TOMBSTONE_REASON_TYPE_AND_SUBTYPE_CHANGE,
        notes="was miscategorised",
        changed_by="tests",
    )
    create_tombstone(
        session=session,
        guid="N08_002",
        original_lemma_text="wyvern",
        original_pos_type="noun",
        original_pos_subtype=None,
        replacement_guid=None,
        lemma_id=None,
        reason=TOMBSTONE_REASON_RELEASE_REMOVAL,
    )
    session.commit()


class TestTombstoneRelease(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.release_dir = self.tmp_path / "tombstones"
        self.db_path = str(self.tmp_path / "test.sqlite")

        self.session = create_database_session(self.db_path)
        ensure_tables_exist(self.session)
        _seed(self.session)

    def tearDown(self) -> None:
        self.session.close()
        self._tmp.cleanup()

    def test_export_writes_every_tombstone_sorted_by_guid(self) -> None:
        count = export_tombstones_to_release(self.session, self.release_dir)

        records = read_release_records(self.release_dir)
        self.assertEqual(2, count)
        self.assertEqual(["A03_001", "N08_002"], [record["guid"] for record in records])

    def test_export_creates_the_directory(self) -> None:
        self.assertFalse(self.release_dir.exists())

        export_tombstones_to_release(self.session, self.release_dir)

        self.assertTrue((self.release_dir / "guid_tombstones.jsonl").is_file())

    def test_the_record_omits_the_local_lemma_id(self) -> None:
        """lemma_id is a SQLite primary key and is not portable across databases."""
        tombstone = get_tombstone_by_guid(self.session, "A03_001")
        assert tombstone is not None
        self.assertEqual(42, tombstone.lemma_id, "the column is still populated locally")

        self.assertNotIn("lemma_id", tombstone_to_release_record(tombstone))

    def test_unset_optional_fields_are_omitted_rather_than_null(self) -> None:
        tombstone = get_tombstone_by_guid(self.session, "N08_002")
        assert tombstone is not None

        record = tombstone_to_release_record(tombstone)

        for field in ("original_pos_subtype", "replacement_guid", "notes", "changed_by"):
            self.assertNotIn(field, record)

    def test_export_is_byte_stable_across_a_round_trip(self) -> None:
        """Re-exporting an unchanged database must not churn the file."""
        export_tombstones_to_release(self.session, self.release_dir)
        first = (self.release_dir / "guid_tombstones.jsonl").read_bytes()

        export_tombstones_to_release(self.session, self.release_dir)

        self.assertEqual(first, (self.release_dir / "guid_tombstones.jsonl").read_bytes())

    def test_import_restores_every_field(self) -> None:
        export_tombstones_to_release(self.session, self.release_dir)

        other_path = str(self.tmp_path / "other.sqlite")
        other = create_database_session(other_path)
        ensure_tables_exist(other)
        try:
            imported = import_tombstones_from_release(other, self.release_dir)

            self.assertEqual(2, imported)
            restored = get_tombstone_by_guid(other, "A03_001")
            assert restored is not None
            self.assertEqual("triangle", restored.original_lemma_text)
            self.assertEqual("adjective", restored.original_pos_type)
            self.assertEqual("quality", restored.original_pos_subtype)
            self.assertEqual("N08_001", restored.replacement_guid)
            self.assertEqual(TOMBSTONE_REASON_TYPE_AND_SUBTYPE_CHANGE, restored.reason)
            self.assertEqual("was miscategorised", restored.notes)
            self.assertEqual("tests", restored.changed_by)
        finally:
            other.close()

    def test_importing_twice_refreshes_rather_than_duplicating(self) -> None:
        export_tombstones_to_release(self.session, self.release_dir)

        other_path = str(self.tmp_path / "other.sqlite")
        other = create_database_session(other_path)
        ensure_tables_exist(other)
        try:
            import_tombstones_from_release(other, self.release_dir)
            import_tombstones_from_release(other, self.release_dir)

            self.assertEqual(2, other.query(GuidTombstone).count())
        finally:
            other.close()

    def test_an_unfamiliar_reason_is_kept_rather_than_dropping_the_row(self) -> None:
        """A stale label must not cost us the retirement it records.

        Minting a tombstone with an unknown reason is an error, but refusing an
        imported one would silently un-retire the GUID.
        """
        other_path = str(self.tmp_path / "other.sqlite")
        other = create_database_session(other_path)
        ensure_tables_exist(other)
        try:
            import_release_record(
                other,
                {
                    "guid": "N08_003",
                    "original_lemma_text": "basilisk",
                    "original_pos_type": "noun",
                    "reason": "a_reason_from_the_future",
                },
            )
            other.commit()

            restored = get_tombstone_by_guid(other, "N08_003")
            assert restored is not None
            self.assertEqual(TOMBSTONE_REASON_TYPE_CHANGE, restored.reason)
        finally:
            other.close()

    def test_an_imported_tombstone_takes_its_guid_out_of_circulation(self) -> None:
        """The point of importing them: allocation must see the retirement."""
        write_release_records(
            self.release_dir,
            [
                {
                    "guid": "N02_009",
                    "original_lemma_text": "aurochs",
                    "original_pos_type": "noun",
                    "original_pos_subtype": "animal",
                    "reason": TOMBSTONE_REASON_RELEASE_REMOVAL,
                }
            ],
        )

        other_path = str(self.tmp_path / "other.sqlite")
        other = create_database_session(other_path)
        ensure_tables_exist(other)
        try:
            import_tombstones_from_release(other, self.release_dir)

            self.assertNotEqual("N02_009", generate_guid(other, "noun", "animal"))
        finally:
            other.close()

    def test_records_are_read_back_keyed_by_guid(self) -> None:
        export_tombstones_to_release(self.session, self.release_dir)

        by_guid = read_release_records_by_guid(self.release_dir)

        self.assertEqual({"A03_001", "N08_002"}, set(by_guid))
        self.assertEqual("N08_001", by_guid["A03_001"]["replacement_guid"])

    def test_reading_a_missing_directory_is_empty_not_an_error(self) -> None:
        self.assertEqual([], read_release_records(self.tmp_path / "nope"))
