#!/usr/bin/env python3

"""Tests for reverse English inflection (langtools.en.utils.candidate_base_forms).

The helper guesses which base forms an inflected word could have come from, so
a caller can try each against real lemmas. It is deliberately over-generous:
"knives" yields both "knif" and "knife" because spelling alone cannot choose.
What these tests pin is that the *correct* base form is always among the
candidates, and that the helper never returns the input itself (which the
caller has already tried) or fragments too short to be words.
"""

import unittest

from langtools.en.utils import candidate_base_forms


class TestCandidateBaseForms(unittest.TestCase):
    def test_regular_plural(self) -> None:
        self.assertIn("tomato", candidate_base_forms("tomatoes"))
        self.assertIn("book", candidate_base_forms("books"))

    def test_consonant_y_plural(self) -> None:
        self.assertIn("party", candidate_base_forms("parties"))

    def test_f_plural(self) -> None:
        candidates = candidate_base_forms("knives")
        self.assertIn("knife", candidates)

    def test_sibilant_plural(self) -> None:
        self.assertIn("glass", candidate_base_forms("glasses"))

    def test_third_person_singular(self) -> None:
        self.assertIn("buy", candidate_base_forms("buys"))

    def test_past_tense(self) -> None:
        self.assertIn("want", candidate_base_forms("wanted"))
        self.assertIn("like", candidate_base_forms("liked"))

    def test_past_tense_with_doubled_consonant(self) -> None:
        self.assertIn("stop", candidate_base_forms("stopped"))

    def test_past_tense_of_consonant_y_verb(self) -> None:
        self.assertIn("carry", candidate_base_forms("carried"))

    def test_present_participle(self) -> None:
        self.assertIn("make", candidate_base_forms("making"))
        self.assertIn("go", candidate_base_forms("going"))

    def test_present_participle_with_doubled_consonant(self) -> None:
        self.assertIn("run", candidate_base_forms("running"))

    def test_comparative_and_superlative(self) -> None:
        self.assertIn("big", candidate_base_forms("bigger"))
        self.assertIn("big", candidate_base_forms("biggest"))
        self.assertIn("large", candidate_base_forms("larger"))
        self.assertIn("happy", candidate_base_forms("happiest"))

    def test_never_returns_the_input(self) -> None:
        for word in ("books", "running", "biggest", "carried"):
            self.assertNotIn(word, candidate_base_forms(word))

    def test_no_duplicates(self) -> None:
        for word in ("tomatoes", "knives", "stopped", "running"):
            candidates = candidate_base_forms(word)
            self.assertEqual(len(candidates), len(set(candidates)), word)

    def test_short_words_yield_nothing(self) -> None:
        """Two-letter words have no morphology worth undoing."""
        self.assertEqual(candidate_base_forms("is"), [])
        self.assertEqual(candidate_base_forms("a"), [])

    def test_double_s_is_not_a_plural(self) -> None:
        """ "glass" is not "glas" + s."""
        self.assertNotIn("glas", candidate_base_forms("glass"))

    def test_uninflected_word_yields_no_misleading_candidates(self) -> None:
        self.assertEqual(candidate_base_forms("tomato"), [])


if __name__ == "__main__":
    unittest.main()
