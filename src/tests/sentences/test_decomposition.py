"""Tests for shared sentence decomposition helpers."""

from sentences.decomposition import (
    all_words_are_lemmas_or_grammatical,
    build_decomposition_schema,
    build_sentence_decomposition_context,
    build_prompt_for_translate_and_decompose,
    build_sentence_decomposition_prompt,
    build_single_language_decomposition_schema,
    find_unresolved_non_grammatical_words,
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
    assert "de_accusative_singular" not in prompt

    context = build_sentence_decomposition_context()
    assert "de_accusative_singular" in context


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


def test_build_translate_and_decompose_prompt_name_is_available() -> None:
    assert callable(build_prompt_for_translate_and_decompose)


def test_all_words_are_lemmas_or_grammatical_handles_spanish_example() -> None:
    words = [
        {
            "position": 0,
            "role": "pronoun",
            "english_gloss": "they",
            "surface_form": "Ellos",
            "grammatical_form": "pronoun/es_subjective",
            "lemma_guid": "NONE",
            "lemma": "No lemma",
        },
        {
            "position": 1,
            "role": "verb",
            "english_gloss": "bought",
            "surface_form": "compraron",
            "grammatical_form": "verb/es_3p_past",
            "lemma_guid": "V01_001",
            "lemma": "buy",
        },
        {
            "position": 2,
            "role": "noun",
            "english_gloss": "salt",
            "surface_form": "sal",
            "grammatical_form": "noun/es_singular",
            "lemma_guid": "N01_001",
            "lemma": "salt",
        },
        {
            "position": 3,
            "role": "preposition",
            "english_gloss": "in",
            "surface_form": "en",
            "grammatical_form": "preposition/es_base",
            "lemma_guid": "NONE",
            "lemma": "No lemma",
        },
        {
            "position": 4,
            "role": "article",
            "english_gloss": "the",
            "surface_form": "la",
            "grammatical_form": "article/es_singular_f",
            "lemma_guid": "NONE",
            "lemma": "No lemma",
        },
        {
            "position": 5,
            "role": "noun",
            "english_gloss": "store",
            "surface_form": "tienda",
            "grammatical_form": "noun/es_singular",
            "lemma_guid": "N01_002",
            "lemma": "store",
        },
    ]

    assert all_words_are_lemmas_or_grammatical(words, "es")
    assert find_unresolved_non_grammatical_words(words, "es") == []


def test_find_unresolved_non_grammatical_words_flags_missing_lemma_content_words() -> None:
    words = [
        {
            "position": 0,
            "role": "noun",
            "english_gloss": "store",
            "surface_form": "tienda",
            "grammatical_form": "noun/es_singular",
            "lemma_guid": "NONE",
            "lemma": "No lemma",
        },
        {
            "position": 1,
            "role": "article",
            "english_gloss": "the",
            "surface_form": "la",
            "grammatical_form": "article/es_singular_f",
            "lemma_guid": "NONE",
            "lemma": "No lemma",
        },
    ]

    unresolved = find_unresolved_non_grammatical_words(words, "es")

    assert len(unresolved) == 1
    assert unresolved[0]["surface_form"] == "tienda"
    assert not all_words_are_lemmas_or_grammatical(words, "es")


def test_negative_case_spanish_fair_without_lemma_fails_check() -> None:
    words = [
        {
            "position": 0,
            "role": "verb",
            "english_gloss": "saw",
            "surface_form": "Vimos",
            "grammatical_form": "verb/es_past",
            "lemma_guid": "V10_001",
            "lemma": "see",
        },
        {
            "position": 1,
            "role": "article",
            "english_gloss": "a",
            "surface_form": "un",
            "grammatical_form": "article/base",
            "lemma_guid": "NONE",
            "lemma": "No lemma",
        },
        {
            "position": 2,
            "role": "object",
            "english_gloss": "pig",
            "surface_form": "cerdo",
            "grammatical_form": "noun/es_singular",
            "lemma_guid": "N22_001",
            "lemma": "pig",
        },
        {
            "position": 3,
            "role": "preposition",
            "english_gloss": "at",
            "surface_form": "en",
            "grammatical_form": "preposition/base",
            "lemma_guid": "NONE",
            "lemma": "No lemma",
        },
        {
            "position": 4,
            "role": "article",
            "english_gloss": "the",
            "surface_form": "la",
            "grammatical_form": "article/base",
            "lemma_guid": "NONE",
            "lemma": "No lemma",
        },
        {
            "position": 5,
            "role": "object_of_preposition",
            "english_gloss": "fair",
            "surface_form": "feria",
            "grammatical_form": "noun/es_singular",
            "lemma_guid": "NONE",
            "lemma": "No lemma",
        },
    ]

    unresolved = find_unresolved_non_grammatical_words(words, "es")

    assert len(unresolved) == 1
    assert unresolved[0]["surface_form"] == "feria"
    assert not all_words_are_lemmas_or_grammatical(words, "es")
