#!/usr/bin/python3

"""Unit tests for the sentence release record builder.

The round-trip regtest (src/regtest/release) covers the pipeline end to end
against the real tree, but it cannot reach the cases here: a database built
from data/release can never hold a hint without a reference, so only a
hand-built row exercises the export-side guard.
"""

from types import SimpleNamespace
from typing import Any, List, Optional

from storage.release.sentence import to_release_record


def _hint(position: int, slot: str, lemma_guid: Optional[str], text: str) -> Any:
    lemma = SimpleNamespace(guid=lemma_guid) if lemma_guid else None
    return SimpleNamespace(
        position=position, slot_name=slot, lemma=lemma, name=None, english_text=text
    )


def _sentence(word_hints: List[Any]) -> Any:
    return SimpleNamespace(
        guid="S_00001",
        sentence_collection=None,
        source_filename=None,
        pattern_type=None,
        tense=None,
        minimum_level=None,
        notes=None,
        translations=[],
        word_hints=word_hints,
        words=[],
        audio_reviews=[],
    )


class TestUnstorableHints:
    """A hint referencing neither a lemma nor a name cannot be stored.

    ck_word_hint_has_reference requires one of them, so exporting such a hint
    writes a row no import can read back -- which is what stopped the release
    round trip from converging.
    """

    def test_hint_without_any_reference_is_dropped(self) -> None:
        record = to_release_record(_sentence([_hint(0, "noun", None, "bike")]))
        assert "word_hints" not in record

    def test_linked_hints_survive_alongside_dropped_ones(self) -> None:
        record = to_release_record(
            _sentence(
                [
                    _hint(0, "adjective", "A19_014", "jealous"),
                    _hint(1, "other", None, "my"),
                    _hint(2, "noun", "N06_001", "bread"),
                ]
            )
        )
        assert [hint["lemma_guid"] for hint in record["word_hints"]] == ["A19_014", "N06_001"]

    def test_positions_are_left_as_written(self) -> None:
        """Dropping a hint must not renumber the survivors.

        uq_sentence_word_hint_position wants uniqueness, not contiguity, and
        renumbering would disagree with the sentence's `words` array.
        """
        record = to_release_record(
            _sentence(
                [
                    _hint(0, "other", None, "my"),
                    _hint(1, "noun", "N06_001", "bread"),
                ]
            )
        )
        assert [hint["position"] for hint in record["word_hints"]] == [1]


class TestUnshippedFields:
    """name_guid is omitted rather than written as a dead null."""

    def test_name_guid_absent_when_unset(self) -> None:
        record = to_release_record(_sentence([_hint(0, "noun", "N06_001", "bread")]))
        assert "name_guid" not in record["word_hints"][0]

    def test_name_guid_written_when_set(self) -> None:
        hint = _hint(0, "noun", None, "Vilnius")
        hint.name = SimpleNamespace(guid="NM_001")
        record = to_release_record(_sentence([hint]))
        assert record["word_hints"][0]["name_guid"] == "NM_001"
