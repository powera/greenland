#!/usr/bin/env python3

"""Tests for the atacama export's stopword section.

Stopwords (the/as/not, don't, isn't, we're, ...) are emitted into the export's
``_stopwords`` section so the atacama-powera annotator token-matches them in the
output. They are flagged and not processed further: no GUID, no translations, no
Lemma table entry. Each carries a ``pos`` and a ``lemma`` display headword -
"I" for "me", the expansion "do not" for "don't".

The table is derived from the langtools English registry
(ENGLISH_STOPWORD_ANNOTATIONS). It previously came from a hand-maintained
data/release/stopwords/en.jsonl that had drifted to 58 words, missing every
conjunction, determiner, interrogative and particle in the registry; these tests
pin the registry as the source of truth so that cannot recur.
"""

import unittest

from atacama.export_atacama import AtacamaExporter
from langtools.en.grammatical_words import (
    ENGLISH_ALL_TIERS,
    ENGLISH_CONTRACTION_ANNOTATIONS,
    ENGLISH_STOPWORD_ANNOTATIONS,
)


class ContractionTableTest(unittest.TestCase):
    """ENGLISH_CONTRACTION_ANNOTATIONS must be well-formed for the export."""

    def test_keys_are_lowercase(self) -> None:
        for key in ENGLISH_CONTRACTION_ANNOTATIONS:
            self.assertEqual(key, key.lower(), f"contraction key not lowercase: {key!r}")

    def test_pos_uses_known_categories(self) -> None:
        for key, annotation in ENGLISH_CONTRACTION_ANNOTATIONS.items():
            self.assertIn(
                annotation.pos,
                ("verb", "pronoun"),
                f"unexpected pos for {key!r}: {annotation.pos!r}",
            )

    def test_every_contraction_has_an_expansion(self) -> None:
        for key, annotation in ENGLISH_CONTRACTION_ANNOTATIONS.items():
            self.assertTrue(annotation.expansion, f"{key!r} has no expansion")
            self.assertNotIn("'", annotation.expansion, f"{key!r} expansion still contracted")

    def test_common_contractions_present(self) -> None:
        for key in ("don't", "isn't", "can't", "won't", "i'm", "we're", "it's", "let's"):
            self.assertIn(key, ENGLISH_CONTRACTION_ANNOTATIONS)


class StopwordAnnotationTest(unittest.TestCase):
    """ENGLISH_STOPWORD_ANNOTATIONS must cover the whole registry."""

    def test_covers_every_registry_word(self) -> None:
        missing = sorted(
            w for w in ENGLISH_ALL_TIERS if w.lower() not in ENGLISH_STOPWORD_ANNOTATIONS
        )
        self.assertEqual(missing, [], f"registry words with no annotation: {missing}")

    def test_covers_every_contraction(self) -> None:
        missing = sorted(
            w for w in ENGLISH_CONTRACTION_ANNOTATIONS if w not in ENGLISH_STOPWORD_ANNOTATIONS
        )
        self.assertEqual(missing, [], f"contractions with no annotation: {missing}")

    def test_keys_are_lowercase(self) -> None:
        for key in ENGLISH_STOPWORD_ANNOTATIONS:
            self.assertEqual(key, key.lower(), f"stopword key not lowercase: {key!r}")

    def test_each_entry_has_pos_and_lemma(self) -> None:
        for key, annotation in ENGLISH_STOPWORD_ANNOTATIONS.items():
            self.assertEqual(
                set(annotation), {"pos", "lemma"}, f"{key!r} must have exactly pos+lemma"
            )
            self.assertTrue(annotation["pos"], f"{key!r} has empty pos")
            self.assertTrue(annotation["lemma"], f"{key!r} has empty lemma")

    def test_conjunctions_are_annotated(self) -> None:
        # The original bug: the curated file had no conjunction section at all,
        # so "as" and every other conjunction went unannotated.
        for word in ("as", "and", "but", "if", "or", "because", "while", "than"):
            self.assertEqual(
                ENGLISH_STOPWORD_ANNOTATIONS[word]["pos"],
                "conjunction",
                f"{word!r} should be a conjunction",
            )

    def test_other_missing_categories_are_annotated(self) -> None:
        for word, pos in (
            ("not", "particle"),
            ("never", "particle"),
            ("this", "determiner"),
            ("each", "determiner"),
            ("who", "pronoun"),
            ("whose", "pronoun"),
            ("to", "preposition"),
            ("cannot", "auxiliary_verb"),
        ):
            self.assertEqual(
                ENGLISH_STOPWORD_ANNOTATIONS[word]["pos"], pos, f"wrong pos for {word!r}"
            )

    def test_display_headwords_group_inflections(self) -> None:
        # These groupings were the curated file's real contribution; they must
        # survive the move into langtools.
        for word, headword in (
            ("me", "I"),
            ("my", "I"),
            ("was", "be"),
            ("been", "be"),
            ("could", "can"),
            ("an", "a"),
            ("them", "they"),
            ("his", "he"),
        ):
            self.assertEqual(
                ENGLISH_STOPWORD_ANNOTATIONS[word]["lemma"],
                headword,
                f"{word!r} should display as {headword!r}",
            )

    def test_contraction_lemma_is_the_expansion(self) -> None:
        self.assertEqual(ENGLISH_STOPWORD_ANNOTATIONS["don't"]["lemma"], "do not")
        self.assertEqual(ENGLISH_STOPWORD_ANNOTATIONS["we're"]["lemma"], "we are")


class LoadStopwordsTest(unittest.TestCase):
    """_load_stopwords returns the registry table, independent of any data file."""

    def test_returns_registry_annotations(self) -> None:
        result = AtacamaExporter()._load_stopwords()
        self.assertEqual(result, dict(ENGLISH_STOPWORD_ANNOTATIONS))

    def test_includes_conjunctions_and_contractions(self) -> None:
        result = AtacamaExporter()._load_stopwords()
        self.assertEqual(result["as"], {"pos": "conjunction", "lemma": "as"})
        self.assertEqual(result["don't"], {"pos": "verb", "lemma": "do not"})

    def test_result_is_a_copy(self) -> None:
        # Callers embed this in the export dict; mutating it must not corrupt
        # the module-level registry table.
        result = AtacamaExporter()._load_stopwords()
        result["as"]["pos"] = "mutated"
        self.assertEqual(ENGLISH_STOPWORD_ANNOTATIONS["as"]["pos"], "conjunction")


if __name__ == "__main__":
    unittest.main()
