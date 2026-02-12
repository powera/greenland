#!/usr/bin/env python3

"""Tests for English verb conjugation expansion (langtools.en.conjugation)."""

import unittest

from langtools.en.conjugation import IRREGULAR_CONJUGATIONS, expand_verb_forms

# Expected keys matching VERB_FORM_MAPPING in langtools.en.llm_forms.
# Defined here to avoid importing llm_forms (which pulls in storage/sqlalchemy).
EXPECTED_VERB_FORM_KEYS = {
    "infinitive",
    "present_participle",
    "past_participle",
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
    "2s_imp",
    "2p_imp",
}


class TestExpandVerbFormsRegular(unittest.TestCase):
    """Test expansion of regular English verbs."""

    def test_walk_all_forms(self) -> None:
        """A completely regular verb should produce all 23 keys."""
        base = {
            "infinitive": "walk",
            "3s_present": "walks",
            "past": "walked",
            "past_participle": "walked",
            "present_participle": "walking",
        }
        result = expand_verb_forms(base)

        # Present tense
        self.assertEqual(result["1s_present"], "walk")
        self.assertEqual(result["2s_present"], "walk")
        self.assertEqual(result["3s_present"], "walks")
        self.assertEqual(result["1p_present"], "walk")
        self.assertEqual(result["2p_present"], "walk")
        self.assertEqual(result["3p_present"], "walk")

        # Past tense - all same
        for person in ("1s", "2s", "3s", "1p", "2p", "3p"):
            self.assertEqual(result[f"{person}_past"], "walked")

        # Future tense - will + infinitive
        for person in ("1s", "2s", "3s", "1p", "2p", "3p"):
            self.assertEqual(result[f"{person}_future"], "will walk")

        # Imperatives
        self.assertEqual(result["2s_imp"], "walk")
        self.assertEqual(result["2p_imp"], "walk")

        # Participles & infinitive
        self.assertEqual(result["infinitive"], "walk")
        self.assertEqual(result["present_participle"], "walking")
        self.assertEqual(result["past_participle"], "walked")

    def test_go_irregular_base_forms(self) -> None:
        """'go' is irregular in its base forms but regular in person-inflection."""
        base = {
            "infinitive": "go",
            "3s_present": "goes",
            "past": "went",
            "past_participle": "gone",
            "present_participle": "going",
        }
        result = expand_verb_forms(base)

        self.assertEqual(result["1s_present"], "go")
        self.assertEqual(result["3s_present"], "goes")
        self.assertEqual(result["1s_past"], "went")
        self.assertEqual(result["3s_past"], "went")
        self.assertEqual(result["past_participle"], "gone")
        self.assertEqual(result["1s_future"], "will go")

    def test_have(self) -> None:
        """'have' has irregular 3s but regular person-inflection otherwise."""
        base = {
            "infinitive": "have",
            "3s_present": "has",
            "past": "had",
            "past_participle": "had",
            "present_participle": "having",
        }
        result = expand_verb_forms(base)

        self.assertEqual(result["1s_present"], "have")
        self.assertEqual(result["3s_present"], "has")
        self.assertEqual(result["2p_present"], "have")
        # Past is uniform
        self.assertEqual(result["1s_past"], "had")
        self.assertEqual(result["3s_past"], "had")

    def test_eat_distinct_past_participle(self) -> None:
        """Verbs where past != past_participle."""
        base = {
            "infinitive": "eat",
            "3s_present": "eats",
            "past": "ate",
            "past_participle": "eaten",
            "present_participle": "eating",
        }
        result = expand_verb_forms(base)

        self.assertEqual(result["1s_past"], "ate")
        self.assertEqual(result["past_participle"], "eaten")
        self.assertEqual(result["1s_future"], "will eat")

    def test_total_form_count(self) -> None:
        """A regular verb with all base forms should produce 23 keys."""
        base = {
            "infinitive": "talk",
            "3s_present": "talks",
            "past": "talked",
            "past_participle": "talked",
            "present_participle": "talking",
        }
        result = expand_verb_forms(base)
        self.assertEqual(len(result), 23)

    def test_infinitive_override(self) -> None:
        """The infinitive_override parameter should take precedence."""
        base = {
            "3s_present": "runs",
            "past": "ran",
            "past_participle": "run",
            "present_participle": "running",
        }
        result = expand_verb_forms(base, infinitive_override="run")

        self.assertEqual(result["infinitive"], "run")
        self.assertEqual(result["1s_present"], "run")
        self.assertEqual(result["3s_present"], "runs")
        self.assertEqual(result["1s_future"], "will run")


class TestExpandVerbFormsBe(unittest.TestCase):
    """Test that 'be' is handled via the irregular table."""

    def test_be_present(self) -> None:
        base = {
            "infinitive": "be",
            "3s_present": "is",
            "past": "was",
            "past_participle": "been",
            "present_participle": "being",
        }
        result = expand_verb_forms(base)

        self.assertEqual(result["1s_present"], "am")
        self.assertEqual(result["2s_present"], "are")
        self.assertEqual(result["3s_present"], "is")
        self.assertEqual(result["1p_present"], "are")
        self.assertEqual(result["2p_present"], "are")
        self.assertEqual(result["3p_present"], "are")

    def test_be_past(self) -> None:
        base = {"infinitive": "be"}
        result = expand_verb_forms(base)

        self.assertEqual(result["1s_past"], "was")
        self.assertEqual(result["2s_past"], "were")
        self.assertEqual(result["3s_past"], "was")
        self.assertEqual(result["1p_past"], "were")
        self.assertEqual(result["2p_past"], "were")
        self.assertEqual(result["3p_past"], "were")

    def test_be_future(self) -> None:
        base = {"infinitive": "be"}
        result = expand_verb_forms(base)

        for person in ("1s", "2s", "3s", "1p", "2p", "3p"):
            self.assertEqual(result[f"{person}_future"], "will be")

    def test_be_imperative(self) -> None:
        base = {"infinitive": "be"}
        result = expand_verb_forms(base)

        self.assertEqual(result["2s_imp"], "be")
        self.assertEqual(result["2p_imp"], "be")

    def test_be_participles(self) -> None:
        base = {"infinitive": "be"}
        result = expand_verb_forms(base)

        self.assertEqual(result["present_participle"], "being")
        self.assertEqual(result["past_participle"], "been")

    def test_be_total_forms(self) -> None:
        """'be' should produce all 23 keys."""
        base = {"infinitive": "be"}
        result = expand_verb_forms(base)
        self.assertEqual(len(result), 23)


class TestExpandVerbFormsMissingBase(unittest.TestCase):
    """Test graceful handling of missing base forms."""

    def test_empty_dict(self) -> None:
        result = expand_verb_forms({})
        self.assertEqual(result, {})

    def test_only_infinitive(self) -> None:
        """With only the infinitive, we can still produce present, future, imperative."""
        result = expand_verb_forms({"infinitive": "play"})

        self.assertEqual(result["infinitive"], "play")
        self.assertEqual(result["1s_present"], "play")
        self.assertEqual(result["1s_future"], "will play")
        self.assertEqual(result["2s_imp"], "play")
        # But no past or participles
        self.assertNotIn("1s_past", result)
        self.assertNotIn("present_participle", result)
        self.assertNotIn("past_participle", result)
        # No 3s_present without that base form
        self.assertNotIn("3s_present", result)

    def test_only_past(self) -> None:
        """With only past, we get all past-tense person forms."""
        result = expand_verb_forms({"past": "jumped"})

        self.assertEqual(result["1s_past"], "jumped")
        self.assertEqual(result["3p_past"], "jumped")
        self.assertNotIn("1s_present", result)
        self.assertNotIn("infinitive", result)

    def test_empty_string_values_ignored(self) -> None:
        """Empty strings should not produce forms."""
        base = {
            "infinitive": "play",
            "3s_present": "",
            "past": "played",
            "past_participle": "",
            "present_participle": "playing",
        }
        result = expand_verb_forms(base)

        self.assertNotIn("3s_present", result)
        self.assertNotIn("past_participle", result)
        self.assertIn("1s_present", result)
        self.assertIn("present_participle", result)


class TestExpandVerbFormsAlignment(unittest.TestCase):
    """Verify that expanded keys match VERB_FORM_MAPPING keys."""

    def test_keys_subset_of_form_mapping(self) -> None:
        """All keys produced by expand_verb_forms should be valid VERB_FORM_MAPPING keys."""
        base = {
            "infinitive": "walk",
            "3s_present": "walks",
            "past": "walked",
            "past_participle": "walked",
            "present_participle": "walking",
        }
        result = expand_verb_forms(base)

        for key in result:
            self.assertIn(
                key,
                EXPECTED_VERB_FORM_KEYS,
                f"Expanded key '{key}' not found in VERB_FORM_MAPPING",
            )

    def test_all_form_mapping_keys_produced(self) -> None:
        """A complete expansion should cover every key in VERB_FORM_MAPPING."""
        base = {
            "infinitive": "walk",
            "3s_present": "walks",
            "past": "walked",
            "past_participle": "walked",
            "present_participle": "walking",
        }
        result = expand_verb_forms(base)

        for key in EXPECTED_VERB_FORM_KEYS:
            self.assertIn(
                key,
                result,
                f"VERB_FORM_MAPPING key '{key}' missing from expanded result",
            )


class TestIrregularConjugationsData(unittest.TestCase):
    """Validate the IRREGULAR_CONJUGATIONS data itself."""

    def test_be_has_all_form_mapping_keys(self) -> None:
        be_forms = IRREGULAR_CONJUGATIONS["be"]
        for key in EXPECTED_VERB_FORM_KEYS:
            self.assertIn(
                key,
                be_forms,
                f"'be' irregular data missing VERB_FORM_MAPPING key '{key}'",
            )

    def test_be_no_empty_values(self) -> None:
        for key, value in IRREGULAR_CONJUGATIONS["be"].items():
            self.assertTrue(value.strip(), f"'be' has empty value for key '{key}'")


if __name__ == "__main__":
    unittest.main()
