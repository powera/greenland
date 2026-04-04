"""Chinese tokenizer using jieba word segmentation."""

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


def tokenize(text: str) -> List[str]:
    """Tokenize Chinese text into words using jieba.

    Falls back to character-by-character if jieba is unavailable.
    Filters empty tokens.
    """
    if _JIEBA_AVAILABLE:
        return [token for token in jieba.cut(text, cut_all=False) if token.strip()]
    # Character-by-character fallback
    return [char for char in text if char.strip()]
