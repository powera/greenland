#!/usr/bin/python3

"""Runner for multilingual sentence decomposition benchmark."""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from benchmarks.lib.runners.partial_credit_runner import PartialCreditRunner
from benchmarks.lib.utils.factory import runner
from langtools.form_equivalences import are_grammatical_forms_equivalent

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@runner("0062_sentence_decomposition")
class SentenceDecompositionRunner(PartialCreditRunner):
    """Runner for sentence decomposition benchmark tests."""

    # A reasonably strict bar while allowing minor annotation mismatch.
    CORRECTNESS_THRESHOLD = 70

    WORD_FIELD_WEIGHTS = {
        "position": 0.15,
        "surface_form": 0.45,
        "lemma_guid": 0.20,
        "role": 0.08,
        "english_gloss": 0.04,
        "grammatical_form": 0.04,
        "lemma": 0.04,
    }

    DEFAULT_INSERTION_PENALTY = 0.18
    LOW_CONTENT_INSERTION_PENALTY = 0.08
    DELETION_PENALTY = 0.30

    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        raw_prompt = question_data["question_text"]
        schema = question_data.get("schema")

        # Extract key information from the raw prompt
        import re

        # Extract target language and translation (the most important parts)
        target_lang_match = re.search(r"Target language: (\w+)", raw_prompt)
        target_translation_match = re.search(r'Target translation: "(.*?)"', raw_prompt)
        source_match = re.search(r'Source sentence \((\w+)\): "(.*?)"', raw_prompt)

        target_lang = target_lang_match.group(1) if target_lang_match else "unknown"
        target_translation = target_translation_match.group(1) if target_translation_match else ""
        source_lang = source_match.group(1) if source_match else "en"
        source_sentence = source_match.group(2) if source_match else ""

        # Extract candidate lemmas section
        candidate_section = ""
        if "Candidate lemmas" in raw_prompt:
            candidate_start = raw_prompt.find("Candidate lemmas")
            candidate_end = raw_prompt.find("\n\nReturn schema requirements")
            if candidate_end <= candidate_start:
                candidate_end = raw_prompt.find("\n\nGrammatical form conventions")
            if candidate_end > candidate_start:
                candidate_section = raw_prompt[candidate_start:candidate_end].strip()

        # Build clean, focused prompt
        prompt = f"""Decompose this sentence into tokens with grammatical analysis.

Target language: {target_lang}
Sentence to analyze: "{target_translation}"

Source ({source_lang}): "{source_sentence}"

{candidate_section}

Output requirements:
- Return exactly ONE language entry and set language_code to "{target_lang}"
- The languages[] breakdown must analyze tokens from "{target_translation}" only
- Include all tokens in order (zero-indexed positions)
- For each token provide: position, role, english_gloss, surface_form, grammatical_form, lemma_guid, lemma
- Use lemma_guid from candidate lemmas when applicable, otherwise use "NONE"
- Set word_count to match the number of token entries
- IMPORTANT: Do NOT include punctuation as standalone tokens in words[]"""

        context = """You are a multilingual linguistics expert specializing in morphological analysis.
Your task is to decompose sentences into tokens and provide detailed grammatical information for each token.

Grammatical form format:
- Use <role>/<language_code>_<morphology> for inflected words.
- Person/number notation: 1s, 2s, 3s, 1p, 2p, 3p.
- Include gender only when the surface form differs by gender (e.g., 3s-f, singular_f).
- Tense/aspect examples: present, past, future, impf, pc, inf.
- Case languages (lt, de): include case + number (e.g., noun/de_accusative_singular).
- Non-case languages (en, fr, es, pt, ko, zh): nouns should use number only (e.g., noun/fr_singular).
- Pronouns: pronoun/<lang>_subjective|objective|possessive|reflexive (or case labels for case languages).
- Numerals: numeral/<lang>_cardinal|ordinal.
- For uninflected function words: <role>/base (e.g., preposition/base).

Important rules:
- Maintain token order from the original sentence
- Use zero-indexed positions
- Ensure word_count equals the number of word entries
- Output must contain exactly one language entry
- Do NOT include punctuation marks as separate words
- Return only valid JSON matching the provided schema"""

        return prompt, schema, context

    def _normalize(self, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().lower().split())
        if isinstance(value, list):
            return [self._normalize(item) for item in value]
        if isinstance(value, dict):
            return {key: self._normalize(val) for key, val in value.items()}
        return value

    def _normalize_language_entry(self, item: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self._normalize(item)
        words: List[Dict[str, Any]] = [
            row for row in normalized.get("words", []) if isinstance(row, dict)
        ]
        words_sorted = sorted(words, key=lambda row: row.get("position", 0))
        normalized["words"] = words_sorted
        normalized["word_count"] = len(words_sorted)
        return normalized

    def _score_word(self, expected_word: Dict[str, Any], model_word: Dict[str, Any]) -> float:
        word_score, _ = self._score_word_with_details(expected_word, model_word)
        return word_score

    def _score_word_with_details(
        self,
        expected_word: Dict[str, Any],
        model_word: Dict[str, Any],
        include_position: bool = True,
    ) -> Tuple[float, Dict[str, Any]]:
        score = 0.0
        fields_to_score = [
            field for field in self.WORD_FIELD_WEIGHTS if include_position or field != "position"
        ]
        total = sum(self.WORD_FIELD_WEIGHTS[field] for field in fields_to_score)
        if total <= 0:
            return 0.0, {"fields": {}, "anchor_match": False, "word_score": 0.0}

        field_matches: Dict[str, bool] = {}

        for field, weight in self.WORD_FIELD_WEIGHTS.items():
            if not include_position and field == "position":
                continue
            expected_value = expected_word.get(field)
            model_value = model_word.get(field)

            # Lemma text may vary by normalization/language; prefer GUID alignment.
            if field == "lemma" and expected_word.get("lemma_guid") == model_word.get("lemma_guid"):
                score += weight
                field_matches[field] = True
                continue

            if expected_value == model_value:
                score += weight
                field_matches[field] = True
                continue

            if field == "english_gloss" and self._is_gloss_match(expected_value, model_value):
                score += weight
                field_matches[field] = True
                continue

            if field == "grammatical_form":
                grammar_similarity = self._grammatical_form_similarity(expected_value, model_value)
                score += weight * grammar_similarity
                field_matches[field] = grammar_similarity > 0
                continue

            field_matches[field] = False

        word_score = score / total
        anchor_match = (
            (not include_position or field_matches.get("position", False))
            and field_matches.get("surface_form", False)
            and field_matches.get("lemma_guid", False)
        )

        return word_score, {
            "fields": field_matches,
            "anchor_match": anchor_match,
            "word_score": round(word_score, 4),
        }

    def _is_punctuation_token(self, word: Dict[str, Any]) -> bool:
        surface_form = word.get("surface_form")
        if not isinstance(surface_form, str) or not surface_form.strip():
            return False
        return bool(re.fullmatch(r"[^\w\s]+", surface_form.strip(), flags=re.UNICODE))

    def _is_low_content_token(self, word: Dict[str, Any]) -> bool:
        role = str(word.get("role", "")).strip().lower()
        grammatical_form = str(word.get("grammatical_form", "")).strip().lower()

        low_content_roles = {
            "particle",
            "determiner",
            "article",
            "auxiliary",
            "preposition",
            "conjunction",
            "marker",
            "case_marker",
            "clitic",
        }
        if role in low_content_roles:
            return True

        if grammatical_form.endswith("/base") and role not in {
            "noun",
            "verb",
            "adjective",
            "adverb",
            "pronoun",
            "numeral",
        }:
            return True

        return False

    def _insertion_penalty(self, model_word: Dict[str, Any]) -> float:
        return (
            self.LOW_CONTENT_INSERTION_PENALTY
            if self._is_low_content_token(model_word)
            else self.DEFAULT_INSERTION_PENALTY
        )

    def _align_words(
        self, expected_words: List[Dict[str, Any]], model_words: List[Dict[str, Any]]
    ) -> Tuple[List[Tuple[Optional[int], Optional[int]]], float]:
        """Align expected/model token streams with DP to avoid cascade errors from token splits."""
        n = len(expected_words)
        m = len(model_words)
        dp = [[0.0 for _ in range(m + 1)] for _ in range(n + 1)]
        back: List[List[Tuple[Optional[int], Optional[int]]]] = [
            [(None, None) for _ in range(m + 1)] for _ in range(n + 1)
        ]

        for i in range(1, n + 1):
            dp[i][0] = dp[i - 1][0] - self.DELETION_PENALTY
            back[i][0] = (i - 1, 0)

        for j in range(1, m + 1):
            dp[0][j] = dp[0][j - 1] - self._insertion_penalty(model_words[j - 1])
            back[0][j] = (0, j - 1)

        for i in range(1, n + 1):
            for j in range(1, m + 1):
                match_score, _ = self._score_word_with_details(
                    expected_words[i - 1], model_words[j - 1], include_position=False
                )
                options = [
                    (dp[i - 1][j - 1] + match_score, (i - 1, j - 1)),
                    (dp[i - 1][j] - self.DELETION_PENALTY, (i - 1, j)),
                    (dp[i][j - 1] - self._insertion_penalty(model_words[j - 1]), (i, j - 1)),
                ]
                best_score, prev = max(options, key=lambda option: option[0])
                dp[i][j] = best_score
                back[i][j] = prev

        alignment: List[Tuple[Optional[int], Optional[int]]] = []
        i, j = n, m
        while i > 0 or j > 0:
            prev_i, prev_j = back[i][j]
            if prev_i is None or prev_j is None:
                break
            if prev_i == i - 1 and prev_j == j - 1:
                alignment.append((i - 1, j - 1))
            elif prev_i == i - 1 and prev_j == j:
                alignment.append((i - 1, None))
            else:
                alignment.append((None, j - 1))
            i, j = prev_i, prev_j

        alignment.reverse()
        return alignment, dp[n][m]

    def _score_language_entry_with_breakdown(
        self, expected: Dict[str, Any], model: Dict[str, Any]
    ) -> Tuple[float, Dict[str, Any]]:
        breakdown: Dict[str, Any] = {
            "language_match": False,
            "translation_match": False,
            "translation_points": 0.0,
            "structure_match": False,
            "structure_points": 0.0,
            "token_component": 0.0,
            "punctuation_penalty": 0.0,
            "punctuation_tokens": [],
            "token_details": [],
            "deductions": [],
        }

        if expected.get("language_code") != model.get("language_code"):
            breakdown["deductions"].append("language_code mismatch")
            return 0.0, breakdown

        breakdown["language_match"] = True

        if expected.get("translation") == model.get("translation"):
            breakdown["translation_match"] = True
            breakdown["translation_points"] = 0.15
        else:
            breakdown["deductions"].append("translation mismatch (-15)")

        expected_words = [w for w in expected.get("words", []) if isinstance(w, dict)]
        model_words_raw = [w for w in model.get("words", []) if isinstance(w, dict)]
        punctuation_tokens = [w for w in model_words_raw if self._is_punctuation_token(w)]
        model_words = [w for w in model_words_raw if not self._is_punctuation_token(w)]

        breakdown["punctuation_tokens"] = punctuation_tokens
        if punctuation_tokens:
            breakdown["punctuation_penalty"] = 0.05
            breakdown["deductions"].append("punctuation token present (-5)")

        token_component = 0.0
        if expected_words:
            alignment, _ = self._align_words(expected_words, model_words)
            aligned_expected = 0
            token_score = 0.0
            inserted_tokens: List[Dict[str, Any]] = []

            for expected_index, model_index in alignment:
                if expected_index is None and model_index is not None:
                    inserted_tokens.append(model_words[model_index])
                    continue

                if expected_index is None:
                    continue

                aligned_expected += 1
                expected_word = expected_words[expected_index]
                model_word = model_words[model_index] if model_index is not None else None
                position = expected_word.get("position")
                token_detail: Dict[str, Any] = {
                    "position": position,
                    "expected_surface_form": expected_word.get("surface_form"),
                    "model_surface_form": model_word.get("surface_form") if model_word else None,
                    "matched": model_word is not None,
                }
                if model_word is not None:
                    word_score, word_breakdown = self._score_word_with_details(
                        expected_word, model_word
                    )
                    token_score += word_score
                    token_detail.update(word_breakdown)
                else:
                    token_detail.update({"fields": {}, "anchor_match": False, "word_score": 0.0})
                breakdown["token_details"].append(token_detail)

            if len(expected_words) == len(model_words):
                breakdown["structure_match"] = True
                breakdown["structure_points"] = 0.05
            elif inserted_tokens and all(
                self._is_low_content_token(word) for word in inserted_tokens
            ):
                breakdown["structure_points"] = 0.03
                breakdown["deductions"].append("minor extra low-content token(s) (-2)")
            else:
                breakdown["deductions"].append("word count mismatch (-5)")

            if aligned_expected < len(expected_words):
                for expected_word in expected_words[aligned_expected:]:
                    breakdown["token_details"].append(
                        {
                            "position": expected_word.get("position"),
                            "expected_surface_form": expected_word.get("surface_form"),
                            "model_surface_form": None,
                            "matched": False,
                            "fields": {},
                            "anchor_match": False,
                            "word_score": 0.0,
                        }
                    )

            token_component = 0.80 * (token_score / len(expected_words))
            breakdown["token_component"] = round(token_component, 4)

        score = (
            breakdown["translation_points"]
            + breakdown["structure_points"]
            + token_component
            - breakdown["punctuation_penalty"]
        )

        if not breakdown["deductions"]:
            breakdown["deductions"].append("none")

        breakdown["raw_score"] = round(score, 4)
        breakdown["final_score"] = round(min(max(score, 0.0), 1.0), 4)

        return min(max(score, 0.0), 1.0), breakdown

    def _is_gloss_match(self, expected: Any, model: Any) -> bool:
        if not isinstance(expected, str) or not isinstance(model, str):
            return False

        expected_norm = expected.strip().lower()
        model_norm = model.strip().lower()

        if expected_norm == model_norm:
            return True

        # Minor inflection differences in glosses (e.g., "go" vs "goes") are acceptable.
        singularized_expected = re.sub(r"(es|s)$", "", expected_norm)
        singularized_model = re.sub(r"(es|s)$", "", model_norm)
        return bool(singularized_expected and singularized_expected == singularized_model)

    def _grammatical_form_similarity(self, expected: Any, model: Any) -> float:
        if not isinstance(expected, str) or not isinstance(model, str):
            return 0.0

        expected_norm = expected.strip().lower()
        model_norm = model.strip().lower()
        if expected_norm == model_norm:
            return 1.0

        # Check language-specific equivalences (e.g. lt locative = inessive).
        if are_grammatical_forms_equivalent(expected_norm, model_norm):
            return 1.0

        # Consider morphology-compatible extensions as partial credit:
        # noun/lt_nominative_singular ~= noun/lt_nominative_singular_m
        if expected_norm.startswith(f"{model_norm}_") or model_norm.startswith(f"{expected_norm}_"):
            return 0.5

        return 0.0

    def _score_language_entry(self, expected: Dict[str, Any], model: Dict[str, Any]) -> float:
        score, _ = self._score_language_entry_with_breakdown(expected, model)
        return score

    def score_response(self, question_data: Dict, response: Any) -> int:
        if not isinstance(response, dict):
            return 0

        expected = question_data.get("correct_answer", {})
        if not isinstance(expected, dict):
            return 0

        expected_languages = expected.get("languages", [])
        model_languages = response.get("languages", [])
        if not isinstance(expected_languages, list) or not isinstance(model_languages, list):
            return 0
        if len(expected_languages) != 1 or len(model_languages) != 1:
            return 0

        expected_entry = self._normalize_language_entry(expected_languages[0])
        model_entry = self._normalize_language_entry(model_languages[0])

        score, _ = self._score_language_entry_with_breakdown(expected_entry, model_entry)
        return int(round(score * 100))

    def build_debug_info(self, question_data: Dict, response: Any, is_correct: bool) -> Dict:
        if hasattr(response, "structured_data") and response.structured_data:
            model_answer = response.structured_data
        else:
            model_answer = response.response_text

        return {
            "prompt": question_data.get("question_text", ""),
            # Keep legacy keys so existing run views can render reliably.
            "response": model_answer,
            "expected": question_data.get("correct_answer"),
            # Also include descriptive keys used by newer runners.
            "model_answer": model_answer,
            "expected_answer": question_data.get("correct_answer"),
            "is_correct": is_correct,
            "response_payload": model_answer,
            "question_snapshot": question_data,
            "scoring_version": "0062-v3-dp-alignment",
            "scoring_breakdown": self._build_scoring_breakdown(question_data, model_answer),
        }

    def _build_scoring_breakdown(
        self, question_data: Dict[str, Any], model_answer: Any
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(model_answer, dict):
            return None

        expected = question_data.get("correct_answer", {})
        if not isinstance(expected, dict):
            return None

        expected_languages = expected.get("languages", [])
        model_languages = model_answer.get("languages", [])
        if not isinstance(expected_languages, list) or not isinstance(model_languages, list):
            return None
        if len(expected_languages) != 1 or len(model_languages) != 1:
            return {
                "error": "expected exactly one language entry in expected and model response",
                "expected_language_count": len(expected_languages),
                "model_language_count": len(model_languages),
            }

        expected_entry = self._normalize_language_entry(expected_languages[0])
        model_entry = self._normalize_language_entry(model_languages[0])
        score, breakdown = self._score_language_entry_with_breakdown(expected_entry, model_entry)
        breakdown["score"] = int(round(score * 100))
        return breakdown
