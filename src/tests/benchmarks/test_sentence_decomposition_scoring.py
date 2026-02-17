#!/usr/bin/python3
"""Unit tests for benchmark 0062 sentence decomposition scoring behavior."""

import sys
import types

# The benchmark runner imports validation utilities that depend on pydantic,
# which is unavailable in this test environment.
if "pydantic" not in sys.modules:
    pydantic_stub = types.ModuleType("pydantic")

    class BaseModel:  # pragma: no cover - compatibility shim
        pass

    pydantic_stub.BaseModel = BaseModel
    sys.modules["pydantic"] = pydantic_stub

from benchmarks.lib.runners.sentence_decomposition_runner import SentenceDecompositionRunner


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
