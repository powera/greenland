#!/usr/bin/python3

"""``NameTranslation.localized_alternative`` and its release round trip.

A name has one rendering per language and that is the one a translation uses:
Russian writes "Джон" for John. Some languages also have a localized
alternative -- "Иван", the character recast as a local rather than respelled --
which is recorded so a reviewer reading Russian output can tell a deliberate
localization from a botched transliteration. It is never pinned into a prompt.

The round-trip assertions mirror ``test_name_translation_notes``: the
whole-record engine compares ``to_record(row) == release_record``, so a field
the import path drops shows a difference that picking "use release" can never
clear.
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

_RECORD_WITH_ALTERNATIVE = {
    "guid": "E01_002",
    "kind": "given_name",
    "name_text": "John",
    "translations": {"ru": "Джон"},
    "translation_metadata": {
        "ru": {
            "localized_alternative": "Иван",
            "notes": "Иван only where the cast is recast as Russian",
        }
    },
}

_RECORD_WITHOUT_ALTERNATIVE = {
    "guid": "E01_003",
    "kind": "given_name",
    "name_text": "George",
    "translations": {"lt": "Džordžas"},
}


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class TestNameLocalizedAlternative(unittest.TestCase):
    def setUp(self) -> None:
        self.session = _make_session()

    def tearDown(self) -> None:
        self.session.close()

    def test_crud_stores_the_alternative(self) -> None:
        name = create_name(self.session, name_text="John", kind="given_name")
        row = set_name_translation(
            self.session,
            name,
            language_code="ru",
            translation="Джон",
            localized_alternative="Иван",
        )
        self.assertEqual("Джон", row.translation)
        self.assertEqual("Иван", row.localized_alternative)

    def test_import_then_export_reproduces_the_record(self) -> None:
        name = import_release_record(self.session, _RECORD_WITH_ALTERNATIVE)
        self.session.commit()
        self.assertIsNotNone(name)
        assert name is not None  # for type checkers
        self.assertEqual(_RECORD_WITH_ALTERNATIVE, name_to_release_record(name))

    def test_applying_a_record_clears_the_difference(self) -> None:
        name = create_name(self.session, name_text="John", kind="given_name")
        name.guid = "E01_002"
        set_name_translation(self.session, name, language_code="ru", translation="Джон")
        self.session.commit()

        self.assertNotEqual(_RECORD_WITH_ALTERNATIVE, name_to_release_record(name))

        apply_release_record(self.session, _RECORD_WITH_ALTERNATIVE, name)
        self.session.commit()
        self.session.refresh(name)

        self.assertEqual(_RECORD_WITH_ALTERNATIVE, name_to_release_record(name))

    def test_a_name_without_one_serializes_as_it_did_before(self) -> None:
        """The field is omitted when unset, so old records stay byte-identical."""
        name = import_release_record(self.session, _RECORD_WITHOUT_ALTERNATIVE)
        self.session.commit()
        assert name is not None

        record = name_to_release_record(name)
        self.assertEqual(_RECORD_WITHOUT_ALTERNATIVE, record)
        self.assertNotIn("translation_metadata", record)

    def test_omitting_the_alternative_is_not_clearing_it(self) -> None:
        """A later write that does not mention it must leave it in place."""
        name = create_name(self.session, name_text="John", kind="given_name")
        set_name_translation(
            self.session,
            name,
            language_code="ru",
            translation="Джон",
            localized_alternative="Иван",
        )
        set_name_translation(self.session, name, language_code="ru", translation="Джон")
        self.session.commit()

        rendering = next(row for row in name.translations if row.language_code == "ru")
        self.assertEqual("Иван", rendering.localized_alternative)

    def test_the_alternative_is_not_a_second_rendering(self) -> None:
        """It lives on the one row, not as a competing rendering of its own."""
        name = create_name(self.session, name_text="John", kind="given_name")
        set_name_translation(
            self.session,
            name,
            language_code="ru",
            translation="Джон",
            localized_alternative="Иван",
        )
        self.session.commit()

        self.assertEqual(1, len(name.translations))
        record = name_to_release_record(name)
        self.assertEqual({"ru": "Джон"}, record["translations"])


if __name__ == "__main__":
    unittest.main()
