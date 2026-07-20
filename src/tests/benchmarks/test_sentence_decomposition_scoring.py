#!/usr/bin/python3
"""Unit tests for benchmark 0062 sentence decomposition scoring behavior."""

import json
import sys
import types
from pathlib import Path

# The benchmark runner imports validation utilities that depend on pydantic,
# which is unavailable in this test environment.
if "pydantic" not in sys.modules:
    pydantic_stub = types.ModuleType("pydantic")

    class BaseModel:  # pragma: no cover - compatibility shim
        pass

    pydantic_stub.BaseModel = BaseModel
    sys.modules["pydantic"] = pydantic_stub

# Import benchmarks.lib.utils BEFORE any runner module. The utils package init
# eagerly imports every generator/runner and then the registry, and the registry
# imports runners back for their registration side effects. Entering that graph
# from a runner instead leaves the runner half-initialized when the registry
# reaches it, raising ImportError. Importing utils first lets it complete.
import benchmarks.lib.utils  # noqa: F401  (import order matters; see above)

from benchmarks.lib.runners.sentence_decomposition_runner import SentenceDecompositionRunner


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "sentence_decomposition"


def _load_fixture(name: str):
    with (FIXTURES_DIR / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def test_0062_allows_close_morphology_and_gloss_variants_for_partial_credit():
    runner = SentenceDecompositionRunner.__new__(SentenceDecompositionRunner)

    expected = {
        "languages": [
            {
                "language_code": "lt",
                "translation": "Mano sūnus eina į mokyklą.",
                "word_count": 5,
                "words": [
                    {
                        "english_gloss": "my",
                        "grammatical_form": "pronoun/lt_possessive",
                        "lemma": "No lemma",
                        "lemma_guid": "NONE",
                        "position": 0,
                        "role": "determiner",
                        "surface_form": "Mano",
                    },
                    {
                        "english_gloss": "son",
                        "grammatical_form": "noun/lt_nominative_singular",
                        "lemma": "son",
                        "lemma_guid": "N35_036",
                        "position": 1,
                        "role": "subject",
                        "surface_form": "sūnus",
                    },
                    {
                        "english_gloss": "goes",
                        "grammatical_form": "verb/lt_3s_present",
                        "lemma": "go",
                        "lemma_guid": "V12_004",
                        "position": 2,
                        "role": "verb",
                        "surface_form": "eina",
                    },
                    {
                        "english_gloss": "to",
                        "grammatical_form": "preposition/base",
                        "lemma": "No lemma",
                        "lemma_guid": "NONE",
                        "position": 3,
                        "role": "preposition",
                        "surface_form": "į",
                    },
                    {
                        "english_gloss": "school",
                        "grammatical_form": "noun/lt_accusative_singular",
                        "lemma": "school (institution)",
                        "lemma_guid": "N07_002",
                        "position": 4,
                        "role": "object",
                        "surface_form": "mokyklą",
                    },
                ],
            }
        ]
    }

    got = {
        "languages": [
            {
                "language_code": "lt",
                "translation": "My son goes to school.",
                "word_count": 5,
                "words": [
                    {
                        "english_gloss": "my",
                        "grammatical_form": "determiner/possessive",
                        "lemma": "mano",
                        "lemma_guid": "NONE",
                        "position": 0,
                        "role": "determiner",
                        "surface_form": "Mano",
                    },
                    {
                        "english_gloss": "son",
                        "grammatical_form": "noun/lt_nominative_singular_m",
                        "lemma": "sūnus",
                        "lemma_guid": "N35_036",
                        "position": 1,
                        "role": "noun",
                        "surface_form": "sūnus",
                    },
                    {
                        "english_gloss": "go",
                        "grammatical_form": "verb/lt_3s_present_indicative",
                        "lemma": "eiti",
                        "lemma_guid": "V12_004",
                        "position": 2,
                        "role": "verb",
                        "surface_form": "eina",
                    },
                    {
                        "english_gloss": "to",
                        "grammatical_form": "preposition/base",
                        "lemma": "į",
                        "lemma_guid": "NONE",
                        "position": 3,
                        "role": "preposition",
                        "surface_form": "į",
                    },
                    {
                        "english_gloss": "school",
                        "grammatical_form": "noun/lt_accusative_singular_f",
                        "lemma": "mokykla",
                        "lemma_guid": "N07_002",
                        "position": 4,
                        "role": "noun",
                        "surface_form": "mokyklą",
                    },
                ],
            }
        ]
    }

    score = runner.score_response({"correct_answer": expected}, got)

    assert score >= runner.CORRECTNESS_THRESHOLD


def test_0062_punctuation_token_is_single_flat_five_point_penalty():
    runner = SentenceDecompositionRunner.__new__(SentenceDecompositionRunner)
    payload = _load_fixture("punctuation_penalty_case.json")

    score = runner.score_response(payload["question_data"], payload["response"])

    assert score == 95


def test_0062_anchor_fields_keep_score_high_even_when_secondary_fields_vary():
    runner = SentenceDecompositionRunner.__new__(SentenceDecompositionRunner)
    payload = _load_fixture("anchor_priority_case.json")

    score = runner.score_response(payload["question_data"], payload["response"])

    assert score >= 80


def test_0062_language_mismatch_still_scores_zero():
    runner = SentenceDecompositionRunner.__new__(SentenceDecompositionRunner)
    payload = _load_fixture("language_mismatch_case.json")

    score = runner.score_response(payload["question_data"], payload["response"])

    assert score == 0


def test_0062_debug_info_contains_payload_for_future_rescoring():
    runner = SentenceDecompositionRunner.__new__(SentenceDecompositionRunner)
    question_data = {"question_text": "q", "correct_answer": {"languages": []}}

    class _Response:
        structured_data = {"languages": []}
        response_text = "raw"

    debug = runner.build_debug_info(question_data, _Response(), is_correct=False)

    # The model answer and the expectation are each stored under both a legacy
    # key (response/expected) and a descriptive one (model_answer/
    # expected_answer), so old run views keep rendering. Either pair is enough
    # to re-score the question later.
    assert debug["response"] == {"languages": []}
    assert debug["model_answer"] == {"languages": []}
    assert debug["expected"] == question_data["correct_answer"]
    assert debug["expected_answer"] == question_data["correct_answer"]
    assert debug["scoring_version"] == "0062-v3-dp-alignment"


def test_0062_split_tokens_do_not_cascade_mismatch_scores():
    runner = SentenceDecompositionRunner.__new__(SentenceDecompositionRunner)

    expected = {
        "languages": [
            {
                "language_code": "zh",
                "translation": "她昨天去了医院。",
                "word_count": 4,
                "words": [
                    {
                        "english_gloss": "she",
                        "grammatical_form": "pronoun/zh_subjective",
                        "lemma": "No lemma",
                        "lemma_guid": "NONE",
                        "position": 0,
                        "role": "pronoun",
                        "surface_form": "她",
                    },
                    {
                        "english_gloss": "yesterday",
                        "grammatical_form": "adverb/zh",
                        "lemma": "yesterday",
                        "lemma_guid": "D03_002",
                        "position": 1,
                        "role": "adverb",
                        "surface_form": "昨天",
                    },
                    {
                        "english_gloss": "went",
                        "grammatical_form": "verb/zh_3s_past",
                        "lemma": "go",
                        "lemma_guid": "V12_004",
                        "position": 2,
                        "role": "verb",
                        "surface_form": "去了",
                    },
                    {
                        "english_gloss": "hospital",
                        "grammatical_form": "noun/zh_singular",
                        "lemma": "hospital",
                        "lemma_guid": "N07_003",
                        "position": 3,
                        "role": "noun",
                        "surface_form": "医院",
                    },
                ],
            }
        ]
    }

    got = {
        "languages": [
            {
                "language_code": "zh",
                "translation": "她昨天去了医院。",
                "word_count": 5,
                "words": [
                    {
                        "english_gloss": "she",
                        "grammatical_form": "pronoun/zh_subjective",
                        "lemma": "她",
                        "lemma_guid": "NONE",
                        "position": 0,
                        "role": "pronoun",
                        "surface_form": "她",
                    },
                    {
                        "english_gloss": "yesterday",
                        "grammatical_form": "adverb/base",
                        "lemma": "昨天",
                        "lemma_guid": "D03_002",
                        "position": 1,
                        "role": "adverb",
                        "surface_form": "昨天",
                    },
                    {
                        "english_gloss": "go",
                        "grammatical_form": "verb/zh_past",
                        "lemma": "去",
                        "lemma_guid": "V12_004",
                        "position": 2,
                        "role": "verb",
                        "surface_form": "去",
                    },
                    {
                        "english_gloss": "(perfective aspect marker)",
                        "grammatical_form": "particle/base",
                        "lemma": "了",
                        "lemma_guid": "NONE",
                        "position": 3,
                        "role": "particle",
                        "surface_form": "了",
                    },
                    {
                        "english_gloss": "hospital",
                        "grammatical_form": "noun/zh_singular",
                        "lemma": "医院",
                        "lemma_guid": "N07_003",
                        "position": 4,
                        "role": "noun",
                        "surface_form": "医院",
                    },
                ],
            }
        ]
    }

    score = runner.score_response({"correct_answer": expected}, got)

    assert score >= runner.CORRECTNESS_THRESHOLD
