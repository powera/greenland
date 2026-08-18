#!/usr/bin/python3

"""Pulling one phrase translation from release must not wipe its status fields.

``set_phrase_translation`` assigns ``translation_status``,
``translation_status_note`` and ``verified`` unconditionally, defaulting them to
None/False. The phrase sync called it positionally with only the text, so
choosing "use release" for one language silently destroyed the status metadata
that the exporter ships and the additions path imports.

These tests pin the CRUD contract that makes the call site's omission
destructive, so the coupling stays visible.
"""

from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import storage.models  # noqa: F401 -- register every model before create_all
from storage.crud.phrase import set_phrase_translation
from storage.models.schema import Base, Phrase


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class TestSetPhraseTranslation(unittest.TestCase):
    def setUp(self) -> None:
        self.session = _make_session()
        self.phrase = Phrase(guid="F01_001", phrase_subtype="greeting", label="See you later")
        self.session.add(self.phrase)
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()

    def _set(self, **kwargs: object) -> None:
        set_phrase_translation(self.session, self.phrase, "lt", "Iki pasimatymo", **kwargs)  # type: ignore[arg-type]
        self.session.commit()

    def test_status_fields_are_stored_when_passed(self) -> None:
        self._set(
            translation_status="needs_review",
            translation_status_note="idiomatic register",
        )
        row = self.phrase.translations[0]
        self.assertEqual("needs_review", row.translation_status)
        self.assertEqual("idiomatic register", row.translation_status_note)

    def test_omitting_the_status_clears_it(self) -> None:
        """The contract that made the sync's positional call destructive.

        This is deliberate on the CRUD side -- it is a full assignment, not a
        patch -- which is exactly why every caller has to pass the metadata it
        wants kept.
        """
        self._set(translation_status="needs_review")
        self.assertEqual("needs_review", self.phrase.translations[0].translation_status)

        self._set()
        self.assertIsNone(self.phrase.translations[0].translation_status)


if __name__ == "__main__":
    unittest.main()
