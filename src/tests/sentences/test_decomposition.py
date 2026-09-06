"""Tests for shared sentence decomposition helpers."""

from typing import Any, Dict

from sentences.decomposition import (
    all_words_are_lemmas_or_grammatical,
    build_decomposed_word_schema,
    build_decomposition_schema,
    build_multi_language_decomposition_schema,
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

    assert "Target language: Spanish (es)" in prompt
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


def test_all_schema_builders_share_one_word_shape() -> None:
    """Every decomposition path must describe a word identically.

    The shapes previously drifted (surface_form/english_gloss/lemma_guid vs
    word/english/guid), which needed adapters to reconcile and silently
    dropped fields when one was missed. Adding a per-word field should mean
    editing build_decomposed_word_schema alone; this test fails if a caller
    starts inlining its own copy again.
    """
    from verbalator.actions.decomposition import DecompositionAction

    canonical = build_decomposed_word_schema()

    single = build_single_language_decomposition_schema()
    single_word = single["properties"]["languages"]["items"]["properties"]["words"]["items"]

    multi = build_multi_language_decomposition_schema(target_languages=["lt"])
    multi_word = multi["properties"]["words_lt"]["items"]

    legacy = build_decomposition_schema(target_languages=["lt"], include_english=False)
    legacy_word = legacy["properties"]["words_lt"]["items"]

    verbalator = DecompositionAction().build_schema()
    verbalator_word = verbalator["properties"]["languages"]["items"]["properties"]["words"]["items"]

    for word_schema in (single_word, multi_word, legacy_word, verbalator_word):
        assert word_schema["properties"] == canonical["properties"]
        assert sorted(word_schema["required"]) == sorted(canonical["required"])


def test_canonical_word_schema_uses_phase3_field_names() -> None:
    """The legacy word/english/guid names must not come back."""
    properties = build_decomposed_word_schema()["properties"]

    assert {"surface_form", "english_gloss", "lemma_guid"} <= set(properties)
    assert not {"word", "english", "guid"} & set(properties)


def test_build_single_language_schema_limits_languages_to_one() -> None:
    schema = build_single_language_decomposition_schema()

    assert schema["properties"]["languages"]["minItems"] == 1
    assert schema["properties"]["languages"]["maxItems"] == 1


def test_build_translate_and_decompose_prompt_name_is_available() -> None:
    assert callable(build_prompt_for_translate_and_decompose)


def test_translate_and_decompose_prompt_renders_candidate_lemmas() -> None:
    """candidate_lemmas kwarg should render a dedicated block in the prompt."""
    from sqlalchemy.orm import Session

    from storage.models.schema import Lemma
    from tests.sentences.candidate_lookup_fixture import (
        add_test_sentence,
        build_test_engine,
        seed_test_database,
    )

    engine = build_test_engine()
    session = Session(engine)
    try:
        seed_test_database(session)
        sentence = add_test_sentence(session, {"en": "I can see him"})

        can_modal = session.query(Lemma).filter_by(guid="TEST_CAN_MODAL").first()
        can_container = session.query(Lemma).filter_by(guid="TEST_CAN_CONTAINER").first()
        assert can_modal is not None and can_container is not None

        _, prompt_with = build_prompt_for_translate_and_decompose(
            sentence,
            ["fr", "es"],
            session,
            source_language="en",
            candidate_lemmas=[can_modal, can_container],
        )
        _, prompt_without = build_prompt_for_translate_and_decompose(
            sentence,
            ["fr", "es"],
            session,
            source_language="en",
        )

        assert "TEST_CAN_MODAL" in prompt_with
        assert "TEST_CAN_CONTAINER" in prompt_with
        assert "(modal)" in prompt_with
        assert "fr=pouvoir" in prompt_with

        assert "TEST_CAN_MODAL" not in prompt_without
        assert "- (none provided)" in prompt_without
    finally:
        session.close()


def test_all_words_are_lemmas_or_grammatical_handles_spanish_example() -> None:
    words = [
        {
            "position": 0,
            "part_of_speech": "pronoun",
            "english_gloss": "they",
            "surface_form": "Ellos",
            "grammatical_form": "pronoun/es_subjective",
            "lemma_guid": "NONE",
            "lemma": "No lemma",
        },
        {
            "position": 1,
            "part_of_speech": "verb",
            "english_gloss": "bought",
            "surface_form": "compraron",
            "grammatical_form": "verb/es_3p_past",
            "lemma_guid": "V01_001",
            "lemma": "buy",
        },
        {
            "position": 2,
            "part_of_speech": "noun",
            "english_gloss": "salt",
            "surface_form": "sal",
            "grammatical_form": "noun/es_singular",
            "lemma_guid": "N01_001",
            "lemma": "salt",
        },
        {
            "position": 3,
            "part_of_speech": "preposition",
            "english_gloss": "in",
            "surface_form": "en",
            "grammatical_form": "preposition/es_base",
            "lemma_guid": "P01_001",
            "lemma": "in",
        },
        {
            "position": 4,
            "part_of_speech": "article",
            "english_gloss": "the",
            "surface_form": "la",
            "grammatical_form": "article/es_singular_f",
            "lemma_guid": "NONE",
            "lemma": "No lemma",
        },
        {
            "position": 5,
            "part_of_speech": "noun",
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
            "part_of_speech": "noun",
            "english_gloss": "store",
            "surface_form": "tienda",
            "grammatical_form": "noun/es_singular",
            "lemma_guid": "NONE",
            "lemma": "No lemma",
        },
        {
            "position": 1,
            "part_of_speech": "article",
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
            "part_of_speech": "verb",
            "english_gloss": "saw",
            "surface_form": "Vimos",
            "grammatical_form": "verb/es_past",
            "lemma_guid": "V10_001",
            "lemma": "see",
        },
        {
            "position": 1,
            "part_of_speech": "article",
            "english_gloss": "a",
            "surface_form": "un",
            "grammatical_form": "article/base",
            "lemma_guid": "NONE",
            "lemma": "No lemma",
        },
        {
            "position": 2,
            "part_of_speech": "object",
            "english_gloss": "pig",
            "surface_form": "cerdo",
            "grammatical_form": "noun/es_singular",
            "lemma_guid": "N22_001",
            "lemma": "pig",
        },
        {
            "position": 3,
            "part_of_speech": "preposition",
            "english_gloss": "at",
            "surface_form": "en",
            "grammatical_form": "preposition/base",
            "lemma_guid": "P01_001",
            "lemma": "in",
        },
        {
            "position": 4,
            "part_of_speech": "article",
            "english_gloss": "the",
            "surface_form": "la",
            "grammatical_form": "article/base",
            "lemma_guid": "NONE",
            "lemma": "No lemma",
        },
        {
            "position": 5,
            "part_of_speech": "object_of_preposition",
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


def test_find_unresolved_non_grammatical_words_unknown_language_has_no_grammar_fallback() -> None:
    words = [
        {
            "position": 0,
            "part_of_speech": "article",
            "english_gloss": "the",
            "surface_form": "the",
            "grammatical_form": "article/en_singular",
            "lemma_guid": "NONE",
            "lemma": "No lemma",
        }
    ]

    unresolved = find_unresolved_non_grammatical_words(words, "xx")

    assert len(unresolved) == 1
    assert unresolved[0]["surface_form"] == "the"


def test_find_unresolved_non_grammatical_words_keeps_skip_for_known_grammatical_tokens() -> None:
    words = [
        {
            "position": 0,
            "part_of_speech": "article",
            "english_gloss": "the",
            "surface_form": "le",
            "grammatical_form": "noun/fr_singular",
            "lemma_guid": "NONE",
            "lemma": "No lemma",
        }
    ]

    unresolved = find_unresolved_non_grammatical_words(words, "fr")

    assert unresolved == []
    assert all_words_are_lemmas_or_grammatical(words, "fr")


def test_find_unresolved_non_grammatical_words_requires_release_backed_function_lemmas() -> None:
    words = [
        {
            "position": position,
            "part_of_speech": part_of_speech,
            "english_gloss": surface_form,
            "surface_form": surface_form,
            "grammatical_form": f"{part_of_speech}/base",
            "lemma_guid": "NONE",
            "lemma": "No lemma",
        }
        for position, (surface_form, part_of_speech) in enumerate(
            [("if", "conjunction"), ("in", "preposition"), ("who", "pronoun")]
        )
    ]

    unresolved = find_unresolved_non_grammatical_words(words, "en")

    assert [word["surface_form"] for word in unresolved] == ["if", "in", "who"]
    assert not all_words_are_lemmas_or_grammatical(words, "en")


def test_find_unresolved_non_grammatical_words_accepts_resolved_function_lemma() -> None:
    words = [
        {
            "position": 0,
            "part_of_speech": "conjunction",
            "english_gloss": "if",
            "surface_form": "if",
            "grammatical_form": "conjunction/base",
            "lemma_guid": "C01_001",
            "lemma": "if",
        }
    ]

    assert find_unresolved_non_grammatical_words(words, "en") == []
    assert all_words_are_lemmas_or_grammatical(words, "en")


def test_translate_and_decompose_prompt_pins_name_renderings() -> None:
    """A name the sentence casts must reach the prompt as its curated spelling.

    Without this the model invents a rendering per call and the same character
    is spelled differently in consecutive sentences.
    """
    from sqlalchemy.orm import Session

    from storage.crud.name_entity import create_name, set_name_translation
    from storage.crud.sentence_word import add_sentence_word
    from tests.sentences.candidate_lookup_fixture import (
        add_test_sentence,
        build_test_engine,
        seed_test_database,
    )

    engine = build_test_engine()
    session = Session(engine)
    try:
        seed_test_database(session)
        sentence = add_test_sentence(session, {"en": "John is at school"})

        name = create_name(session, name_text="John", kind="given_name")
        set_name_translation(session, name, language_code="lt", translation="Džonas")
        set_name_translation(
            session,
            name,
            language_code="ru",
            translation="Иван",
            rendering_kind="localization",
        )
        add_sentence_word(
            session,
            sentence=sentence,
            position=0,
            part_of_speech="noun",
            language_code="en",
            name=name,
        )
        session.flush()

        _, prompt = build_prompt_for_translate_and_decompose(
            sentence, ["lt", "ru"], session, source_language="en"
        )

        assert "John: lt=Džonas" in prompt
        # Transliteration is the default, so the localization is not pinned here.
        assert "Иван" not in prompt

        _, localized = build_prompt_for_translate_and_decompose(
            sentence,
            ["lt", "ru"],
            session,
            source_language="en",
            rendering_kind="localization",
        )

        assert "ru=Иван" in localized
        # Lithuanian has no localization, so it falls back rather than dropping.
        assert "lt=Džonas" in localized
    finally:
        session.close()


def test_translate_and_decompose_prompt_without_names_says_none() -> None:
    """A sentence casting no names must still render a well-formed prompt."""
    from sqlalchemy.orm import Session

    from tests.sentences.candidate_lookup_fixture import (
        add_test_sentence,
        build_test_engine,
        seed_test_database,
    )

    engine = build_test_engine()
    session = Session(engine)
    try:
        seed_test_database(session)
        sentence = add_test_sentence(session, {"en": "I can see him"})

        _, prompt = build_prompt_for_translate_and_decompose(
            sentence, ["fr"], session, source_language="en"
        )

        assert "Name renderings" in prompt
        assert "(none)" in prompt
    finally:
        session.close()
