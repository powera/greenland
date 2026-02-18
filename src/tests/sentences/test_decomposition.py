"""Tests for shared sentence decomposition helpers."""

from sentences.decomposition import (
    build_decomposition_schema,
    build_sentence_decomposition_prompt,
    build_single_language_decomposition_schema,
)


def test_build_sentence_decomposition_prompt_includes_core_sections() -> None:
    prompt = build_sentence_decomposition_prompt(
        source_sentence="I read a book",
        source_language="en",
        target_language="es",
        target_translation="Leo un libro",
        helper_translations=[{"language_code": "fr", "translation": "Je lis un livre"}],
        candidate_lemmas=[
            {
                "guid": "V01_001",
                "lemma": "read",
                "disambiguation": "consume text",
                "pos": "verb",
                "definition": "look at and comprehend writing",
                "translations": {"en": "read", "es": "leer", "fr": "lire", "de": "lesen"},
            }
        ],
    )

    assert "Target language: es" in prompt
    assert 'Target translation: "Leo un libro"' in prompt
    assert "Candidate lemmas" in prompt
    assert "lemma_guid=NONE" in prompt
    assert "de_accusative_singular" in prompt


def test_build_decomposition_schema_has_words_for_target_languages() -> None:
    schema = build_decomposition_schema(target_languages=["lt", "es"], include_english=False)

    assert "lt" in schema["properties"]
    assert "words_lt" in schema["properties"]
    assert "es" in schema["properties"]
    assert "words_es" in schema["properties"]
    assert "en" not in schema["properties"]


def test_build_single_language_schema_limits_languages_to_one() -> None:
    schema = build_single_language_decomposition_schema()

    assert schema["properties"]["languages"]["minItems"] == 1
    assert schema["properties"]["languages"]["maxItems"] == 1
