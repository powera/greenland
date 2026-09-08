#!/usr/bin/python3

"""The ``data/release`` <-> SQLite round trip, against the real release tree.

See README.md for why byte-equality with ``data/release`` is the wrong
assertion and idempotence is the right one.
"""

from pathlib import Path
from typing import Any, Dict

from regtest.release.conftest import jsonl_digest, read_release_sentences


class TestIdempotence:
    """Exporting a database built from an export must reproduce that export."""

    def test_every_file_is_byte_identical(self, first_pass: Path, second_pass: Path) -> None:
        """The second pass changes nothing -- the pipeline is a fixed point.

        This is the assertion that actually protects data/release: any change
        that makes the exporter or the importer lose, add, or reorder a field
        shows up here as a differing file.
        """
        first = jsonl_digest(first_pass)
        second = jsonl_digest(second_pass)

        assert set(first) == set(second), "the two passes wrote different sets of files"
        differing = sorted(name for name in first if first[name] != second[name])
        assert not differing, f"{len(differing)} file(s) changed on re-export: {differing[:10]}"

    def test_the_tree_is_not_empty(self, first_pass: Path) -> None:
        """Guard against a vacuous pass: an empty export would satisfy every
        equality above."""
        digest = jsonl_digest(first_pass)
        assert len(digest) > 300, f"expected a full release tree, got {len(digest)} files"


class TestSentenceAudioSurvives:
    """Sentence audio is carried inline on each record and must round-trip.

    It regressed silently for a long time: the export wrote the ``audio`` key
    but nothing read it back, so a database rebuilt from data/release held no
    sentence audio and the next export dropped the key entirely.
    """

    def test_no_sentence_loses_its_audio(self, checked_in_release: Path, first_pass: Path) -> None:
        committed = read_release_sentences(checked_in_release)
        exported = read_release_sentences(first_pass)

        with_audio = {guid for guid, record in committed.items() if record.get("audio")}
        assert with_audio, "fixture problem: no committed sentence carries audio"

        lost = sorted(guid for guid in with_audio if not exported.get(guid, {}).get("audio"))
        assert not lost, f"{len(lost)} sentence(s) lost their audio: {lost[:10]}"

    def test_audio_entries_are_unchanged(self, checked_in_release: Path, first_pass: Path) -> None:
        committed = read_release_sentences(checked_in_release)
        exported = read_release_sentences(first_pass)

        changed = [
            guid
            for guid, record in committed.items()
            if record.get("audio") and exported.get(guid, {}).get("audio") != record["audio"]
        ]
        assert not changed, f"{len(changed)} sentence(s) changed audio: {changed[:10]}"


class TestUnstorableHintsAreDropped:
    """A hint the schema cannot hold must not be exported.

    ck_word_hint_has_reference requires a lemma or a name, so a hint with
    neither can only be skipped on import. Exporting one means the file
    disagrees with any database built from it -- which is what kept the round
    trip from converging.
    """

    def test_no_exported_hint_lacks_a_reference(self, first_pass: Path) -> None:
        """No exported hint is missing both references.

        Note this cannot fail by removing the export-side guard alone: a
        release-built database can never hold such a hint (the importer skips
        it, ck_word_hint_has_reference forbids it), so there is nothing for the
        export to write. The guard exists for databases populated another way
        -- the Barsukas sync -- and is unit-tested in
        src/tests/storage/test_sentence_release_record.py. What this pins is
        the committed tree's own 704 unlinked hints staying out of the export.
        """
        offenders = [
            (guid, hint)
            for guid, record in read_release_sentences(first_pass).items()
            for hint in record.get("word_hints", [])
            if hint.get("lemma_guid") is None and "name_guid" not in hint
        ]
        assert not offenders, f"{len(offenders)} unstorable hint(s) exported: {offenders[:5]}"

    def test_export_writes_exactly_what_the_database_holds(
        self, first_pass_database: Path, first_pass: Path
    ) -> None:
        """Every exported hint corresponds to a stored row, and vice versa.

        Comparing the file against data/release cannot catch an over-eager
        export: an unstorable hint is dropped on the *next* import, so both
        passes agree and idempotence still holds. Comparing against the
        database is what actually pins it -- the schema is the authority on
        what a hint may be.
        """
        import sqlite3

        connection = sqlite3.connect(str(first_pass_database))
        try:
            stored: Dict[str, int] = {
                guid: count
                for guid, count in connection.execute(
                    "SELECT s.guid, COUNT(h.id) FROM sentences s "
                    "LEFT JOIN sentence_word_hints h ON h.sentence_id = s.id "
                    "WHERE s.guid IS NOT NULL GROUP BY s.guid"
                )
            }
        finally:
            connection.close()

        mismatched = {
            guid: (len(record.get("word_hints", [])), stored.get(guid, 0))
            for guid, record in read_release_sentences(first_pass).items()
            if len(record.get("word_hints", [])) != stored.get(guid, 0)
        }
        assert not mismatched, (
            f"{len(mismatched)} sentence(s) exported a hint count the database does not "
            f"hold (file, db): {dict(list(mismatched.items())[:5])}"
        )

    def test_linked_hints_are_preserved(self, checked_in_release: Path, first_pass: Path) -> None:
        """Dropping unlinked hints must not disturb the linked ones.

        S_00780 is the known exception: its "head" hint names N27_003, a
        tombstoned GUID, so no import can resolve it.
        """
        committed = read_release_sentences(checked_in_release)
        exported = read_release_sentences(first_pass)
        tombstoned_reference = {"S_00780"}

        for guid, record in committed.items():
            if guid in tombstoned_reference:
                continue
            expected = [
                hint
                for hint in record.get("word_hints", [])
                if hint.get("lemma_guid") is not None or "name_guid" in hint
            ]
            assert exported[guid].get("word_hints", []) == expected, f"{guid} lost a linked hint"


class TestUnshippedFieldsStayOut:
    """Fields for unfinished features must not appear as dead nulls.

    Proper names and UD dependency parsing have no rows in any database and no
    keys anywhere in data/release. Writing them as explicit nulls would add
    three dead keys to every word of every sentence.
    """

    def test_no_null_placeholder_keys(self, first_pass: Path) -> None:
        unshipped = ("name_guid", "ud_relation", "ud_head_position")
        offenders: Dict[str, Any] = {}
        for guid, record in read_release_sentences(first_pass).items():
            for array_key in ("words", "word_hints"):
                for entry in record.get(array_key, []):
                    for field in unshipped:
                        if field in entry and entry[field] is None:
                            offenders.setdefault(f"{array_key}.{field}", guid)
        assert not offenders, f"null placeholder keys written: {offenders}"


class TestImportPersists:
    """Importing one element type on its own must reach the disk.

    Every importer commits its own work. That was not always true, and the
    inconsistency hid itself: a commit flushes the whole session, so a module
    that left work pending was still saved whenever a later module in the same
    run committed. Only importing such an element type *alone* lost the rows --
    which is exactly what scripts/bootstrap.sh does.
    """

    def test_a_lone_import_reaches_the_disk(self, tmp_path: Path, checked_in_release: Path) -> None:
        import sqlite3
        import subprocess
        import sys

        from regtest.release.conftest import REPOSITORY_ROOT, SOURCE_ROOT, build_database

        database = tmp_path / "import.sqlite"
        build_database(database, checked_in_release)

        connection = sqlite3.connect(str(database))
        try:
            connection.execute("DELETE FROM idiom_equivalents")
            connection.execute("DELETE FROM idioms")
            connection.commit()
        finally:
            connection.close()

        subprocess.run(
            [
                sys.executable,
                "-m",
                "storage.release.cli",
                # Alone, deliberately: pairing this with a second element type
                # would mask a missing commit rather than expose it.
                "import",
                "idioms",
                "--sqlite-path",
                str(database),
                "--release-root",
                str(checked_in_release),
            ],
            cwd=REPOSITORY_ROOT,
            env={"PYTHONPATH": str(SOURCE_ROOT), "GREENLAND_TEST_MODE": "1", "PATH": ""},
            check=True,
            capture_output=True,
        )

        connection = sqlite3.connect(str(database))
        try:
            imported = connection.execute("SELECT COUNT(*) FROM idioms").fetchone()[0]
        finally:
            connection.close()

        assert imported > 0, "idiom import did not reach the disk"
