"""Cross-language tokenizer dispatcher.

Each language that needs non-default tokenization provides a
``langtools.<lang_code>.tokenizer`` module with a ``tokenize(text: str) -> List[str]``
function.

Languages without a dedicated module fall back to whitespace splitting,
which is appropriate for most space-delimited scripts (en, fr, lt, de, …).
"""

import importlib
import logging
from typing import cast
import re
from functools import lru_cache
from typing import Callable, List, Optional

from langtools.dialect_overrides import get_base_language

logger = logging.getLogger(__name__)

# Languages with dedicated tokenizer modules.
_LANGUAGE_MODULE_PATHS: dict[str, str] = {
    "zh": "langtools.zh.tokenizer",
    "ja": "langtools.ja.tokenizer",
    "ko": "langtools.ko.tokenizer",
}


@lru_cache(maxsize=None)
def _load_tokenize_fn(language_code: str) -> Callable[[str], List[str]] | None:
    """Return the tokenize() function for a language module, or None if unavailable."""
    # zh-tw tokenizes with the zh segmenter; there is no per-dialect module.
    module_path = _LANGUAGE_MODULE_PATHS.get(get_base_language(language_code))
    if module_path is None:
        return None
    try:
        module = importlib.import_module(module_path)
        fn = getattr(module, "tokenize", None)
        if callable(fn):
            return cast(Callable[[str], List[str]], fn)
        logger.warning("Module %s has no callable tokenize()", module_path)
        return None
    except ImportError:
        logger.warning("Tokenizer module %s not available", module_path)
        return None


def _whitespace_tokenize(text: str) -> List[str]:
    """Tokenize by splitting on whitespace and stripping punctuation boundaries."""
    return [token for token in re.split(r"\s+", text.strip()) if token]


def tokenize(text: str, language_code: str) -> List[str]:
    """Tokenize *text* using the appropriate strategy for *language_code*.

    Uses a language-specific tokenizer module when one is registered;
    otherwise falls back to whitespace splitting.
    """
    if not text.strip():
        return []
    fn = _load_tokenize_fn(language_code.strip().lower())
    if fn is not None:
        return fn(text)
    return _whitespace_tokenize(text)
