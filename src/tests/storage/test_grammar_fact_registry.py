#!/usr/bin/python3

"""Every grammar fact type must be classified as exported or not.

The registry's rule is "export what a mechanical generator cannot reproduce"
(see the module docstring on ``storage.config.grammar_fact_registry``). The two
lists there are the source of truth, and a fact type added without being put in
one of them would silently default to database-only -- which nobody would
notice, because the lemma sync only ever diffs release-side facts.

These tests make that impossible: a new fact type fails until it is listed, and
the diff then shows a reviewer which side it landed on.
"""

import unittest

from storage.config.grammar_fact_registry import (
    EXPORTED_FACT_TYPES,
    GRAMMAR_FACT_DEFINITIONS,
    NOT_EXPORTED_FACT_TYPES,
    RELEASE_GRAMMAR_FACT_TYPES,
)


class TestEveryFactTypeIsClassified(unittest.TestCase):
    """The two lists must partition the registry, exactly."""

    def test_the_lists_cover_every_fact_type(self) -> None:
        self.assertEqual(
            set(EXPORTED_FACT_TYPES) | set(NOT_EXPORTED_FACT_TYPES),
            set(GRAMMAR_FACT_DEFINITIONS),
            "A grammar fact type was added or removed. Decide whether a mechanical "
            "generator can reproduce it (see the registry module docstring) and add it "
            "to EXPORTED_FACT_TYPES or NOT_EXPORTED_FACT_TYPES, with the reason.",
        )

    def test_no_fact_type_is_in_both_lists(self) -> None:
        self.assertEqual(set(), set(EXPORTED_FACT_TYPES) & set(NOT_EXPORTED_FACT_TYPES))

    def test_neither_list_has_duplicates(self) -> None:
        self.assertEqual(len(EXPORTED_FACT_TYPES), len(set(EXPORTED_FACT_TYPES)))
        self.assertEqual(len(NOT_EXPORTED_FACT_TYPES), len(set(NOT_EXPORTED_FACT_TYPES)))

    def test_neither_list_names_an_unknown_fact_type(self) -> None:
        """A typo in a list would otherwise silently classify nothing."""
        for fact_type in (*EXPORTED_FACT_TYPES, *NOT_EXPORTED_FACT_TYPES):
            with self.subTest(fact_type=fact_type):
                self.assertIn(fact_type, GRAMMAR_FACT_DEFINITIONS)


class TestDerivedFlagFollowsTheLists(unittest.TestCase):
    """release_sync is derived, so it cannot drift from the lists."""

    def test_flag_matches_list_membership(self) -> None:
        for fact_type, definition in sorted(GRAMMAR_FACT_DEFINITIONS.items()):
            with self.subTest(fact_type=fact_type):
                self.assertEqual(definition.release_sync, fact_type in EXPORTED_FACT_TYPES)

    def test_exported_types_reach_the_per_language_lookup(self) -> None:
        """The lookup the sync actually consults must agree with the list."""
        synced_somewhere = set()
        for fact_types in RELEASE_GRAMMAR_FACT_TYPES.values():
            synced_somewhere.update(fact_types)
        self.assertEqual(set(EXPORTED_FACT_TYPES), synced_somewhere)

    def test_non_exported_types_reach_no_language(self) -> None:
        synced_somewhere = set()
        for fact_types in RELEASE_GRAMMAR_FACT_TYPES.values():
            synced_somewhere.update(fact_types)
        self.assertEqual(set(), synced_somewhere & set(NOT_EXPORTED_FACT_TYPES))


class TestNothingIsBothUngeneratedAndUnexported(unittest.TestCase):
    """The empty quadrant, enforced.

    A fact that is neither GENERATED nor EXPORTED could only have been typed by
    a human, and nothing can put it back after a rebuild: no agent regenerates
    it and no release file carries it. That combination is always a mistake, so
    it is checked rather than trusted.
    """

    def test_every_unexported_fact_type_is_generated(self) -> None:
        for fact_type in NOT_EXPORTED_FACT_TYPES:
            with self.subTest(fact_type=fact_type):
                self.assertTrue(
                    GRAMMAR_FACT_DEFINITIONS[fact_type].generatable,
                    f"{fact_type} is neither exported nor automatically generated, so a "
                    f"rebuild would destroy it. Export it, or give it a generator.",
                )


class TestTheTwoAxesAreIndependent(unittest.TestCase):
    """EXPORTED and GENERATED are orthogonal; these are the worked examples.

    GENERATED asks "can an agent produce this at all, by Python or LLM".
    EXPORTED asks "is this *not* derivable mechanically, in Python, from the
    rest of data/release". Reading one off the other is how facts get lost.
    """

    def test_a_generated_fact_can_still_be_exported(self) -> None:
        """measure_words: an LLM call is not a mechanical derivation."""
        self.assertTrue(GRAMMAR_FACT_DEFINITIONS["measure_words"].generatable)
        self.assertIn("measure_words", EXPORTED_FACT_TYPES)

    def test_a_generator_input_is_exported(self) -> None:
        """grammatical_gender feeds decline_noun; nothing in Python derives it."""
        self.assertTrue(GRAMMAR_FACT_DEFINITIONS["grammatical_gender"].generatable)
        self.assertIn("grammatical_gender", EXPORTED_FACT_TYPES)

    def test_a_python_derivation_is_not_exported(self) -> None:
        """declension_class falls out of decline_noun given the noun and its gender."""
        self.assertIn("declension_class", NOT_EXPORTED_FACT_TYPES)
        # ...which is only safe while its inputs ship.
        self.assertIn("grammatical_gender", EXPORTED_FACT_TYPES)

    def test_both_axes_are_actually_populated_both_ways(self) -> None:
        """Guard the docstring's quadrant table against quietly collapsing."""
        generated = {ft for ft, d in GRAMMAR_FACT_DEFINITIONS.items() if d.generatable}
        exported = set(EXPORTED_FACT_TYPES)
        self.assertTrue(exported - generated, "no exported-but-not-generated fact types")
        self.assertTrue(exported & generated, "no exported-and-generated fact types")
        self.assertTrue(generated - exported, "no generated-but-not-exported fact types")


if __name__ == "__main__":
    unittest.main()
