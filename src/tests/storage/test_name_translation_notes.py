#!/usr/bin/python3

"""A name rendering's ``notes`` must survive the release round trip.

``translation_metadata_record`` has always emitted ``notes``, but
``set_name_translation`` had no ``notes`` parameter, so neither the apply nor
the import path could put it back. The whole-record engine compares
``to_record(row) == release_record``, so such a name showed a difference that
picking "use release" could never clear -- the import dropped the field, the
re-serialization omitted it, and the row came straight back.
"""

from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import storage.models  # noqa: F401 -- register every model before create_all
from storage.crud.name_entity import create_name, set_name_translation
from storage.models.schema import Base
from storage.release.name import (
    apply_release_record,
    import_release_record,
    name_to_release_record,
)

_RECORD_WITH_NOTES = {
    "guid": "E01_001",
    "kind": "given_name",
    "name_text": "George",
    "translations": {"lt": "Džordžas"},
    "translation_metadata": {
        "lt": {
            "ipa_pronunciation": "dʒɔrdʒas",
            "notes": "declines like a masculine a-stem",
        }
    },
}


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class TestNameTranslationNotes(unittest.TestCase):
    def setUp(self) -> None:
        self.session = _make_session()

    def tearDown(self) -> None:
        self.session.close()

    def test_crud_stores_notes(self) -> None:
        name = create_name(self.session, name_text="George", kind="given_name")
        row = set_name_translation(
            self.session,
            name,
            language_code="lt",
            translation="Džordžas",
            notes="declines like a masculine a-stem",
        )
        self.assertEqual("declines like a masculine a-stem", row.notes)

    def test_import_then_export_reproduces_the_record(self) -> None:
        name = import_release_record(self.session, _RECORD_WITH_NOTES)
        self.session.commit()
        self.assertIsNotNone(name)
        assert name is not None  # for type checkers
        self.assertEqual(_RECORD_WITH_NOTES, name_to_release_record(name))

    def test_applying_a_record_clears_the_difference(self) -> None:
        """The bug: after 'use release' the row still differed from its own file."""
        name = create_name(self.session, name_text="George", kind="given_name")
        name.guid = "E01_001"
        set_name_translation(self.session, name, language_code="lt", translation="Džordžas")
        self.session.commit()

        self.assertNotEqual(_RECORD_WITH_NOTES, name_to_release_record(name))

        apply_release_record(self.session, _RECORD_WITH_NOTES, name)
        self.session.commit()
        self.session.refresh(name)

        self.assertEqual(_RECORD_WITH_NOTES, name_to_release_record(name))

    def test_omitted_notes_are_left_alone(self) -> None:
        """A record with no notes must not be treated as 'clear the notes'."""
        name = create_name(self.session, name_text="George", kind="given_name")
        set_name_translation(
            self.session, name, language_code="lt", translation="Džordžas", notes="keep me"
        )
        set_name_translation(self.session, name, language_code="lt", translation="Džordžas")
        self.session.commit()

        rendering = next(row for row in name.translations if row.language_code == "lt")
        self.assertEqual("keep me", rendering.notes)


if __name__ == "__main__":
    unittest.main()
