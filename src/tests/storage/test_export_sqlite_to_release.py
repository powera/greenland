#!/usr/bin/python3

"""The CLI release export writes the same base record the UI sync writes.

``export_sqlite_to_release`` used to build the lemma base record inline, and its
version disagreed with the sync blueprint's: no ``qid``, no
``translation_disambiguations``, and ``concept_label`` without the
disambiguation. Running it after any UI work therefore stripped those from the
tree -- and since the disambiguation is recovered by parsing ``concept_label``,
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

from storage.crud.concept import link_lemma_to_concept
from storage.migrate import export_sqlite_to_release
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
        # The exporter also writes GUID tombstones to a sibling directory and
        # expects it to exist, as it does in a real data/release tree.
        (self.tmp_path / "tombstones").mkdir()

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
        self.assertEqual({"lt": "gyvūnas"}, record["translation_disambiguations"])

    def test_export_still_carries_what_only_it_had(self) -> None:
        """difficulty_overrides was CLI-only; unifying must not have lost it."""
        self.assertEqual({"lt": 7}, self._exported_record()["difficulty_overrides"])


if __name__ == "__main__":
    unittest.main()
