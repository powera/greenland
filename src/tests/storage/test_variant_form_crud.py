"""Tests for variant-form CRUD and the operation-log entries it writes.

A variant row has no GUID of its own, so every entry it writes is keyed to the
*owning lemma's* GUID with the variant's identity (kind, key, grammatical form,
language) in the fact -- the same shape phrase and name translations use.  The
tests below pin that down, along with the ``source is None`` opt-out that lets
every caller invoke the logging helpers unconditionally.

``add_variant_form`` is an idempotent upsert, which is the subtle case: calling
it again with different text silently updates the existing row, and an update
that changes nothing must not leave an entry claiming an edit occurred.
"""

from __future__ import annotations

import json
import unittest
from typing import List

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Import the full model registry so every table (FK targets included) is created.
import storage.models  # noqa: F401
from storage.crud.operation_log import VARIANT_CREATE, VARIANT_DELETE, VARIANT_UPDATE
from storage.crud.variant_form import add_variant_form, delete_variant
from storage.models.operation_log import OperationLog
from storage.models.schema import Base, Lemma
from storage.models.variant_form import VARIANT_KIND_SPELLING, VariantForm

LEMMA_GUID = "A02_008"
SOURCE = "test-suite/variants"


class VariantFormCrudLoggingTest(unittest.TestCase):
    """add_variant_form / delete_variant and their operation-log entries."""

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

    def _add(self, text: str = "grey", **overrides: object) -> VariantForm:
        kwargs = {
            "session": self.db,
            "lemma": self.lemma,
            "variant_form_text": text,
            "language_code": "en",
            "variant_key": "grey",
            "grammatical_form": "adjective/en_positive",
            "is_base_form": True,
            "source": SOURCE,
        }
        kwargs.update(overrides)
        return add_variant_form(**kwargs)  # type: ignore[arg-type]

    # -- create ---------------------------------------------------------

    def test_add_creates_row(self) -> None:
        variant = self._add()
        self.assertEqual(variant.variant_form_text, "grey")
        self.assertEqual(self.db.query(VariantForm).count(), 1)

    def test_add_logs_against_the_lemma_guid(self) -> None:
        """A variant has no GUID, so the entry names its lemma."""
        self._add()
        logs = self._logs(VARIANT_CREATE)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].entity_guid, LEMMA_GUID)
        self.assertEqual(logs[0].lemma_id, self.lemma.id)
        self.assertEqual(logs[0].source, SOURCE)

    def test_create_fact_identifies_which_variant(self) -> None:
        self._add()
        fact = json.loads(self._logs(VARIANT_CREATE)[0].fact)
        self.assertEqual(fact["variant_kind"], VARIANT_KIND_SPELLING)
        self.assertEqual(fact["variant_key"], "grey")
        self.assertEqual(fact["grammatical_form"], "adjective/en_positive")
        self.assertEqual(fact["language_code"], "en")
        self.assertEqual(fact["text"], "grey")

    def test_no_source_writes_no_log(self) -> None:
        """source=None means the caller did not ask for logging."""
        self._add(source=None)
        self.assertEqual(self.db.query(OperationLog).count(), 0)
        self.assertEqual(self.db.query(VariantForm).count(), 1)

    # -- update (the upsert branch) -------------------------------------

    def test_add_again_updates_rather_than_duplicating(self) -> None:
        first = self._add()
        second = self._add(text="greigh")
        self.assertEqual(first.id, second.id)
        self.assertEqual(self.db.query(VariantForm).count(), 1)
        self.assertEqual(second.variant_form_text, "greigh")

    def test_update_logs_the_real_diff(self) -> None:
        self._add()
        self._add(text="greigh")

        logs = self._logs(VARIANT_UPDATE)
        self.assertEqual(len(logs), 1)
        fact = json.loads(logs[0].fact)
        self.assertEqual(logs[0].entity_guid, LEMMA_GUID)
        self.assertEqual(fact["changed_fields"], ["variant_form_text"])
        change = fact["changes"][0]
        self.assertEqual(change["old_value"], "grey")
        self.assertEqual(change["new_value"], "greigh")

    def test_unchanged_update_logs_nothing(self) -> None:
        """A no-op upsert must not claim an edit occurred."""
        self._add()
        self._add()
        self.assertEqual(self._logs(VARIANT_UPDATE), [])

    def test_update_keeps_unsupplied_optional_fields(self) -> None:
        """Not passing ipa must not read as clearing it."""
        self._add(ipa_pronunciation="/ɡreɪ/")
        self._add(text="greigh")
        variant = self.db.query(VariantForm).one()
        self.assertEqual(variant.ipa_pronunciation, "/ɡreɪ/")

    # -- delete ---------------------------------------------------------

    def test_delete_removes_whole_paradigm(self) -> None:
        for grammatical_form, text in (
            ("adjective/en_positive", "grey"),
            ("adjective/en_comparative", "greyer"),
        ):
            self._add(text=text, grammatical_form=grammatical_form)

        deleted = delete_variant(
            session=self.db, lemma=self.lemma, variant_key="grey", source=SOURCE
        )
        self.assertEqual(deleted, 2)
        self.assertEqual(self.db.query(VariantForm).count(), 0)

    def test_delete_logs_one_entry_for_the_paradigm(self) -> None:
        self._add()
        self._add(text="greyer", grammatical_form="adjective/en_comparative")
        delete_variant(session=self.db, lemma=self.lemma, variant_key="grey", source=SOURCE)

        logs = self._logs(VARIANT_DELETE)
        self.assertEqual(len(logs), 1)
        fact = json.loads(logs[0].fact)
        self.assertEqual(logs[0].entity_guid, LEMMA_GUID)
        self.assertEqual(fact["count"], 2)
        self.assertEqual(fact["variant_key"], "grey")
        # The paradigm is the entity here, not any one slot.
        self.assertNotIn("grammatical_form", fact)

    def test_delete_matching_nothing_logs_nothing(self) -> None:
        deleted = delete_variant(
            session=self.db, lemma=self.lemma, variant_key="absent", source=SOURCE
        )
        self.assertEqual(deleted, 0)
        self.assertEqual(self._logs(VARIANT_DELETE), [])


if __name__ == "__main__":
    unittest.main()
