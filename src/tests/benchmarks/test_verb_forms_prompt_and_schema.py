"""Tests for language-specific verb-form prompt text and response schemas."""

import sys
import types

if "pydantic" not in sys.modules:
    sys.modules["pydantic"] = types.SimpleNamespace(BaseModel=object)

# Must precede any generator import; see test_sentence_decomposition_scoring.py.
import benchmarks.lib.utils  # noqa: F401  (import order matters)

from benchmarks.lib.generators.verb_forms_generator import VerbFormsGenerator
from words.verb_forms import build_verb_forms_prompt


class TestVerbFormsPromptAndSchema:
    def setup_method(self):
        # Avoid base initializer side effects; these methods are pure.
        self.generator = VerbFormsGenerator.__new__(VerbFormsGenerator)

    def test_lithuanian_schema_and_prompt_are_default_person_based(self):
        schema = self.generator._response_schema("lt", ["present_active_participle"])
        forms = schema["properties"]["forms"]

        assert forms["required"] == ["present", "past", "future"]
        assert forms["properties"]["present"]["required"] == ["1s", "2s", "3s", "1p", "2p", "3p"]
        assert forms["properties"]["past"]["required"] == ["1s", "2s", "3s", "1p", "2p", "3p"]
        assert forms["properties"]["future"]["required"] == ["1s", "2s", "3s", "1p", "2p", "3p"]

        prompt = build_verb_forms_prompt("lt", "dirbti")
        assert "Additional language-specific guidance" not in prompt
        assert "passé composé" not in prompt
        assert "Swedish verbs do not conjugate by person" not in prompt
        assert "Japanese conjugation categories" not in prompt

    def test_french_schema_and_prompt_include_french_specific_guidance(self):
        schema = self.generator._response_schema("fr", ["present_participle", "past_participle"])
        forms = schema["properties"]["forms"]

        assert forms["required"] == ["present", "imparfait", "passe_compose", "futur_simple"]
        for key in ["present", "imparfait", "passe_compose", "futur_simple"]:
            assert forms["properties"][key]["required"] == ["1s", "2s", "3s", "1p", "2p", "3p"]

        prompt = build_verb_forms_prompt("fr", "être")
        assert "Additional language-specific guidance" in prompt
        assert "include distinct imparfait and passé composé paradigms" in prompt
        assert "Japanese conjugation categories" not in prompt
        assert "Swedish verbs do not conjugate by person" not in prompt

    def test_japanese_schema_and_prompt_use_string_slots_without_persons(self):
        schema = self.generator._response_schema("ja", ["te"])
        forms = schema["properties"]["forms"]

        assert forms["required"] == [
            "dictionary",
            "masu_present",
            "masu_past",
            "nai",
            "te",
            "ta",
            "potential",
            "volitional",
        ]
        for key in forms["required"]:
            assert forms["properties"][key]["type"] == "string"
            assert "required" not in forms["properties"][key]

        prompt = build_verb_forms_prompt("ja", "食べる")
        assert "Additional language-specific guidance" in prompt
        assert "Japanese conjugation categories" in prompt
        assert "passé composé" not in prompt
        assert "Swedish verbs do not conjugate by person" not in prompt
