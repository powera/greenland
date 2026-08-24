#!/usr/bin/python3

"""Emoji assignment rules: ordering, uniqueness, and conflict reporting.

The storage round trip is covered by ``test_lemma_release_record``; what is
pinned here is the policy layered on top of it -- that the first entry is the
primary glyph, and that one emoji belongs to at most one lemma.
"""

from __future__ import annotations

import unittest
from typing import Dict, List

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import storage.models  # noqa: F401 -- register every model before create_all
from storage.models.schema import Base, Lemma
from storage.models.emoji import (
    EMOJI_STATUS_ASSIGNED,
    EMOJI_STATUS_MISSING_LEMMA,
    EMOJI_STATUS_NO_MATCH,
    EMOJI_STATUS_UNDECIDED,
    Emoji,
)
from storage.models.imports import PendingImport
from storage.release.lemma import decode_db_emoji, encode_db_emoji
from words.emoji import (
    EmojiConflictError,
    assign_emoji,
    assigned_emoji_values,
    attach_pending_emoji_to_lemma,
    emoji_name,
    emoji_values,
    find_emoji_holders,
    find_mirror_drift,
    lemma_emoji,
    mark_missing_lemma,
    mark_no_match,
    normalize_emoji_input,
    primary_emoji,
    refresh_lemma_mirror,
    status_counts,
)


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _add_lemma(session: Session, guid: str, text: str, emoji: str | None = None) -> Lemma:
    lemma = Lemma(
        guid=guid,
        lemma_text=text,
        definition_text=f"The concept {text}.",
        pos_type="noun",
        emoji=emoji,
    )
    session.add(lemma)
    session.flush()
    return lemma


class NormalizeInputTests(unittest.TestCase):
    """Reviewer and agent input arrives as a loose string of glyphs."""

    def test_splits_on_whitespace_and_commas(self) -> None:
        self.assertEqual(
            [{"type": "unicode", "value": "🐕"}, {"type": "unicode", "value": "🐶"}],
            normalize_emoji_input("🐕, 🐶"),
        )

    def test_preserves_order_because_first_is_primary(self) -> None:
        self.assertEqual(["🐶", "🐕"], [e["value"] for e in normalize_emoji_input("🐶 🐕")])

    def test_drops_repeats_within_one_input(self) -> None:
        self.assertEqual(["🐕", "🐶"], [e["value"] for e in normalize_emoji_input("🐕 🐶 🐕")])

    def test_empty_input_clears(self) -> None:
        self.assertEqual([], normalize_emoji_input("   "))


class EmojiNameTests(unittest.TestCase):
    def test_single_codepoint_has_a_name(self) -> None:
        self.assertEqual("DOG", emoji_name("🐕"))

    def test_zwj_sequence_has_no_single_name(self) -> None:
        self.assertIsNone(emoji_name("🧑‍🌾"))


class PrimaryEmojiTests(unittest.TestCase):
    """Order is meaning: the first entry is the one single-glyph consumers use."""

    def setUp(self) -> None:
        self.session = _make_session()

    def tearDown(self) -> None:
        self.session.close()

    def test_primary_is_the_first_entry(self) -> None:
        lemma = _add_lemma(
            self.session,
            "N05_001",
            "dog",
            encode_db_emoji(
                [{"type": "unicode", "value": "🐕"}, {"type": "unicode", "value": "🐶"}]
            ),
        )
        self.assertEqual("🐕", primary_emoji(lemma))
        self.assertEqual(["🐕", "🐶"], emoji_values(lemma))

    def test_unassigned_lemma_has_no_primary(self) -> None:
        lemma = _add_lemma(self.session, "N05_002", "justice")
        self.assertIsNone(primary_emoji(lemma))
        self.assertEqual([], lemma_emoji(lemma))


class AssignEmojiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = _make_session()
        self.dog = _add_lemma(self.session, "N05_001", "dog")
        self.puppy = _add_lemma(self.session, "N05_002", "puppy")

    def tearDown(self) -> None:
        self.session.close()

    def test_assigns_and_encodes(self) -> None:
        assign_emoji(self.session, self.dog, normalize_emoji_input("🐕 🐶"))
        self.assertEqual(["🐕", "🐶"], emoji_values(self.dog))

    def test_empty_sequence_clears_the_assignment(self) -> None:
        assign_emoji(self.session, self.dog, normalize_emoji_input("🐕"))
        assign_emoji(self.session, self.dog, [])
        self.assertIsNone(self.dog.emoji)

    def test_rejects_an_emoji_held_by_another_lemma(self) -> None:
        assign_emoji(self.session, self.dog, normalize_emoji_input("🐕"))
        with self.assertRaises(EmojiConflictError) as caught:
            assign_emoji(self.session, self.puppy, normalize_emoji_input("🐕"))
        self.assertEqual("🐕", caught.exception.value)
        self.assertIs(self.dog, caught.exception.holder)

    def test_conflict_on_an_alternate_also_blocks(self) -> None:
        """Uniqueness covers every entry, not just the primary."""
        assign_emoji(self.session, self.dog, normalize_emoji_input("🐕 🐶"))
        with self.assertRaises(EmojiConflictError):
            assign_emoji(self.session, self.puppy, normalize_emoji_input("🐶"))

    def test_nothing_is_written_when_the_assignment_conflicts(self) -> None:
        assign_emoji(self.session, self.dog, normalize_emoji_input("🐕"))
        assign_emoji(self.session, self.puppy, normalize_emoji_input("🦮"))
        with self.assertRaises(EmojiConflictError):
            assign_emoji(self.session, self.puppy, normalize_emoji_input("🐩 🐕"))
        self.assertEqual(["🦮"], emoji_values(self.puppy))

    def test_resaving_a_lemmas_own_emoji_is_not_a_self_conflict(self) -> None:
        assign_emoji(self.session, self.dog, normalize_emoji_input("🐕 🐶"))
        assign_emoji(self.session, self.dog, normalize_emoji_input("🐶 🐕"))
        self.assertEqual(["🐶", "🐕"], emoji_values(self.dog))

    def test_duplicates_within_one_assignment_collapse(self) -> None:
        assign_emoji(self.session, self.dog, [{"type": "unicode", "value": "🐕"}] * 3)
        self.assertEqual(["🐕"], emoji_values(self.dog))


class UniquenessIsATableConstraintTests(unittest.TestCase):
    """One glyph, one row: the emoji table cannot name two lemmas at once."""

    def setUp(self) -> None:
        self.session = _make_session()
        self.dog = _add_lemma(self.session, "N05_001", "dog")
        self.pet = _add_lemma(self.session, "N05_002", "pet")

    def tearDown(self) -> None:
        self.session.close()

    def test_one_row_per_glyph_regardless_of_reassignment(self) -> None:
        assign_emoji(self.session, self.dog, normalize_emoji_input("\U0001F415"))
        with self.assertRaises(EmojiConflictError):
            assign_emoji(self.session, self.pet, normalize_emoji_input("\U0001F415"))
        self.assertEqual(1, self.session.query(Emoji).filter(Emoji.value == "\U0001F415").count())

    def test_holders_lookup_skips_the_excluded_lemma(self) -> None:
        assign_emoji(self.session, self.dog, normalize_emoji_input("\U0001F415"))
        self.assertEqual({"\U0001F415": self.dog}, find_emoji_holders(self.session, ["\U0001F415"]))
        self.assertEqual(
            {}, find_emoji_holders(self.session, ["\U0001F415"], exclude_lemma_id=self.dog.id)
        )

    def test_assigned_values_indexes_every_glyph(self) -> None:
        assign_emoji(self.session, self.dog, normalize_emoji_input("\U0001F415 \U0001F436"))
        assigned = assigned_emoji_values(self.session)
        self.assertEqual({"\U0001F415", "\U0001F436"}, set(assigned))
        self.assertIs(self.dog, assigned["\U0001F436"])


class ReviewOutcomeTests(unittest.TestCase):
    """A glyph can be assigned, dismissed, or flagged as a missing word."""

    def setUp(self) -> None:
        self.session = _make_session()
        self.dog = _add_lemma(self.session, "N05_001", "dog")

    def tearDown(self) -> None:
        self.session.close()

    def test_no_match_is_distinct_from_undecided(self) -> None:
        """A dismissed glyph must not resurface, which is what ends the walk."""
        row = mark_no_match(self.session, "\u27B0", notes="a shape, not a thing")
        self.assertEqual(EMOJI_STATUS_NO_MATCH, row.status)
        self.assertIsNone(row.lemma_id)
        self.assertEqual("a shape, not a thing", row.notes)

    def test_missing_lemma_records_the_staged_term(self) -> None:
        pending = PendingImport(
            english_word="ninja",
            definition="A covert agent of feudal Japan.",
            disambiguation_translation="ninja",
            disambiguation_language="lt",
        )
        self.session.add(pending)
        self.session.flush()

        row = mark_missing_lemma(self.session, "\U0001F977", pending_import_id=pending.id)
        self.assertEqual(EMOJI_STATUS_MISSING_LEMMA, row.status)
        self.assertEqual(pending.id, row.pending_import_id)
        self.assertIsNone(row.lemma_id)

    def test_approving_the_pending_term_attaches_the_glyph(self) -> None:
        pending = PendingImport(
            english_word="ninja",
            definition="A covert agent of feudal Japan.",
            disambiguation_translation="ninja",
            disambiguation_language="lt",
        )
        self.session.add(pending)
        self.session.flush()
        mark_missing_lemma(self.session, "\U0001F977", pending_import_id=pending.id)

        ninja = _add_lemma(self.session, "N05_050", "ninja")
        attached = attach_pending_emoji_to_lemma(self.session, pending.id, ninja)

        self.assertEqual(1, attached)
        self.assertEqual(["\U0001F977"], emoji_values(ninja))

    def test_dismissing_an_assigned_glyph_clears_the_mirror(self) -> None:
        assign_emoji(self.session, self.dog, normalize_emoji_input("\U0001F415"))
        mark_no_match(self.session, "\U0001F415")
        self.assertEqual([], emoji_values(self.dog))

    def test_status_counts_cover_every_state(self) -> None:
        assign_emoji(self.session, self.dog, normalize_emoji_input("\U0001F415"))
        mark_no_match(self.session, "\u27B0")
        counts = status_counts(self.session)
        self.assertEqual(1, counts[EMOJI_STATUS_ASSIGNED])
        self.assertEqual(1, counts[EMOJI_STATUS_NO_MATCH])


class MirrorTests(unittest.TestCase):
    """Lemma.emoji is derived from the table and is what reaches data/release."""

    def setUp(self) -> None:
        self.session = _make_session()
        self.dog = _add_lemma(self.session, "N05_001", "dog")

    def tearDown(self) -> None:
        self.session.close()

    def test_assignment_writes_the_release_shaped_mirror(self) -> None:
        assign_emoji(self.session, self.dog, normalize_emoji_input("\U0001F415"))
        self.assertEqual(
            [{"type": "unicode", "value": "\U0001F415"}], decode_db_emoji(self.dog.emoji)
        )

    def test_refresh_preserves_primacy_when_no_order_is_given(self) -> None:
        assign_emoji(self.session, self.dog, normalize_emoji_input("\U0001F436 \U0001F415"))
        refresh_lemma_mirror(self.session, self.dog)
        self.assertEqual(["\U0001F436", "\U0001F415"], emoji_values(self.dog))

    def test_release_import_writing_the_mirror_alone_is_reported_as_drift(self) -> None:
        """A release round trip writes Lemma.emoji directly, bypassing the table."""
        self.dog.emoji = encode_db_emoji([{"type": "unicode", "value": "\U0001F415"}])
        self.session.flush()

        drift = find_mirror_drift(self.session)
        self.assertEqual(1, len(drift))
        self.assertEqual(["\U0001F415"], drift[0].mirror_values)
        self.assertEqual([], drift[0].table_values)

    def test_consistent_data_reports_no_drift(self) -> None:
        assign_emoji(self.session, self.dog, normalize_emoji_input("\U0001F415 \U0001F436"))
        self.assertEqual([], find_mirror_drift(self.session))

    def test_reordering_the_mirror_is_not_drift(self) -> None:
        assign_emoji(self.session, self.dog, normalize_emoji_input("\U0001F415 \U0001F436"))
        assign_emoji(self.session, self.dog, normalize_emoji_input("\U0001F436 \U0001F415"))
        self.assertEqual([], find_mirror_drift(self.session))


if __name__ == "__main__":
    unittest.main()
