#!/usr/bin/python3

"""Deterministic heuristic cognate detection.

Operational definition used here:
- A "cognate" is treated as a likely shared-origin/shared-form pair based on
  orthographic and phonetic similarity after lightweight normalization.
- This is intentionally a heuristic signal for large-scale processing loops,
  not a full historical-etymology proof.

This module is pure and deterministic (no DB/LLM calls).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence


@dataclass(frozen=True)
class CognateResult:
    """Heuristic cognate decision with feature scores and reason codes."""

    source_word: str
    target_word: str
    source_lang: str
    target_lang: str
    normalized_source: str
    normalized_target: str
    score: float
    threshold: float
    is_cognate: bool
    levenshtein_similarity: float
    lcs_ratio: float
    prefix_ratio: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class CognateConfig:
    """Per-language normalization and scoring rules.

    Rules are keyed only by language code and applied independently to source
    and target words, keeping configuration linear in number of languages.
    """

    language_suffix_rules: Mapping[str, Sequence[str]]
    language_orthography_rules: Mapping[str, Sequence[tuple[str, str]]]
    feature_weights: Mapping[str, float]
    threshold: float = 0.62


_KANA_ROMAJI_MAP: Mapping[str, str] = {
    "あ": "a",
    "い": "i",
    "う": "u",
    "え": "e",
    "お": "o",
    "か": "ka",
    "き": "ki",
    "く": "ku",
    "け": "ke",
    "こ": "ko",
    "さ": "sa",
    "し": "shi",
    "す": "su",
    "せ": "se",
    "そ": "so",
    "た": "ta",
    "ち": "chi",
    "つ": "tsu",
    "て": "te",
    "と": "to",
    "な": "na",
    "に": "ni",
    "ぬ": "nu",
    "ね": "ne",
    "の": "no",
    "は": "ha",
    "ひ": "hi",
    "ふ": "fu",
    "へ": "he",
    "ほ": "ho",
    "ま": "ma",
    "み": "mi",
    "む": "mu",
    "め": "me",
    "も": "mo",
    "や": "ya",
    "ゆ": "yu",
    "よ": "yo",
    "ら": "ra",
    "り": "ri",
    "る": "ru",
    "れ": "re",
    "ろ": "ro",
    "わ": "wa",
    "を": "o",
    "ん": "n",
}

_BASIC_ZH_ROMANIZATION_MAP: Mapping[str, str] = {
    "中": "zhong",
    "国": "guo",
    "學": "xue",
    "学": "xue",
    "語": "yu",
    "语": "yu",
    "人": "ren",
    "水": "shui",
    "火": "huo",
    "木": "mu",
}

_BASIC_UK_ROMANIZATION_MAP: Mapping[str, str] = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "h",
    "ґ": "g",
    "д": "d",
    "е": "e",
    "є": "ye",
    "ж": "zh",
    "з": "z",
    "и": "y",
    "і": "i",
    "ї": "yi",
    "й": "i",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ь": "",
    "ю": "yu",
    "я": "ya",
}

DEFAULT_COGNATE_CONFIG = CognateConfig(
    language_suffix_rules={
        "lt": ("as", "is", "us", "a", "ė", "ija"),
        "en": ("ion", "ity", "al", "ic", "ism", "ist", "y"),
        "es": ("cion", "sion", "dad", "ista", "ico", "ica"),
        "fr": ("tion", "ite", "isme", "iste"),
        "de": ("ung", "keit", "heit", "ismus"),
        "it": ("zione", "ita", "ismo", "ista"),
        "pt": ("cao", "dade", "ismo", "ista"),
        "ro": ("tie", "tate", "ism", "ist"),
        "uk": ("ist", "iya"),
        "zh": (),
        "ja": (),
    },
    language_orthography_rules={
        "lt": (("š", "s"), ("č", "c"), ("ž", "z"), ("y", "i")),
        "en": (("ph", "f"), ("qu", "k")),
        "es": (("qu", "k"), ("ll", "y"), ("h", "")),
        "fr": (("qu", "k"), ("ph", "f"), ("eau", "o")),
        "de": (("sch", "s"), ("z", "ts"), ("ä", "a"), ("ö", "o"), ("ü", "u")),
        "it": (("ch", "k"), ("gh", "g"), ("gl", "l")),
        "pt": (("ç", "c"), ("nh", "n"), ("lh", "l")),
        "ro": (("ț", "t"), ("ș", "s"), ("â", "a"), ("ă", "a")),
        "uk": (("ї", "i"), ("й", "i"), ("є", "e"), ("ґ", "g")),
        "zh": (),
        "ja": (),
    },
    feature_weights={"levenshtein": 0.45, "lcs": 0.35, "prefix": 0.20},
)


class LemmaLike(Protocol):
    lemma_text: str


def detect_cognate(
    source_word: str,
    target_word: str,
    source_lang: str,
    target_lang: str,
    *,
    config: CognateConfig = DEFAULT_COGNATE_CONFIG,
) -> CognateResult:
    reasons: list[str] = []
    source_code = source_lang.lower()
    target_code = target_lang.lower()

    normalized_source = _normalize_base(source_word, source_code)
    normalized_target = _normalize_base(target_word, target_code)

    source_after_affixes = _strip_suffix(
        normalized_source, config.language_suffix_rules.get(source_code, ())
    )
    target_after_affixes = _strip_suffix(
        normalized_target, config.language_suffix_rules.get(target_code, ())
    )
    if source_after_affixes != normalized_source or target_after_affixes != normalized_target:
        reasons.append("affix_rule_applied")

    source_after_orthography = _apply_orthography_rules(
        source_after_affixes, config.language_orthography_rules.get(source_code, ())
    )
    target_after_orthography = _apply_orthography_rules(
        target_after_affixes, config.language_orthography_rules.get(target_code, ())
    )
    if (
        source_after_orthography != source_after_affixes
        or target_after_orthography != target_after_affixes
    ):
        reasons.append("orthography_rule_applied")

    levenshtein_similarity = 1.0 - _normalized_levenshtein(
        source_after_orthography, target_after_orthography
    )
    lcs_ratio = _lcs_ratio(source_after_orthography, target_after_orthography)
    prefix_ratio = _prefix_ratio(source_after_orthography, target_after_orthography)

    score = (
        config.feature_weights["levenshtein"] * levenshtein_similarity
        + config.feature_weights["lcs"] * lcs_ratio
        + config.feature_weights["prefix"] * prefix_ratio
    )

    if levenshtein_similarity >= 0.8:
        reasons.append("high_levenshtein_similarity")
    if lcs_ratio >= 0.75:
        reasons.append("high_lcs_ratio")
    if prefix_ratio >= 0.7:
        reasons.append("high_prefix_similarity")

    is_cognate = score >= config.threshold
    reasons.append("above_threshold" if is_cognate else "below_threshold")

    return CognateResult(
        source_word=source_word,
        target_word=target_word,
        source_lang=source_lang,
        target_lang=target_lang,
        normalized_source=source_after_orthography,
        normalized_target=target_after_orthography,
        score=score,
        threshold=config.threshold,
        is_cognate=is_cognate,
        levenshtein_similarity=levenshtein_similarity,
        lcs_ratio=lcs_ratio,
        prefix_ratio=prefix_ratio,
        reasons=tuple(reasons),
    )


def detect_cognate_for_lemmas(
    source_lemma: LemmaLike,
    target_lemma: LemmaLike,
    source_lang: str,
    target_lang: str,
    *,
    config: CognateConfig = DEFAULT_COGNATE_CONFIG,
) -> CognateResult:
    return detect_cognate(
        source_lemma.lemma_text, target_lemma.lemma_text, source_lang, target_lang, config=config
    )


def _normalize_base(raw_text: str, language_code: str) -> str:
    romanized_text = _romanize_if_needed(raw_text, language_code)
    normalized_text = unicodedata.normalize("NFKD", romanized_text).casefold()
    text_without_marks = "".join(
        character for character in normalized_text if not unicodedata.combining(character)
    )
    return re.sub(r"[\W_]+", "", text_without_marks, flags=re.UNICODE)


def _romanize_if_needed(raw_text: str, language_code: str) -> str:
    if language_code == "ja":
        return "".join(
            _KANA_ROMAJI_MAP.get(character, character)
            for character in _katakana_to_hiragana(raw_text)
        )
    if language_code == "zh":
        return "".join(
            _BASIC_ZH_ROMANIZATION_MAP.get(character, character) for character in raw_text
        )
    if language_code == "uk":
        return "".join(
            _BASIC_UK_ROMANIZATION_MAP.get(character, character) for character in raw_text
        )
    return raw_text


def _katakana_to_hiragana(raw_text: str) -> str:
    output_chars: list[str] = []
    for character in raw_text:
        codepoint = ord(character)
        if 0x30A1 <= codepoint <= 0x30F6:
            output_chars.append(chr(codepoint - 0x60))
        else:
            output_chars.append(character)
    return "".join(output_chars)


def _strip_suffix(word: str, suffixes: Sequence[str]) -> str:
    output_word = word
    for suffix in sorted(suffixes, key=len, reverse=True):
        if len(output_word) <= len(suffix) + 2:
            continue
        if output_word.endswith(suffix):
            output_word = output_word[: -len(suffix)]
            break
    return output_word


def _apply_orthography_rules(word: str, rules: Sequence[tuple[str, str]]) -> str:
    output_word = word
    for from_pattern, to_pattern in rules:
        output_word = output_word.replace(from_pattern, to_pattern)
    return output_word


def _normalized_levenshtein(left: str, right: str) -> float:
    if not left and not right:
        return 0.0
    if not left or not right:
        return 1.0
    previous_row = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current_row = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            insertion_cost = current_row[right_index - 1] + 1
            deletion_cost = previous_row[right_index] + 1
            substitution_cost = previous_row[right_index - 1] + (left_char != right_char)
            current_row.append(min(insertion_cost, deletion_cost, substitution_cost))
        previous_row = current_row
    return previous_row[-1] / max(len(left), len(right))


def _lcs_ratio(left: str, right: str) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    rows = len(left) + 1
    columns = len(right) + 1
    matrix = [[0] * columns for _ in range(rows)]
    for left_index in range(1, rows):
        for right_index in range(1, columns):
            if left[left_index - 1] == right[right_index - 1]:
                matrix[left_index][right_index] = matrix[left_index - 1][right_index - 1] + 1
            else:
                matrix[left_index][right_index] = max(
                    matrix[left_index - 1][right_index], matrix[left_index][right_index - 1]
                )
    return matrix[-1][-1] / max(len(left), len(right))


def _prefix_ratio(left: str, right: str) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    prefix_length = 0
    for left_char, right_char in zip(left, right):
        if left_char != right_char:
            break
        prefix_length += 1
    return prefix_length / max(len(left), len(right))
