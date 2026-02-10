#!/usr/bin/env python3

"""Tests to verify langtools form names align with language_forms mappings and GrammaticalForm enum.

This ensures that the form names used in Wiktionary parsing (langtools) are compatible
with the form names used in sentence translation and database storage (language_forms).
"""

import unittest

# Import langtools types
from langtools.lt.types import (
    NounDeclension as LTNounDeclension,
    VerbConjugation as LTVerbConjugation,
    AdjectiveDeclension as LTAdjectiveDeclension,
    AdverbForms as LTAdverbForms,
)
from langtools.de.types import (
    NounDeclension as DENounDeclension,
    VerbConjugation as DEVerbConjugation,
    AdjectiveDeclension as DEAdjectiveDeclension,
    AdverbForms as DEAdverbForms,
)
from langtools.fr.types import (
    NounDeclension as FRNounDeclension,
    VerbConjugation as FRVerbConjugation,
    AdjectiveDeclension as FRAdjectiveDeclension,
    AdverbForms as FRAdverbForms,
)

# Import GrammaticalForm enum directly using importlib to avoid __init__.py chain
import importlib.util
import sys
from pathlib import Path

# Load enums module directly to avoid SQLAlchemy dependency
enums_path = Path(__file__).parent.parent.parent / "storage" / "models" / "enums.py"
spec = importlib.util.spec_from_file_location("enums", enums_path)
if spec and spec.loader:
    enums_module = importlib.util.module_from_spec(spec)
    sys.modules["enums"] = enums_module
    spec.loader.exec_module(enums_module)
    GrammaticalForm = enums_module.GrammaticalForm
else:
    raise ImportError("Could not load enums module")


# Define expected form mappings based on what language_forms uses
# These are the authoritative form names that langtools should match
# (copied from wordfreq/translation/language_forms/*.py to avoid import issues)

LT_NOUN_FORMS = [
    "nominative_singular",
    "genitive_singular",
    "dative_singular",
    "accusative_singular",
    "instrumental_singular",
    "locative_singular",
    "vocative_singular",
    "nominative_plural",
    "genitive_plural",
    "dative_plural",
    "accusative_plural",
    "instrumental_plural",
    "locative_plural",
    "vocative_plural",
]

LT_VERB_FORMS = [
    "1s_present",
    "2s_present",
    "3s_present",
    "1p_present",
    "2p_present",
    "3p_present",
    "1s_past",
    "2s_past",
    "3s_past",
    "1p_past",
    "2p_past",
    "3p_past",
    "1s_future",
    "2s_future",
    "3s_future",
    "1p_future",
    "2p_future",
    "3p_future",
]

LT_ADJECTIVE_FORMS = [
    "nominative_singular_m",
    "genitive_singular_m",
    "dative_singular_m",
    "accusative_singular_m",
    "instrumental_singular_m",
    "locative_singular_m",
    "vocative_singular_m",
    "nominative_singular_f",
    "genitive_singular_f",
    "dative_singular_f",
    "accusative_singular_f",
    "instrumental_singular_f",
    "locative_singular_f",
    "vocative_singular_f",
    "nominative_plural_m",
    "genitive_plural_m",
    "dative_plural_m",
    "accusative_plural_m",
    "instrumental_plural_m",
    "locative_plural_m",
    "vocative_plural_m",
    "nominative_plural_f",
    "genitive_plural_f",
    "dative_plural_f",
    "accusative_plural_f",
    "instrumental_plural_f",
    "locative_plural_f",
    "vocative_plural_f",
]

LT_ADVERB_FORMS = ["positive", "comparative", "superlative"]

DE_NOUN_FORMS = [
    "nominative_singular",
    "accusative_singular",
    "dative_singular",
    "genitive_singular",
    "nominative_plural",
    "accusative_plural",
    "dative_plural",
    "genitive_plural",
]

DE_VERB_FORMS = [
    "1s_present",
    "2s_present",
    "3s_present",
    "1p_present",
    "2p_present",
    "3p_present",
    "1s_past",
    "2s_past",
    "3s_past",
    "1p_past",
    "2p_past",
    "3p_past",
    "1s_future",
    "2s_future",
    "3s_future",
    "1p_future",
    "2p_future",
    "3p_future",
]

DE_ADJECTIVE_FORMS = ["singular_m", "singular_f", "plural_m", "plural_f"]

FR_NOUN_FORMS = ["singular", "plural"]

FR_VERB_FORMS = [
    "1s_present",
    "2s_present",
    "3s_present",
    "1p_present",
    "2p_present",
    "3p_present",
    "1s_impf",
    "2s_impf",
    "3s_impf",
    "1p_impf",
    "2p_impf",
    "3p_impf",
    "1s_future",
    "2s_future",
    "3s_future",
    "1p_future",
    "2p_future",
    "3p_future",
    "pc_m",
    "pc_f",
]

FR_ADJECTIVE_FORMS = ["singular_m", "singular_f", "plural_m", "plural_f"]


class TestLithuanianFormAlignment(unittest.TestCase):
    """Test that Lithuanian langtools forms align with language_forms mappings."""

    def test_noun_forms_match(self) -> None:
        """Langtools noun forms should match language_forms mapping keys."""
        langtools_forms = set(LTNounDeclension.ALL_FORMS)
        expected_forms = set(LT_NOUN_FORMS)

        self.assertEqual(
            langtools_forms,
            expected_forms,
            f"Lithuanian noun form mismatch.\n"
            f"  In langtools but not expected: {langtools_forms - expected_forms}\n"
            f"  Expected but not in langtools: {expected_forms - langtools_forms}",
        )

    def test_verb_forms_match(self) -> None:
        """Langtools verb forms should match language_forms mapping keys."""
        langtools_forms = set(LTVerbConjugation.ALL_FORMS)
        expected_forms = set(LT_VERB_FORMS)

        self.assertEqual(
            langtools_forms,
            expected_forms,
            f"Lithuanian verb form mismatch.\n"
            f"  In langtools but not expected: {langtools_forms - expected_forms}\n"
            f"  Expected but not in langtools: {expected_forms - langtools_forms}",
        )

    def test_adjective_forms_match(self) -> None:
        """Langtools adjective forms should match language_forms mapping keys."""
        langtools_forms = set(LTAdjectiveDeclension.ALL_FORMS)
        expected_forms = set(LT_ADJECTIVE_FORMS)

        self.assertEqual(
            langtools_forms,
            expected_forms,
            f"Lithuanian adjective form mismatch.\n"
            f"  In langtools but not expected: {langtools_forms - expected_forms}\n"
            f"  Expected but not in langtools: {expected_forms - langtools_forms}",
        )

    def test_adverb_forms_match(self) -> None:
        """Langtools adverb forms should match language_forms mapping keys."""
        langtools_forms = set(LTAdverbForms.ALL_FORMS)
        expected_forms = set(LT_ADVERB_FORMS)

        self.assertEqual(
            langtools_forms,
            expected_forms,
            f"Lithuanian adverb form mismatch.\n"
            f"  In langtools but not expected: {langtools_forms - expected_forms}\n"
            f"  Expected but not in langtools: {expected_forms - langtools_forms}",
        )


class TestGermanFormAlignment(unittest.TestCase):
    """Test that German langtools forms align with language_forms mappings."""

    def test_noun_forms_match(self) -> None:
        """Langtools noun forms should match language_forms mapping keys."""
        langtools_forms = set(DENounDeclension.ALL_FORMS)
        expected_forms = set(DE_NOUN_FORMS)

        self.assertEqual(
            langtools_forms,
            expected_forms,
            f"German noun form mismatch.\n"
            f"  In langtools but not expected: {langtools_forms - expected_forms}\n"
            f"  Expected but not in langtools: {expected_forms - langtools_forms}",
        )

    def test_verb_forms_match(self) -> None:
        """Langtools verb forms should match language_forms mapping keys."""
        langtools_forms = set(DEVerbConjugation.ALL_FORMS)
        expected_forms = set(DE_VERB_FORMS)

        self.assertEqual(
            langtools_forms,
            expected_forms,
            f"German verb form mismatch.\n"
            f"  In langtools but not expected: {langtools_forms - expected_forms}\n"
            f"  Expected but not in langtools: {expected_forms - langtools_forms}",
        )

    def test_adjective_forms_match(self) -> None:
        """Langtools adjective forms should match expected GrammaticalForm patterns."""
        langtools_forms = set(DEAdjectiveDeclension.ALL_FORMS)
        expected_forms = set(DE_ADJECTIVE_FORMS)

        self.assertEqual(
            langtools_forms,
            expected_forms,
            f"German adjective form mismatch.\n"
            f"  In langtools but not expected: {langtools_forms - expected_forms}\n"
            f"  Expected but not in langtools: {expected_forms - langtools_forms}",
        )


class TestFrenchFormAlignment(unittest.TestCase):
    """Test that French langtools forms align with language_forms mappings."""

    def test_noun_forms_match(self) -> None:
        """Langtools noun forms should match language_forms mapping keys."""
        langtools_forms = set(FRNounDeclension.ALL_FORMS)
        expected_forms = set(FR_NOUN_FORMS)

        self.assertEqual(
            langtools_forms,
            expected_forms,
            f"French noun form mismatch.\n"
            f"  In langtools but not expected: {langtools_forms - expected_forms}\n"
            f"  Expected but not in langtools: {expected_forms - langtools_forms}",
        )

    def test_verb_forms_match(self) -> None:
        """Langtools verb forms should match language_forms mapping keys."""
        langtools_forms = set(FRVerbConjugation.ALL_FORMS)
        expected_forms = set(FR_VERB_FORMS)

        self.assertEqual(
            langtools_forms,
            expected_forms,
            f"French verb form mismatch.\n"
            f"  In langtools but not expected: {langtools_forms - expected_forms}\n"
            f"  Expected but not in langtools: {expected_forms - langtools_forms}",
        )

    def test_adjective_forms_match(self) -> None:
        """Langtools adjective forms should match expected GrammaticalForm patterns."""
        langtools_forms = set(FRAdjectiveDeclension.ALL_FORMS)
        expected_forms = set(FR_ADJECTIVE_FORMS)

        self.assertEqual(
            langtools_forms,
            expected_forms,
            f"French adjective form mismatch.\n"
            f"  In langtools but not expected: {langtools_forms - expected_forms}\n"
            f"  Expected but not in langtools: {expected_forms - langtools_forms}",
        )


class TestGrammaticalFormEnumConsistency(unittest.TestCase):
    """Test that GrammaticalForm enum values follow consistent naming patterns."""

    def test_verb_form_pattern(self) -> None:
        """Verb enum values should follow pattern: verb/{lang}_{person}_{tense}."""
        verb_forms = [e for e in GrammaticalForm if e.value.startswith("verb/")]

        for form in verb_forms:
            # Skip generic forms
            if form.value in (
                "verb/infinitive",
                "verb/past_participle",
                "verb/present_participle",
                "verb/gerund",
            ):
                continue

            # Should have language code
            value = form.value.replace("verb/", "")
            parts = value.split("_")
            self.assertGreaterEqual(
                len(parts),
                2,
                f"Verb form {form.value} doesn't follow expected pattern",
            )

    def test_noun_form_pattern(self) -> None:
        """Noun enum values should follow pattern: noun/{lang}_{case}_{number}."""
        noun_forms = [e for e in GrammaticalForm if e.value.startswith("noun/")]

        for form in noun_forms:
            # Skip generic forms
            if form.value in (
                "noun/singular",
                "noun/plural",
                "noun/possessive_singular",
                "noun/possessive_plural",
            ):
                continue

            # Should have language code
            value = form.value.replace("noun/", "")
            self.assertIn(
                "_",
                value,
                f"Language-specific noun form {form.value} should have underscore separator",
            )

    def test_adjective_form_pattern(self) -> None:
        """Adjective enum values should follow consistent patterns."""
        adj_forms = [e for e in GrammaticalForm if e.value.startswith("adjective/")]

        for form in adj_forms:
            # Skip generic forms
            if form.value in (
                "adjective/positive",
                "adjective/comparative",
                "adjective/superlative",
            ):
                continue

            # Should have language code
            value = form.value.replace("adjective/", "")
            self.assertIn(
                "_",
                value,
                f"Language-specific adjective form {form.value} should have underscore separator",
            )


if __name__ == "__main__":
    unittest.main()
