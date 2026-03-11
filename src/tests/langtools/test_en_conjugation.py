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
        """'have' uses the irregular table for its 3s_present 'has'."""
        base = {"infinitive": "have", "past": "had", "past_participle": "had"}
        result = expand_verb_forms(base)

        self.assertEqual(result["1s_present"], "have")
        self.assertEqual(result["3s_present"], "has")
        self.assertEqual(result["2p_present"], "have")
        self.assertEqual(result["present_participle"], "having")
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
        """With only the infinitive, all forms are generated mechanically."""
        result = expand_verb_forms({"infinitive": "play"})

        self.assertEqual(result["infinitive"], "play")
        self.assertEqual(result["1s_present"], "play")
        self.assertEqual(result["1s_future"], "will play")
        self.assertEqual(result["2s_imp"], "play")
        # Auto-generated from infinitive
        self.assertEqual(result["3s_present"], "plays")
        self.assertEqual(result["present_participle"], "playing")
        # Past and past_participle are now auto-generated from infinitive
        self.assertEqual(result["1s_past"], "played")
        self.assertEqual(result["past_participle"], "played")

    def test_only_past(self) -> None:
        """With only past, we get all past-tense person forms."""
        result = expand_verb_forms({"past": "jumped"})

        self.assertEqual(result["1s_past"], "jumped")
        self.assertEqual(result["3p_past"], "jumped")
        self.assertNotIn("1s_present", result)
        self.assertNotIn("infinitive", result)

    def test_empty_string_values_auto_generated(self) -> None:
        """Empty 3s_present / present_participle are auto-generated from infinitive."""
        base = {
            "infinitive": "play",
            "3s_present": "",
            "past": "played",
            "past_participle": "",
            "present_participle": "",
        }
        result = expand_verb_forms(base)

        # Auto-generated from infinitive
        self.assertEqual(result["3s_present"], "plays")
        self.assertEqual(result["present_participle"], "playing")
        # past_participle is now derived from past when past is provided
        self.assertEqual(result["past_participle"], "played")
        self.assertIn("1s_present", result)


class TestAutoGenerationFromInfinitive(unittest.TestCase):
    """Test that 3s_present and present_participle are generated when missing."""

    def test_3s_present_generated(self) -> None:
        """When 3s_present is omitted, it is derived from the infinitive."""
        base = {"infinitive": "watch", "past": "watched", "past_participle": "watched"}
        result = expand_verb_forms(base)
        self.assertEqual(result["3s_present"], "watches")

    def test_present_participle_generated(self) -> None:
        """When present_participle is omitted, it is derived from the infinitive."""
        base = {"infinitive": "run", "past": "ran", "past_participle": "run"}
        result = expand_verb_forms(base)
        self.assertEqual(result["present_participle"], "running")

    def test_explicit_overrides_auto(self) -> None:
        """Explicitly supplied 3s_present / present_participle take precedence."""
        base = {
            "infinitive": "go",
            "3s_present": "goes",
            "past": "went",
            "past_participle": "gone",
            "present_participle": "going",
        }
        result = expand_verb_forms(base)
        # Should use the explicit values, not the auto-generated ones
        self.assertEqual(result["3s_present"], "goes")
        self.assertEqual(result["present_participle"], "going")

    def test_three_forms_produce_full_table(self) -> None:
        """Just infinitive + past + past_participle should produce all 23 keys."""
        base = {"infinitive": "talk", "past": "talked", "past_participle": "talked"}
        result = expand_verb_forms(base)
        self.assertEqual(len(result), 23)
        self.assertEqual(result["3s_present"], "talks")
        self.assertEqual(result["present_participle"], "talking")

    def test_try_generates_correct_3s(self) -> None:
        """Consonant+y verbs: try -> tries, not trys."""
        base = {"infinitive": "try", "past": "tried", "past_participle": "tried"}
        result = expand_verb_forms(base)
        self.assertEqual(result["3s_present"], "tries")
        self.assertEqual(result["present_participle"], "trying")


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

    def test_have_has_all_form_mapping_keys(self) -> None:
        have_forms = IRREGULAR_CONJUGATIONS["have"]
        for key in EXPECTED_VERB_FORM_KEYS:
            self.assertIn(
                key,
                have_forms,
                f"'have' irregular data missing VERB_FORM_MAPPING key '{key}'",
            )

    def test_have_3s_present_is_has(self) -> None:
        self.assertEqual(IRREGULAR_CONJUGATIONS["have"]["3s_present"], "has")

    def test_have_no_empty_values(self) -> None:
        for key, value in IRREGULAR_CONJUGATIONS["have"].items():
            self.assertTrue(value.strip(), f"'have' has empty value for key '{key}'")


if __name__ == "__main__":
    unittest.main()
