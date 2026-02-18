"""Tests for word translation prompt and schema helpers."""

from words.translation import build_single_target_translation_prompt


def test_single_target_prompt_contains_expected_phrases_and_schema():
    context, prompt, schema = build_single_target_translation_prompt(
        source_word="cat",
        source_language="en",
        target_language="fr",
        candidate_translations=["chat", "chien", "maison"],
    )

    assert "multilingual translation expert" in context
    assert 'Translate the single word "cat"' in prompt
    assert "Return only one translation in lemma/base form." in prompt
    assert "choose exactly one candidate" in prompt
    assert "Candidate translations:" in prompt
    assert "- chat" in prompt
    assert "- chien" in prompt

    assert schema["type"] == "object"
    assert schema["required"] == ["translation"]
    assert "translation" in schema["properties"]
    translation_field = schema["properties"]["translation"]
    assert translation_field["type"] == "string"
    assert "Single-word translation" in translation_field["description"]
