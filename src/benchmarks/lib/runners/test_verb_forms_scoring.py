#!/usr/bin/python3

"""Unit tests for 0121 verb forms scoring."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path


def _load_runner_module():
    # Provide lightweight stubs so this unit test can run without full benchmark deps.
    clients_module = types.ModuleType("clients")
    clients_module.unified_client = object()
    sys.modules.setdefault("clients", clients_module)

    ollama_module = types.ModuleType("clients.ollama_client")

    class OllamaTimeoutError(Exception):
        pass

    ollama_module.OllamaTimeoutError = OllamaTimeoutError
    sys.modules.setdefault("clients.ollama_client", ollama_module)

    base_module = types.ModuleType("benchmarks.lib.utils.base")

    class BenchmarkRunner:
        def __init__(self, model, metadata):
            self.model = model
            self.metadata = metadata

    base_module.BenchmarkRunner = BenchmarkRunner
    sys.modules.setdefault("benchmarks.lib.utils.base", base_module)

    data_models_module = types.ModuleType("benchmarks.lib.utils.data_models")

    class BenchmarkMetadata:
        def __init__(self, code, name, description):
            self.code = code
            self.name = name
            self.description = description

    class BenchmarkResult:
        pass

    data_models_module.BenchmarkMetadata = BenchmarkMetadata
    data_models_module.BenchmarkResult = BenchmarkResult
    sys.modules.setdefault("benchmarks.lib.utils.data_models", data_models_module)

    factory_module = types.ModuleType("benchmarks.lib.utils.factory")

    def runner(_code):
        def decorator(cls):
            return cls

        return decorator

    factory_module.runner = runner
    sys.modules.setdefault("benchmarks.lib.utils.factory", factory_module)

    runners_pkg = types.ModuleType("benchmarks.lib.runners")
    runners_pkg.__path__ = []
    sys.modules.setdefault("benchmarks.lib.runners", runners_pkg)

    partial_path = Path(__file__).with_name("partial_credit_runner.py")
    partial_spec = importlib.util.spec_from_file_location(
        "benchmarks.lib.runners.partial_credit_runner", partial_path
    )
    partial_module = importlib.util.module_from_spec(partial_spec)
    assert partial_spec and partial_spec.loader
    partial_spec.loader.exec_module(partial_module)
    sys.modules["benchmarks.lib.runners.partial_credit_runner"] = partial_module

    module_path = Path(__file__).with_name("verb_forms_runner.py")
    spec = importlib.util.spec_from_file_location("verb_forms_runner_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


RUNNER_MODULE = _load_runner_module()
VerbFormsRunner = RUNNER_MODULE.VerbFormsRunner


class TestVerbFormsScoring(unittest.TestCase):
    def setUp(self):
        # Score methods do not require full base-runner initialization.
        self.runner = VerbFormsRunner.__new__(VerbFormsRunner)

    def test_partial_credit_for_etre_imparfait_vs_passe_compose(self):
        question_data = {
            "correct_answer": {
                "language_code": "fr",
                "lemma": "être",
                "required_extra_forms": ["present_participle", "past_participle"],
                "extra_forms": {
                    "past_participle": "été",
                    "present_participle": "étant",
                },
                "forms": {
                    "future": {
                        "1p": "serons",
                        "1s": "serai",
                        "2p": "serez",
                        "2s": "seras",
                        "3p": "seront",
                        "3s": "sera",
                    },
                    "past": {
                        "1p": "avons été",
                        "1s": "ai été",
                        "2p": "avez été",
                        "2s": "as été",
                        "3p": "ont été",
                        "3s": "a été",
                    },
                    "present": {
                        "1p": "sommes",
                        "1s": "suis",
                        "2p": "êtes",
                        "2s": "es",
                        "3p": "sont",
                        "3s": "est",
                    },
                },
            }
        }

        response = {
            "language_code": "fr",
            "lemma": "être",
            "extra_forms": {
                "past_participle": "été",
                "present_participle": "étant",
            },
            "forms": {
                "future": {
                    "1p": "serons",
                    "1s": "serai",
                    "2p": "serez",
                    "2s": "seras",
                    "3p": "seront",
                    "3s": "sera",
                },
                "past": {
                    "1p": "étions",
                    "1s": "étais",
                    "2p": "étiez",
                    "2s": "étais",
                    "3p": "étaient",
                    "3s": "était",
                },
                "present": {
                    "1p": "sommes",
                    "1s": "suis",
                    "2p": "êtes",
                    "2s": "es",
                    "3p": "sont",
                    "3s": "est",
                },
            },
        }

        score = self.runner.score_response(question_data, response)
        self.assertEqual(score, 56)

    def test_french_pronoun_stripping_scores_100(self):
        """LLM responses with subject pronouns should match bare verb forms."""
        question_data = {
            "correct_answer": {
                "language_code": "fr",
                "lemma": "ouvrir",
                "required_extra_forms": ["present_participle", "past_participle"],
                "extra_forms": {
                    "past_participle": "ouvert",
                    "present_participle": "ouvrant",
                },
                "forms": {
                    "present": {
                        "1s": "ouvre",
                        "2s": "ouvres",
                        "3s": "ouvre",
                        "1p": "ouvrons",
                        "2p": "ouvrez",
                        "3p": "ouvrent",
                    },
                    "past": {
                        "1s": "ai ouvert",
                        "2s": "as ouvert",
                        "3s": "a ouvert",
                        "1p": "avons ouvert",
                        "2p": "avez ouvert",
                        "3p": "ont ouvert",
                    },
                    "future": {
                        "1s": "ouvrirai",
                        "2s": "ouvriras",
                        "3s": "ouvrira",
                        "1p": "ouvrirons",
                        "2p": "ouvrirez",
                        "3p": "ouvriront",
                    },
                },
            }
        }

        # Response includes subject pronouns
        response = {
            "language_code": "fr",
            "lemma": "ouvrir",
            "extra_forms": {
                "past_participle": "ouvert",
                "present_participle": "ouvrant",
            },
            "forms": {
                "present": {
                    "1s": "j'ouvre",
                    "2s": "tu ouvres",
                    "3s": "il/elle ouvre",
                    "1p": "nous ouvrons",
                    "2p": "vous ouvrez",
                    "3p": "ils/elles ouvrent",
                },
                "past": {
                    "1s": "j'ai ouvert",
                    "2s": "tu as ouvert",
                    "3s": "il a ouvert",
                    "1p": "nous avons ouvert",
                    "2p": "vous avez ouvert",
                    "3p": "ils ont ouvert",
                },
                "future": {
                    "1s": "j'ouvrirai",
                    "2s": "tu ouvriras",
                    "3s": "il ouvrira",
                    "1p": "nous ouvrirons",
                    "2p": "vous ouvrirez",
                    "3p": "ils ouvriront",
                },
            },
        }

        score = self.runner.score_response(question_data, response)
        self.assertEqual(score, 100)

    def test_spanish_pronoun_stripping_scores_100(self):
        question_data = {
            "correct_answer": {
                "language_code": "es",
                "lemma": "hablar",
                "required_extra_forms": ["gerund", "participle"],
                "extra_forms": {
                    "gerund": "hablando",
                    "participle": "hablado",
                },
                "forms": {
                    "present": {
                        "1s": "hablo",
                        "2s": "hablas",
                        "3s": "habla",
                        "1p": "hablamos",
                        "2p": "habláis",
                        "3p": "hablan",
                    },
                    "past": {
                        "1s": "hablé",
                        "2s": "hablaste",
                        "3s": "habló",
                        "1p": "hablamos",
                        "2p": "hablasteis",
                        "3p": "hablaron",
                    },
                    "future": {
                        "1s": "hablaré",
                        "2s": "hablarás",
                        "3s": "hablará",
                        "1p": "hablaremos",
                        "2p": "hablaréis",
                        "3p": "hablarán",
                    },
                },
            }
        }

        response = {
            "language_code": "es",
            "lemma": "hablar",
            "extra_forms": {"gerund": "hablando", "participle": "hablado"},
            "forms": {
                "present": {
                    "1s": "yo hablo",
                    "2s": "tú hablas",
                    "3s": "ella habla",
                    "1p": "nosotros hablamos",
                    "2p": "vosotros habláis",
                    "3p": "ellos hablan",
                },
                "past": {
                    "1s": "yo hablé",
                    "2s": "tú hablaste",
                    "3s": "ella habló",
                    "1p": "nosotros hablamos",
                    "2p": "vosotros hablasteis",
                    "3p": "ellos hablaron",
                },
                "future": {
                    "1s": "yo hablaré",
                    "2s": "tú hablarás",
                    "3s": "ella hablará",
                    "1p": "nosotros hablaremos",
                    "2p": "vosotros hablaréis",
                    "3p": "ellos hablarán",
                },
            },
        }

        score = self.runner.score_response(question_data, response)
        self.assertEqual(score, 100)

    def test_non_person_language_slots_are_scored(self):
        question_data = {
            "correct_answer": {
                "language_code": "ja",
                "lemma": "食べる",
                "required_extra_forms": ["te"],
                "extra_forms": {"te": "食べて"},
                "forms": {
                    "dictionary": "食べる",
                    "masu_present": "食べます",
                    "masu_past": "食べました",
                    "nai": "食べない",
                },
            }
        }

        response = {
            "language_code": "ja",
            "lemma": "食べる",
            "required_extra_forms": ["te"],
            "extra_forms": {"te": "食べて"},
            "forms": {
                "dictionary": "食べる",
                "masu_present": "食べます",
                "masu_past": "食べました",
                "nai": "食べない",
            },
        }

        score = self.runner.score_response(question_data, response)
        self.assertEqual(score, 100)


if __name__ == "__main__":
    unittest.main()
