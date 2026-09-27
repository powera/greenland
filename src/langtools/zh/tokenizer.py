"""Chinese tokenizer (jieba word segmentation) and lemma-matching hook."""

import logging
from typing import List

logger = logging.getLogger(__name__)

try:
    import jieba

    _JIEBA_AVAILABLE = True
except ImportError:
    _JIEBA_AVAILABLE = False
    logger.warning(
        "jieba not available - Chinese tokenization will fall back to character-by-character"
    )


# Aspect particles and the personal plural, written onto the word they modify
# when jieba keeps them together: 吃了 -> 吃, 朋友们 -> 朋友.
_ATTACHED_SUFFIXES = ("了", "过", "着", "们")

# Adjectives are stored with attributive 的 (正确的), but running text often
# uses them predicatively or adverbially (很正确, 正确地).
_ATTRIBUTIVE = "的"
_ADVERBIAL = "地"

_NEGATIONS = ("不", "没")


def tokenize(text: str) -> List[str]:
    """Tokenize Chinese text into words using jieba.

    Falls back to character-by-character if jieba is unavailable.
    Filters empty tokens.
    """
    if _JIEBA_AVAILABLE:
        return [token for token in jieba.cut(text, cut_all=False) if token.strip()]
    # Character-by-character fallback
    return [char for char in text if char.strip()]


def candidate_lemmas(token: str) -> List[str]:
    """Guess the stored lemma behind a segmented Chinese token.

    Chinese does not inflect, so the misses are segmentation mismatches rather
    than morphology: a particle jieba left attached (吃了), an adjective stored
    with 的 but written without it, reduplication (看看, 试一试), fused negation
    (不好), or a compound the stored lemma is part of (好朋友 contains 朋友).
    Compound parts come from jieba's search-mode segmentation and are kept only
    at two or more characters: single-character matches are what drowned the
    old substring matching in noise.
    """
    candidates: List[str] = []

    def _add(candidate: str) -> None:
        if candidate and candidate != token and candidate not in candidates:
            candidates.append(candidate)

    if len(token) >= 2 and token.endswith(_ATTACHED_SUFFIXES):
        _add(token[:-1])
    if token.endswith((_ATTRIBUTIVE, _ADVERBIAL)):
        if len(token) >= 2:
            _add(token[:-1])
            _add(token[:-1] + _ATTRIBUTIVE)
    else:
        _add(token + _ATTRIBUTIVE)
    if len(token) == 2 and token[0] == token[1]:
        _add(token[0])
    if len(token) == 3 and token[1] == "一" and token[0] == token[2]:
        _add(token[0])
    if 2 <= len(token) <= 4 and token.startswith(_NEGATIONS):
        _add(token[1:])
    if _JIEBA_AVAILABLE and len(token) >= 3:
        for part in jieba.cut_for_search(token):
            if len(part) >= 2:
                _add(part)
    return candidates
