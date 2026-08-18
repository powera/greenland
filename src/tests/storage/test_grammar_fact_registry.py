#!/usr/bin/python3

"""Pin which grammar fact types reach data/release and which stay in the database.

``GrammarFactDefinition.release_sync`` defaults to ``False``, so a fact type
added without thinking about it silently becomes database-only -- and the lemma
sync only ever diffs release-side facts, so nobody would notice. These tests
make that choice explicit: a new fact type fails here until it is listed in one
of the two sets below, and the diff shows a reviewer which side it landed on.

Changing a fact type's side changes what a release export writes. That is a
deliberate act; update the sets here in the same commit and say why.
"""

import unittest

from storage.config.grammar_fact_registry import (
    GRAMMAR_FACT_DEFINITIONS,
    RELEASE_GRAMMAR_FACT_TYPES,
)

#: Fact types written to and read from ``data/release/lemmas/{lang}.jsonl``.
#: Almost all are inflected forms -- a principal part or an irregular form that
#: cannot be regenerated from the lemma alone.
RELEASE_SYNCED_FACT_TYPES = frozenset(
    {
        "1s_future",
        "1s_past",
        "1s_present",
        "3p_past",
        "3p_present",
        "3s_past",
        "3s_present",
        "comparative",
        "fanciful_collective",
        "feminine_form",
        "gradability",
        "infinitive",
        "measure_words",
        "number_type",
        "past",
        "past_participle",
        "plural",
        "superlative",
    }
)

#: Fact types that stay in the database. These are lexical classifications an
#: agent can regenerate, rather than forms that must round-trip.
#:
#: Two of these are worth revisiting: ``grammatical_gender`` and
#: ``declension_class`` drive inflection rather than decorate it, and while they
#: sit here the release tree cannot rebuild a database that declines correctly.
#: Moving either is a release-format decision, not a cleanup.
DATABASE_ONLY_FACT_TYPES = frozenset(
    {
        "animacy",
        "auxiliary_verb",
        "countability",
        "declension_class",
        "grammatical_gender",
        "verb_reflexivity",
        "verb_transitivity",
    }
)


class TestGrammarFactReleasePartition(unittest.TestCase):
    """The registry's release_sync flags, pinned."""

    def test_every_fact_type_is_classified(self) -> None:
        """A new fact type must be added to exactly one of the two sets."""
        self.assertEqual(
            RELEASE_SYNCED_FACT_TYPES | DATABASE_ONLY_FACT_TYPES,
            set(GRAMMAR_FACT_DEFINITIONS),
            "A grammar fact type was added or removed. Decide whether it belongs in "
            "data/release and add it to RELEASE_SYNCED_FACT_TYPES or "
            "DATABASE_ONLY_FACT_TYPES in this file.",
        )

    def test_the_two_sets_do_not_overlap(self) -> None:
        self.assertEqual(frozenset(), RELEASE_SYNCED_FACT_TYPES & DATABASE_ONLY_FACT_TYPES)

    def test_release_sync_flags_match_the_pinned_sets(self) -> None:
        """Each definition's release_sync flag agrees with its set membership."""
        for fact_type, definition in sorted(GRAMMAR_FACT_DEFINITIONS.items()):
            with self.subTest(fact_type=fact_type):
                self.assertEqual(
                    definition.release_sync,
                    fact_type in RELEASE_SYNCED_FACT_TYPES,
                    f"{fact_type} has release_sync={definition.release_sync} but is pinned "
                    f"as {'release-synced' if fact_type in RELEASE_SYNCED_FACT_TYPES else 'database-only'}",
                )

    def test_database_only_types_reach_no_language(self) -> None:
        """Nothing database-only leaks into the per-language release lookup."""
        synced_somewhere = set()
        for fact_types in RELEASE_GRAMMAR_FACT_TYPES.values():
            synced_somewhere.update(fact_types)
        self.assertEqual(frozenset(), synced_somewhere & DATABASE_ONLY_FACT_TYPES)

    def test_every_release_type_reaches_at_least_one_language(self) -> None:
        """A release-synced type with no languages would be silently inert."""
        synced_somewhere = set()
        for fact_types in RELEASE_GRAMMAR_FACT_TYPES.values():
            synced_somewhere.update(fact_types)
        self.assertEqual(RELEASE_SYNCED_FACT_TYPES, synced_somewhere)


if __name__ == "__main__":
    unittest.main()
