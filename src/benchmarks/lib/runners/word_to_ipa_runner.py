#!/usr/bin/python3

"""Runner for the word-to-IPA benchmark."""

import json
import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from benchmarks.lib.utils.base_runner import BenchmarkRunner
from benchmarks.lib.utils.data_models import BenchmarkMetadata, BenchmarkResult
from benchmarks.lib.utils.factory import runner
from words import build_ipa_pronunciation_prompt

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Define benchmark metadata
BENCHMARK_METADATA = BenchmarkMetadata(
    code="0061_word_to_ipa",
    name="Word to IPA Pronunciation",
    description="A benchmark to evaluate a model's ability to convert words in multiple languages to IPA pronunciation.",
)


@runner("0061_word_to_ipa")
class WordToIPARunner(BenchmarkRunner):
    """Runner for word-to-IPA benchmark."""

    def __init__(self, model: str, metadata: BenchmarkMetadata):
        """Initialize runner with model and benchmark metadata."""
        super().__init__(model, metadata)

    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        """
        Prepare prompt and context for the question.

        Args:
            question_data: Question data from database

        Returns:
            Tuple of (prompt, schema, context)
        """
        question_text = question_data.get("question_text", "")
        language_code = "en"
        word = ""
        definition = ""
        sentence = ""

        for line in question_text.splitlines():
            if line.startswith("Language:"):
                language_value = line.split(":", 1)[1].strip()
                language_code = language_value.split("(")[-1].rstrip(")").strip().lower()
            elif line.startswith("Word:"):
                word = line.split(":", 1)[1].strip()
            elif line.startswith("Definition:"):
                definition = line.split(":", 1)[1].strip()
            elif line.startswith("Sentence:"):
                sentence = line.split(":", 1)[1].strip()

        if not word:
            match = re.search(r"word ['\"]([^'\"]+)['\"]", question_text, re.IGNORECASE)
            word = match.group(1).strip() if match else question_text.strip()

        combined_prompt = build_ipa_pronunciation_prompt(
            language_code,
            word,
            definition=definition,
            sentence=sentence,
        )
        context, prompt = combined_prompt.split("\n\n", 1)

        # Define a schema to ensure the response is just the IPA
        schema = {
            "type": "object",
            "properties": {
                "ipa": {"type": "string", "description": "The IPA pronunciation of the word"}
            },
            "required": ["ipa"],
        }

        return prompt, schema, context

    def evaluate_response(self, question_data: Dict, response: Any) -> bool:
        """
        Evaluate if a response is correct according to question criteria.

        Args:
            question_data: Question data from database
            response: Model response (structured data with 'ipa' field)

        Returns:
            Boolean indicating whether response is correct
        """
        # Get the correct answer from the question data
        correct_answer = question_data.get("correct_answer", "")

        # Get the model's response
        if isinstance(response, dict) and "ipa" in response:
            model_answer = response["ipa"].strip()
        else:
            # If not a dict or doesn't have 'ipa' key, use the raw response
            model_answer = str(response).strip()

        # Clean up the IPA strings by removing extra spaces and normalizing
        model_answer = self._normalize_ipa(model_answer)
        correct_answer = self._normalize_ipa(correct_answer)

        # Check if the model's answer matches the correct answer
        if model_answer == correct_answer:
            return True

        # Check against alternative pronunciations if available
        if (
            "evaluation_criteria" in question_data
            and "alternatives" in question_data["evaluation_criteria"]
        ):
            alternatives = question_data["evaluation_criteria"]["alternatives"]
            for alt in alternatives:
                normalized_alt = self._normalize_ipa(alt)
                if model_answer == normalized_alt:
                    return True

        # Check for close matches with slight variations (allow small differences)
        if self._is_close_match(model_answer, correct_answer):
            return True

        # If we get here, the answer is incorrect
        return False

    def score_response(self, question_data: Dict, response: Any) -> int:
        """Score a response on a 0-100 scale.

        Rules:
        - exact/accepted match: 100
        - otherwise: Levenshtein similarity ratio scaled from 60
          (e.g. 80% -> 48, 50% -> 30)
        """
        if isinstance(response, dict) and "ipa" in response:
            model_answer = response["ipa"].strip()
        else:
            model_answer = str(response).strip()

        normalized_model = self._normalize_ipa(model_answer)
        if not normalized_model:
            return 0

        candidates = [self._normalize_ipa(question_data.get("correct_answer", ""))]
        if (
            "evaluation_criteria" in question_data
            and "alternatives" in question_data["evaluation_criteria"]
        ):
            candidates.extend(
                self._normalize_ipa(alt)
                for alt in question_data["evaluation_criteria"]["alternatives"]
            )

        # For rescoring/partial credit, reserve 100 for strict accepted matches only.
        if any(normalized_model == expected for expected in candidates if expected):
            return 100

        best_ratio = max(
            (self._similarity_ratio(normalized_model, expected) for expected in candidates if expected),
            default=0.0,
        )
        return int(round(60 * best_ratio))

    def _similarity_ratio(self, left: str, right: str) -> float:
        """Compute Levenshtein similarity ratio in [0, 1]."""
        if left == right:
            return 1.0
        if not left or not right:
            return 0.0

        max_len = max(len(left), len(right))
        if max_len == 0:
            return 1.0

        distance = self._levenshtein_distance(left, right)
        return max(0.0, 1.0 - (distance / max_len))

    def _levenshtein_distance(self, left: str, right: str) -> int:
        """Compute Levenshtein edit distance between two strings."""
        if left == right:
            return 0
        if not left:
            return len(right)
        if not right:
            return len(left)

        previous_row = list(range(len(right) + 1))
        for i, left_char in enumerate(left, start=1):
            current_row = [i]
            for j, right_char in enumerate(right, start=1):
                insert_cost = current_row[j - 1] + 1
                delete_cost = previous_row[j] + 1
                substitute_cost = previous_row[j - 1] + (left_char != right_char)
                current_row.append(min(insert_cost, delete_cost, substitute_cost))
            previous_row = current_row

        return previous_row[-1]

    def _normalize_ipa(self, ipa_string: str) -> str:
        """
        Normalize an IPA string for consistent comparison.

        Args:
            ipa_string: The IPA string to normalize

        Returns:
            Normalized IPA string
        """
        # Remove any text that's not part of the IPA (common with model responses)
        # Look for brackets, slashes, or other common IPA delimiters
        ipa_markers = [
            (r"/(.+?)/", r"\1"),  # Extract content between /.../ slashes
            (r"\[(.+?)\]", r"\1"),  # Extract content between [...] brackets
            (r"\((.+?)\)", r"\1"),  # Extract content between (...) parentheses
        ]

        # Try to extract IPA from delimiters
        extracted = ipa_string
        for pattern, replacement in ipa_markers:
            match = re.search(pattern, ipa_string)
            if match:
                extracted = re.sub(pattern, replacement, ipa_string)
                break

        # Remove any surrounding whitespace and normalize Unicode composition.
        normalized = unicodedata.normalize("NFC", extracted.strip())

        # Normalize equivalent affricate tie-bar forms (e.g., t͡ɕ -> tɕ).
        # This keeps comparison robust across common IPA rendering variants.
        normalized = normalized.replace("͡", "").replace("͜", "")

        # Normalize syllable delimiters commonly emitted by models (e.g., bɔ̃.ʒuʁ).
        normalized = normalized.replace(".", "")


        # Remove any explanatory text before or after the IPA
        # This is a simple heuristic - we look for the longest contiguous segment with IPA-like characters
        ipa_chars = set("ɪiɛeæaɑɔoʊuʌəɚɝɜː̩̯̆͡ˌˈʰʷ.ptksʒʃθðŋnmɹrlvfbdgzʤʧywχѲ")
        segments = re.findall(r"[^\s,;:]+", normalized)
        if segments:
            # Find the segment with the highest percentage of IPA characters
            best_segment = max(
                segments,
                key=lambda s: (
                    sum(1 for c in s.lower() if c in ipa_chars) / len(s) if len(s) > 0 else 0
                ),
            )
            if (
                best_segment
                and sum(1 for c in best_segment.lower() if c in ipa_chars) / len(best_segment) > 0.5
            ):
                normalized = best_segment

        return normalized

    def _is_close_match(
        self, model_answer: str, correct_answer: str, threshold: float = 0.8
    ) -> bool:
        """
        Check if the model's answer is a close match to the correct answer.

        Args:
            model_answer: The model's IPA answer
            correct_answer: The correct IPA answer
            threshold: Similarity threshold (0-1)

        Returns:
            Boolean indicating whether the answers are close enough
        """
        # If either string is empty, they're not close
        if not model_answer or not correct_answer:
            return False

        # Allow slight symbol variation across broad/narrow transcriptions.
        similar_chars = {
            "i": set(["i", "ɪ", "iː"]),
            "ɪ": set(["ɪ", "i", "iː"]),
            "e": set(["e", "ɛ", "eɪ"]),
            "ɛ": set(["ɛ", "e", "eɪ"]),
            "æ": set(["æ", "a", "ɑ"]),
            "a": set(["a", "æ", "ɑ"]),
            "ɑ": set(["ɑ", "a", "æ", "ɒ"]),
            "ɒ": set(["ɒ", "ɑ", "o", "ɔ"]),
            "ɔ": set(["ɔ", "o", "ɒ"]),
            "o": set(["o", "ɔ", "ɒ", "oʊ"]),
            "u": set(["u", "ʊ", "uː"]),
            "ʊ": set(["ʊ", "u", "uː"]),
            "ʌ": set(["ʌ", "ə", "ɜ"]),
            "ə": set(["ə", "ʌ", "ɜ", "ɚ"]),
            "ɝ": set(["ɝ", "ɚ", "ɜ"]),
            "ɚ": set(["ɚ", "ɝ", "ə"]),
            "ɹ": set(["ɹ", "r"]),
            "r": set(["r", "ɹ"]),
            "t": set(["t", "ɾ"]),  # Especially for American English
            "ɾ": set(["ɾ", "t"]),
            # Common spirantization/lenition variants in broad transcriptions.
            "ɡ": set(["ɡ", "g", "ɣ"]),
            "g": set(["g", "ɡ", "ɣ"]),
            "ɣ": set(["ɣ", "ɡ", "g"]),
            "d": set(["d", "ð"]),
            "ð": set(["ð", "d"]),
            "b": set(["b", "β"]),
            "β": set(["β", "b"]),
            "ɲ": set(["ɲ", "n"]),
            "n": set(["n", "ɲ"]),
        }

        def substitution_cost(a: str, b: str) -> float:
            if a == b:
                return 0.0
            if a in similar_chars.get(b, set()) or b in similar_chars.get(a, set()):
                return 0.5
            return 1.0

        m, n = len(model_answer), len(correct_answer)
        if m == 0 or n == 0:
            return False

        # Weighted Levenshtein distance to tolerate insertions/deletions,
        # not just positionally-aligned substitutions.
        dp = [[0.0] * (n + 1) for _ in range(m + 1)]
        for i in range(1, m + 1):
            dp[i][0] = float(i)
        for j in range(1, n + 1):
            dp[0][j] = float(j)

        for i in range(1, m + 1):
            for j in range(1, n + 1):
                sub_cost = substitution_cost(model_answer[i - 1], correct_answer[j - 1])
                dp[i][j] = min(
                    dp[i - 1][j] + 1.0,  # deletion
                    dp[i][j - 1] + 1.0,  # insertion
                    dp[i - 1][j - 1] + sub_cost,  # substitution/match
                )

        max_len = max(m, n)
        similarity = 1.0 - (dp[m][n] / max_len)
        return similarity >= threshold

    def build_debug_info(self, question_data: Dict, response: Any, is_correct: bool) -> Dict:
        """Build debug information for benchmark results."""
        # Extract model's answer based on response type
        if (
            hasattr(response, "structured_data")
            and isinstance(response.structured_data, dict)
            and "ipa" in response.structured_data
        ):
            # Response object with structured data
            model_answer = response.structured_data["ipa"]
        elif isinstance(response, dict) and "ipa" in response:
            # Direct dictionary with ipa key
            model_answer = response["ipa"]
        elif hasattr(response, "response_text"):
            # Response object with text
            model_answer = response.response_text
        else:
            # Any other format
            model_answer = str(response)

        # Get the correct answer
        correct_answer = question_data.get("correct_answer", "")

        # Simplified debug info with just essential information
        return {"response": model_answer, "expected": correct_answer, "is_correct": is_correct}
