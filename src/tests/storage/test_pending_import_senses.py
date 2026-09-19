"""Tests for the pending-import sense detail accessors.

``PendingImport.translations`` and ``PendingImport.example_sentences`` carry the
parts of a staged LLM response that have nowhere else to live until the term
becomes a lemma. These cover the round trip, the NULL-for-empty encoding that
keeps "nothing carried" unambiguous, and the tolerance for malformed stored
JSON -- a staged row is review material, so a bad value is dropped rather than
raising in the middle of an approval.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Import the full model registry so every table is created.
import storage.models  # noqa: F401
from storage.crud.pending_import_senses import (
    decode_example_sentences,
    decode_translations,
    read_pending_import_example_sentences,
    read_pending_import_translations,
    serialize_example_sentences,
    serialize_translations,
)
from storage.models.imports import PendingImport
from storage.models.schema import Base


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


def _pending(**kwargs: Any) -> PendingImport:
    """A staged row with the NOT NULL columns filled in."""
    defaults: Dict[str, Any] = {
        "english_word": "parasite",
        "definition": "an organism living on a host",
        "disambiguation_translation": "parazitas",
        "disambiguation_language": "lt",
    }
    defaults.update(kwargs)
    return PendingImport(**defaults)


class TestSerializeTranslations:
    def test_round_trips_through_the_column(self, session: Session) -> None:
        pending = _pending(
            translations=serialize_translations({"lt": "parazitas", "fr": "parasite"})
        )
        session.add(pending)
        session.flush()

        assert read_pending_import_translations(pending) == {
            "lt": "parazitas",
            "fr": "parasite",
        }

    def test_empty_mapping_becomes_null(self) -> None:
        assert serialize_translations({}) is None

    def test_blank_values_are_dropped(self) -> None:
        # A blank translation is the same as an absent one; keeping both shapes
        # would make "untranslated" ambiguous.
        assert serialize_translations({"lt": "   ", "fr": "parasite"}) == json.dumps(
            {"fr": "parasite"}, ensure_ascii=False
        )

    def test_all_blank_values_become_null(self) -> None:
        assert serialize_translations({"lt": "", "fr": "  "}) is None

    def test_non_ascii_is_stored_unescaped(self) -> None:
        stored = serialize_translations({"zh": "寄生虫"})
        assert stored is not None
        assert "寄生虫" in stored


class TestDecodeTranslations:
    def test_null_yields_empty(self) -> None:
        assert decode_translations(None) == {}

    def test_malformed_json_is_ignored(self) -> None:
        assert decode_translations("not json at all") == {}

    def test_wrong_json_shape_is_ignored(self) -> None:
        # A list where an object belongs: readable, but not translations.
        assert decode_translations('["parazitas"]') == {}

    def test_non_string_values_are_dropped(self) -> None:
        assert decode_translations('{"lt": "parazitas", "fr": 7}') == {"lt": "parazitas"}


class TestExampleSentences:
    def test_round_trips_through_the_column(self, session: Session) -> None:
        sentences = ["The parasite weakened its host.", "Some parasites are microscopic."]
        pending = _pending(example_sentences=serialize_example_sentences(sentences))
        session.add(pending)
        session.flush()

        assert read_pending_import_example_sentences(pending) == sentences

    def test_empty_list_becomes_null(self) -> None:
        assert serialize_example_sentences([]) is None

    def test_blank_entries_are_dropped(self) -> None:
        assert serialize_example_sentences(["  ", "A real sentence."]) == json.dumps(
            ["A real sentence."], ensure_ascii=False
        )

    def test_entries_are_stripped(self) -> None:
        assert decode_example_sentences('["  padded  "]') == ["padded"]

    def test_null_yields_empty(self) -> None:
        assert decode_example_sentences(None) == []

    def test_malformed_json_is_ignored(self) -> None:
        assert decode_example_sentences("{oops") == []

    def test_non_string_entries_are_dropped(self) -> None:
        assert decode_example_sentences('["a sentence", 3, null]') == ["a sentence"]


class TestDefaults:
    def test_a_row_staged_without_detail_reads_empty(self, session: Session) -> None:
        # Every row staged before these columns existed looks like this, and
        # approval must fall back to its LLM query rather than break.
        pending = _pending()
        session.add(pending)
        session.flush()

        assert read_pending_import_translations(pending) == {}
        assert read_pending_import_example_sentences(pending) == []
