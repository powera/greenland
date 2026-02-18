#!/usr/bin/python3

"""Unit tests for French utility functions."""

import unittest

from langtools.fr.utils import strip_subject_pronoun


class TestStripSubjectPronoun(unittest.TestCase):
    def test_simple_pronouns(self) -> None:
        self.assertEqual(strip_subject_pronoun("je mange"), "mange")
        self.assertEqual(strip_subject_pronoun("tu manges"), "manges")
        self.assertEqual(strip_subject_pronoun("il mange"), "mange")
        self.assertEqual(strip_subject_pronoun("elle mange"), "mange")
        self.assertEqual(strip_subject_pronoun("on mange"), "mange")
        self.assertEqual(strip_subject_pronoun("nous mangeons"), "mangeons")
        self.assertEqual(strip_subject_pronoun("vous mangez"), "mangez")
        self.assertEqual(strip_subject_pronoun("ils mangent"), "mangent")
        self.assertEqual(strip_subject_pronoun("elles mangent"), "mangent")

    def test_elided_j(self) -> None:
        self.assertEqual(strip_subject_pronoun("j'ouvre"), "ouvre")
        self.assertEqual(strip_subject_pronoun("j'ai ouvert"), "ai ouvert")

    def test_elided_j_curly_apostrophe(self) -> None:
        self.assertEqual(strip_subject_pronoun("j\u2019ouvre"), "ouvre")

    def test_combined_pronouns(self) -> None:
        self.assertEqual(strip_subject_pronoun("ils/elles mangent"), "mangent")
        self.assertEqual(strip_subject_pronoun("il/elle mange"), "mange")
        self.assertEqual(strip_subject_pronoun("il/elle/on aura"), "aura")

    def test_bare_verb_unchanged(self) -> None:
        self.assertEqual(strip_subject_pronoun("mange"), "mange")
        self.assertEqual(strip_subject_pronoun("ouvre"), "ouvre")

    def test_case_insensitive(self) -> None:
        self.assertEqual(strip_subject_pronoun("Je mange"), "mange")
        self.assertEqual(strip_subject_pronoun("J'ouvre"), "ouvre")
        self.assertEqual(strip_subject_pronoun("Nous mangeons"), "mangeons")

    def test_whitespace_handling(self) -> None:
        self.assertEqual(strip_subject_pronoun("  je mange  "), "mange")
        self.assertEqual(strip_subject_pronoun(""), "")
        self.assertEqual(strip_subject_pronoun("   "), "")

    def test_compound_past_tense(self) -> None:
        self.assertEqual(strip_subject_pronoun("nous avons mangé"), "avons mangé")
        self.assertEqual(strip_subject_pronoun("ils ont ouvert"), "ont ouvert")

    def test_elles_before_elle(self) -> None:
        """Ensure 'elles' is matched before 'elle'."""
        self.assertEqual(strip_subject_pronoun("elles sont"), "sont")


if __name__ == "__main__":
    unittest.main()
