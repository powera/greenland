"""Tests for derivative-form release serialization and CRUD logging.

Two things are pinned here.

**The release record shape.**  A lemma's per-language line carries an
array-shaped ``forms`` key; a dict-shaped ``derivative_forms`` key is the older
format that the loader still accepts.  ``storage.migrate`` once wrote the old
shape while every shipped file used the new one, so a whole-tree re-export
silently rewrote the entire release tree.  The builder now lives in one place
and is asserted to emit the shipped shape, in *paradigm* order rather than
alphabetical -- "positive", "comparative", "superlative", the order a reader
expects and the order the files are already in.

**The operation-log entries.**  A derivative form has no GUID of its own, so
its entries are keyed to the owning lemma's GUID, with ``source=None`` opting
out of logging entirely.
"""

from __future__ import annotations

import json
import unittest
from typing import List

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Import the full model registry so every table (FK targets included) is created.
import storage.models  # noqa: F401
from storage.crud.derivative_form import (
    add_derivative_form,
    delete_derivative_form,
    update_derivative_form,
)
from storage.crud.operation_log import (
    DERIVATIVE_FORM_CREATE,
    DERIVATIVE_FORM_DELETE,
    DERIVATIVE_FORM_UPDATE,
)
from storage.models.operation_log import OperationLog
from storage.models.schema import Base, DerivativeForm, Lemma
from storage.release.derivative_form import forms_by_language, split_forms_and_synonyms

LEMMA_GUID = "A02_008"
SOURCE = "test-suite/forms"


def _form(grammatical_form: str, text: str, is_base_form: bool = False) -> DerivativeForm:
    return DerivativeForm(
        language_code="en",
        grammatical_form=grammatical_form,
        derivative_form_text=text,
        is_base_form=is_base_form,
    )


class DerivativeFormReleaseRecordTest(unittest.TestCase):
    """The release record shape and ordering."""

    def test_record_uses_the_shipped_key_names(self) -> None:
        """``text``, not the legacy ``form``; no null pronunciations."""
        inflections, _ = split_forms_and_synonyms([_form("noun/en_plural", "dogs")])
        self.assertEqual(
            inflections,
            [{"grammatical_form": "noun/en_plural", "text": "dogs", "is_base_form": False}],
        )

    def test_forms_are_written_in_paradigm_order(self) -> None:
        """Not alphabetical: comparative must not sort ahead of positive."""
        inflections, _ = split_forms_and_synonyms(
            [
                _form("adjective/en_superlative", "grayest"),
                _form("adjective/en_comparative", "grayer"),
                _form("adjective/en_positive", "gray", is_base_form=True),
            ]
        )
        self.assertEqual(
            [entry["grammatical_form"] for entry in inflections],
            [
                "adjective/en_positive",
                "adjective/en_comparative",
                "adjective/en_superlative",
            ],
        )

    def test_synonyms_are_split_out_of_forms(self) -> None:
        """A synonym is not an inflection and carries no is_base_form."""
        inflections, synonyms = split_forms_and_synonyms(
            [
                _form("noun/en_singular", "bicycle", is_base_form=True),
                _form("synonym_near", "cycle"),
            ]
        )
        self.assertEqual([entry["text"] for entry in inflections], ["bicycle"])
        self.assertEqual([entry["text"] for entry in synonyms], ["cycle"])
        self.assertNotIn("is_base_form", synonyms[0])

    def test_pronunciations_are_omitted_when_unset(self) -> None:
        with_ipa = _form("noun/en_singular", "dog", is_base_form=True)
        with_ipa.ipa_pronunciation = "/dɒɡ/"
        inflections, _ = split_forms_and_synonyms([with_ipa])
        self.assertEqual(inflections[0]["ipa"], "/dɒɡ/")
        self.assertNotIn("phonetic", inflections[0])

    def test_languages_without_data_are_absent(self) -> None:
        """Callers test membership to decide whether to write the key."""
        forms_by_lang, synonyms_by_lang = forms_by_language([_form("noun/en_plural", "dogs")])
        self.assertEqual(list(forms_by_lang), ["en"])
        self.assertEqual(synonyms_by_lang, {})


class DerivativeFormCrudLoggingTest(unittest.TestCase):
    """Operation-log entries written by the derivative-form CRUD."""

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.lemma = Lemma(
            lemma_text="gray",
            definition_text="Of a color between black and white.",
            pos_type="adjective",
            pos_subtype="color",
            guid=LEMMA_GUID,
            difficulty_level=3,
        )
        self.db.add(self.lemma)
        self.db.flush()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _logs(self, operation_type: str) -> List[OperationLog]:
        return (
            self.db.query(OperationLog).filter(OperationLog.operation_type == operation_type).all()
        )

    def _add(self, text: str = "grayer", source: object = SOURCE) -> DerivativeForm:
        return add_derivative_form(
            session=self.db,
            lemma=self.lemma,
            derivative_form_text=text,
            language_code="en",
            grammatical_form="adjective/en_comparative",
            source=source,  # type: ignore[arg-type]
        )

    def test_create_logs_against_the_lemma_guid(self) -> None:
        self._add()
        logs = self._logs(DERIVATIVE_FORM_CREATE)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].entity_guid, LEMMA_GUID)
        fact = json.loads(logs[0].fact)
        self.assertEqual(fact["text"], "grayer")
        self.assertEqual(fact["grammatical_form"], "adjective/en_comparative")

    def test_no_source_writes_no_log(self) -> None:
        self._add(source=None)
        self.assertEqual(self.db.query(OperationLog).count(), 0)
        self.assertEqual(self.db.query(DerivativeForm).count(), 1)

    def test_update_logs_the_real_diff(self) -> None:
        form = self._add()
        update_derivative_form(self.db, form.id, derivative_form_text="greyer", source=SOURCE)
        logs = self._logs(DERIVATIVE_FORM_UPDATE)
        self.assertEqual(len(logs), 1)
        fact = json.loads(logs[0].fact)
        self.assertEqual(logs[0].entity_guid, LEMMA_GUID)
        self.assertEqual(fact["changed_fields"], ["derivative_form_text"])
        self.assertEqual(fact["changes"][0]["old_value"], "grayer")

    def test_unchanged_update_logs_nothing(self) -> None:
        form = self._add()
        update_derivative_form(self.db, form.id, derivative_form_text="grayer", source=SOURCE)
        self.assertEqual(self._logs(DERIVATIVE_FORM_UPDATE), [])

    def test_delete_logs_before_the_row_is_gone(self) -> None:
        form = self._add()
        self.assertTrue(delete_derivative_form(self.db, form.id, source=SOURCE))

        logs = self._logs(DERIVATIVE_FORM_DELETE)
        self.assertEqual(len(logs), 1)
        # The entry outlives the row it describes, which is the point.
        self.assertEqual(logs[0].entity_guid, LEMMA_GUID)
        self.assertEqual(json.loads(logs[0].fact)["text"], "grayer")
        self.assertEqual(self.db.query(DerivativeForm).count(), 0)


if __name__ == "__main__":
    unittest.main()
