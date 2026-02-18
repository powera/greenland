#!/usr/bin/python3

"""Unit tests for generic pronoun stripping helpers."""

import unittest

from langtools.pronouns import strip_pronoun, strip_pronoun_or_raise


class TestStripPronoun(unittest.TestCase):
    def test_supported_languages(self) -> None:
        cases = [
            ("fr", "j'ouvre", "ouvre"),
            ("en", "they walk", "walk"),
            ("es", "yo hablo", "hablo"),
            ("lt", "aš einu", "einu"),
            ("it", "io parlo", "parlo"),
            ("kn", "ನಾನು ಬರೆಯುತ್ತೇನೆ", "ಬರೆಯುತ್ತೇನೆ"),
            ("uk", "я пишу", "пишу"),
            ("bn", "আমি লিখি", "লিখি"),
            ("de", "ich gehe", "gehe"),
            ("nl", "ik loop", "loop"),
            ("pt", "eu falo", "falo"),
            ("sv", "jag går", "går"),
            ("zh", "我们学习", "学习"),
        ]
        for language_code, text, expected in cases:
            with self.subTest(language_code=language_code, text=text):
                self.assertEqual(strip_pronoun(language_code, text), expected)

    def test_best_effort_returns_input_when_missing(self) -> None:
        self.assertEqual(strip_pronoun("zz", "foo"), "foo")

    def test_raise_variant_throws_for_missing_language(self) -> None:
        with self.assertRaises(NotImplementedError):
            strip_pronoun_or_raise("zz", "foo")


if __name__ == "__main__":
    unittest.main()
