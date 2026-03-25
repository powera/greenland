"""Utilities for IPA normalization and comparison."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import cast

_IPA_CHARS_PATH = Path(__file__).with_name("ipa_chars.json")
_IPA_CHARS_RAW = json.loads(_IPA_CHARS_PATH.read_text(encoding="utf-8"))["chars"]
_IPA_CHARS: frozenset[str] = frozenset(cast(list[str], _IPA_CHARS_RAW))

_SIMILAR_CHARS_BASE: dict[str, set[str]] = {
    "i": {"i", "ɪ"},
    "ɪ": {"ɪ", "i"},
    "e": {"e", "ɛ"},
    "ɛ": {"ɛ", "e"},
    "æ": {"æ", "a", "ɑ"},
    "a": {"a", "æ", "ɑ"},
    "ɑ": {"ɑ", "a", "æ", "ɒ"},
    "ɒ": {"ɒ", "ɑ", "o", "ɔ"},
    "ɔ": {"ɔ", "o", "ɒ"},
    "o": {"o", "ɔ", "ɒ"},
    "u": {"u", "ʊ"},
    "ʊ": {"ʊ", "u"},
    "ʌ": {"ʌ", "ə", "ɜ"},
    "ə": {"ə", "ʌ", "ɜ", "ɚ"},
    "ɝ": {"ɝ", "ɚ", "ɜ"},
    "ɚ": {"ɚ", "ɝ", "ə"},
    "ɹ": {"ɹ", "r"},
    "r": {"r", "ɹ"},
    "t": {"t", "ɾ"},
    "ɾ": {"ɾ", "t"},
    "ɡ": {"ɡ", "g", "ɣ"},
    "g": {"g", "ɡ", "ɣ"},
    "ɣ": {"ɣ", "ɡ", "g"},
    "d": {"d", "ð"},
    "ð": {"ð", "d"},
    "b": {"b", "β"},
    "β": {"β", "b"},
    "ɲ": {"ɲ", "n"},
    "n": {"n", "ɲ"},
}


def normalize_ipa(ipa_value: str) -> str:
    """Normalize an IPA string for robust comparison."""
    ipa_markers: list[tuple[str, str]] = [
        (r"/(.+?)/", r"\1"),
        (r"\[(.+?)\]", r"\1"),
        (r"\((.+?)\)", r"\1"),
    ]

    extracted = ipa_value
    for pattern, replacement in ipa_markers:
        marker_match = re.search(pattern, ipa_value)
        if marker_match:
            extracted = re.sub(pattern, replacement, ipa_value)
            break

    normalized = unicodedata.normalize("NFC", extracted.strip())
    normalized = normalized.replace("͡", "").replace("͜", "")
    normalized = normalized.replace(".", "")

    segments: list[str] = re.findall(r"[^\s,;:]+", normalized)
    if not segments:
        return normalized

    def ipa_ratio(segment: str) -> float:
        if not segment:
            return 0.0
        known_chars = sum(1 for character in segment.lower() if character in _IPA_CHARS)
        return known_chars / len(segment)

    best_segment = max(segments, key=ipa_ratio)
    if best_segment and ipa_ratio(best_segment) > 0.5:
        return best_segment

    return normalized


def weighted_similarity_ratio(left: str, right: str) -> float:
    """Compute a phonetic-weighted Levenshtein similarity ratio in [0, 1]."""
    if left == right:
        return 1.0
    if not left or not right:
        return 0.0

    left_length, right_length = len(left), len(right)
    max_length = max(left_length, right_length)

    def substitution_cost(left_char: str, right_char: str) -> float:
        if left_char == right_char:
            return 0.0
        left_matches = _SIMILAR_CHARS_BASE.get(left_char, set())
        right_matches = _SIMILAR_CHARS_BASE.get(right_char, set())
        if left_char in right_matches or right_char in left_matches:
            return 0.5
        return 1.0

    distance_matrix: list[list[float]] = [
        [0.0] * (right_length + 1) for _ in range(left_length + 1)
    ]
    for left_index in range(1, left_length + 1):
        distance_matrix[left_index][0] = float(left_index)
    for right_index in range(1, right_length + 1):
        distance_matrix[0][right_index] = float(right_index)

    for left_index in range(1, left_length + 1):
        for right_index in range(1, right_length + 1):
            replace_cost = substitution_cost(left[left_index - 1], right[right_index - 1])
            distance_matrix[left_index][right_index] = min(
                distance_matrix[left_index - 1][right_index] + 1.0,
                distance_matrix[left_index][right_index - 1] + 1.0,
                distance_matrix[left_index - 1][right_index - 1] + replace_cost,
            )

    return max(0.0, 1.0 - (distance_matrix[left_length][right_length] / max_length))


def are_ipa_equivalent(model_ipa: str, reference_ipa: str, threshold: float = 0.8) -> bool:
    """Return whether two IPA strings are equivalent after normalization."""
    normalized_model = normalize_ipa(model_ipa)
    normalized_reference = normalize_ipa(reference_ipa)

    if not normalized_model or not normalized_reference:
        return False
    if normalized_model == normalized_reference:
        return True

    similarity = weighted_similarity_ratio(normalized_model, normalized_reference)
    return similarity >= threshold


def is_ipa_levenshtein_match(model_ipa: str, reference_ipa: str, threshold: float = 0.8) -> bool:
    """Alias for weighted-Levenshtein IPA matching semantics."""
    return are_ipa_equivalent(model_ipa=model_ipa, reference_ipa=reference_ipa, threshold=threshold)
