#!/usr/bin/python3

"""Unit tests for Japanese script analysis (word-level kanji signal)."""

import unittest

from langtools.ja.script_analysis import (
    JapaneseScriptType,
    classify_japanese_script,
    contains_japanese,
    has_hiragana,
    has_kanji,
    has_katakana,
    kanji_ratio,
)


class TestHasKanji(unittest.TestCase):
    def test_kanji_detection(self) -> None:
        cases = [
            ("学校", True),  # all kanji
            ("食べる", True),  # kanji + okurigana (only part kanji)
            ("人々", True),  # kanji with iteration mark
            ("パン", False),  # katakana loanword
            ("が", False),  # hiragana particle
            ("コーヒー", False),  # katakana with prolonged sound mark
            ("", False),
            ("romaji", False),
            ("123", False),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(has_kanji(text), expected)


class TestKanaDetection(unittest.TestCase):
    def test_hiragana_and_katakana(self) -> None:
        self.assertTrue(has_hiragana("食べる"))
        self.assertFalse(has_hiragana("パン"))
        self.assertTrue(has_katakana("パン"))
        self.assertTrue(has_katakana("コーヒー"))  # prolonged sound mark counts
        self.assertFalse(has_katakana("食べる"))

    def test_contains_japanese(self) -> None:
        self.assertTrue(contains_japanese("学校"))
        self.assertTrue(contains_japanese("パン"))
        self.assertTrue(contains_japanese("が"))
        self.assertFalse(contains_japanese(""))
        self.assertFalse(contains_japanese("hello"))


class TestClassifyJapaneseScript(unittest.TestCase):
    def test_categories(self) -> None:
        cases = [
            ("学校", JapaneseScriptType.KANJI),
            ("漢字", JapaneseScriptType.KANJI),
            ("人々", JapaneseScriptType.KANJI),  # iteration mark is kanji-like
            ("食べる", JapaneseScriptType.MIXED),
            ("大きい", JapaneseScriptType.MIXED),
            ("パン", JapaneseScriptType.KATAKANA),
            ("コーヒー", JapaneseScriptType.KATAKANA),
            ("が", JapaneseScriptType.HIRAGANA),
            ("です", JapaneseScriptType.HIRAGANA),
            ("オーケーだ", JapaneseScriptType.KANA),  # katakana + hiragana, no kanji
            ("", JapaneseScriptType.NONE),
            ("romaji", JapaneseScriptType.NONE),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(classify_japanese_script(text), expected)

    def test_has_kanji_property(self) -> None:
        self.assertTrue(JapaneseScriptType.KANJI.has_kanji)
        self.assertTrue(JapaneseScriptType.MIXED.has_kanji)
        self.assertFalse(JapaneseScriptType.KATAKANA.has_kanji)
        self.assertFalse(JapaneseScriptType.HIRAGANA.has_kanji)
        self.assertFalse(JapaneseScriptType.KANA.has_kanji)
        self.assertFalse(JapaneseScriptType.NONE.has_kanji)


class TestKanjiRatio(unittest.TestCase):
    def test_ratio(self) -> None:
        self.assertEqual(kanji_ratio("学校"), 1.0)
        self.assertEqual(kanji_ratio("パン"), 0.0)
        self.assertEqual(kanji_ratio(""), 0.0)
        self.assertEqual(kanji_ratio("romaji"), 0.0)
        # 食べる: one kanji out of three Japanese characters.
        self.assertAlmostEqual(kanji_ratio("食べる"), 1 / 3)
        # Punctuation and Latin are ignored in the denominator.
        self.assertEqual(kanji_ratio("学校。"), 1.0)


if __name__ == "__main__":
    unittest.main()
