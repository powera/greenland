"""Cross-language tokenization and lemma-matching dispatcher.

Two related jobs live here:

* **Tokenization** -- splitting running text into surface tokens.
* **Lemma matching** -- mapping a surface token back to the dictionary forms it
  could be an inflection of, so a sentence containing Spanish "canciones" or
  Lithuanian "namuose" can be linked to the stored lemma "canción" / "namas"
  even when that inflected form has no ``DerivativeForm`` row.

Each language that needs non-default behavior provides a
``langtools.<lang_code>.tokenizer`` module.  Every hook in it is optional:

* ``tokenize(text: str) -> List[str]`` -- languages without one fall back to
  whitespace splitting, which suits most space-delimited scripts.
* ``split_contractions(token: str) -> List[str]`` -- expand a fused or elided
  token into its words (French "du" -> ["de", "le"], "l'homme" -> ["le",
  "homme"]); returns ``[token]`` when nothing applies.
* ``candidate_lemmas(token: str) -> List[str]`` -- rule-based guesses at the
  dictionary forms behind an inflected token, most plausible first.

Lemma candidates over-generate by design; they are keys to look up against
stored lemmas, never answers on their own.  Dialects resolve to their base
language (es-419 -> es, zh-tw -> zh), since dialects inflect like their parent.
"""

import importlib
import logging
import re
import unicodedata
from functools import lru_cache
from typing import Callable, List, Optional, cast

from langtools.dialect_overrides import get_base_language

logger = logging.getLogger(__name__)

_TokenHook = Callable[[str], List[str]]

# Hooks a language tokenizer module may define.
_HOOK_NAMES = ("tokenize", "split_contractions", "candidate_lemmas")

# Typographic apostrophes folded to ASCII so elision rules need one spelling.
_APOSTROPHES = str.maketrans({"’": "'", "ʼ": "'", "‘": "'"})


@lru_cache(maxsize=None)
def _load_hook(base_language: str, hook_name: str) -> Optional[_TokenHook]:
    """Return a hook from ``langtools.<base>.tokenizer``, or None if absent."""
    module_path = f"langtools.{base_language}.tokenizer"
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        # Only the language module itself being absent means "no hooks"; a
        # missing dependency inside an existing module is a real error.
        if exc.name in (module_path, f"langtools.{base_language}"):
            return None
        raise
    fn = getattr(module, hook_name, None)
    if fn is None:
        return None
    if not callable(fn):
        logger.warning("%s.%s is not callable", module_path, hook_name)
        return None
    return cast(_TokenHook, fn)


def _hook(language_code: str, hook_name: str) -> Optional[_TokenHook]:
    """Resolve a hook for a (possibly dialect) language code."""
    if hook_name not in _HOOK_NAMES:
        raise ValueError(f"Unknown tokenizer hook: {hook_name}")
    base = get_base_language((language_code or "").strip().lower())
    if not base:
        return None
    return _load_hook(base, hook_name)


def _whitespace_tokenize(text: str) -> List[str]:
    """Tokenize by splitting on whitespace; punctuation stays attached."""
    return [token for token in re.split(r"\s+", text.strip()) if token]


def tokenize(text: str, language_code: str) -> List[str]:
    """Tokenize *text* using the appropriate strategy for *language_code*.

    Uses a language-specific ``tokenize`` hook when one is defined; otherwise
    falls back to whitespace splitting.
    """
    if not text.strip():
        return []
    fn = _hook(language_code, "tokenize")
    if fn is not None:
        return fn(text)
    return _whitespace_tokenize(text)


def _is_edge_punctuation(ch: str, *, keep_apostrophe: bool) -> bool:
    if keep_apostrophe and ch == "'":
        return False
    return unicodedata.category(ch).startswith("P") or unicodedata.category(ch) == "Sm"


def _strip_edges(token: str, *, keep_trailing_apostrophe: bool) -> str:
    start = 0
    end = len(token)
    while start < end and _is_edge_punctuation(token[start], keep_apostrophe=False):
        start += 1
    while end > start and _is_edge_punctuation(
        token[end - 1], keep_apostrophe=keep_trailing_apostrophe
    ):
        end -= 1
    return token[start:end]


def _normalize(token: str, *, keep_trailing_apostrophe: bool) -> str:
    folded = unicodedata.normalize("NFC", token).translate(_APOSTROPHES).strip().lower()
    return _strip_edges(folded, keep_trailing_apostrophe=keep_trailing_apostrophe)


def normalize_token(token: str) -> str:
    """NFC-normalize, lowercase, fold apostrophes and strip edge punctuation.

    This is the form every lemma-matching function below compares in.  Stored
    lemma translations are NFC; German nouns are capitalized in storage, so
    callers comparing against the database should compare case-insensitively.
    """
    return _normalize(token, keep_trailing_apostrophe=False)


def split_contractions(language_code: str, token: str) -> List[str]:
    """Expand a contracted or elided token into its component words.

    Args:
        language_code: Language of the token (dialects resolve to their base).
        token: One surface token; normalized here.

    Returns:
        The component words, normalized (French "du" -> ["de", "le"], Italian
        "dell'acqua" -> ["di", "lo", "acqua"]).  ``[token]`` when the language
        has no contraction rules or none apply; ``[]`` for an empty token.
    """
    # A trailing apostrophe marks elision ("l'" as its own token), so it
    # survives until the language hook has seen it.
    raw = _normalize(token, keep_trailing_apostrophe=True)
    if not raw:
        return []
    fn = _hook(language_code, "split_contractions")
    parts = fn(raw) if fn is not None else [raw]
    out: List[str] = []
    for part in parts:
        cleaned = normalize_token(part)
        if cleaned:
            out.append(cleaned)
    return out


def supports_lemma_candidates(language_code: str) -> bool:
    """True when the language defines rule-based ``candidate_lemmas``."""
    return _hook(language_code, "candidate_lemmas") is not None


def candidate_lemmas(language_code: str, token: str) -> List[str]:
    """Guess the dictionary forms an inflected token could have come from.

    Args:
        language_code: Language of the token (dialects resolve to their base).
        token: One surface token; normalized here.

    Returns:
        Normalized candidate lemma texts, most plausible first, without the
        token itself and without duplicates.  Empty when the language has no
        rules or none apply.  Candidates over-generate: callers must check them
        against stored lemmas.
    """
    normalized = normalize_token(token)
    if not normalized:
        return []
    fn = _hook(language_code, "candidate_lemmas")
    if fn is None:
        return []
    out: List[str] = []
    for candidate in fn(normalized):
        cleaned = normalize_token(candidate)
        if cleaned and cleaned != normalized and cleaned not in out:
            out.append(cleaned)
    return out


def lemma_lookup_keys(language_code: str, token: str) -> List[str]:
    """Every string worth looking up as a lemma for one surface token.

    The token itself first, then its contraction parts, then lemma candidates
    for the token and for each part.  This is the one-call entry point for
    callers that match tokens against stored lemma/derivative-form text.

    Args:
        language_code: Language of the token.
        token: One surface token; normalized here.

    Returns:
        De-duplicated normalized keys, most direct match first.
    """
    normalized = normalize_token(token)
    if not normalized:
        return []
    keys: List[str] = [normalized]

    def _add(key: str) -> None:
        if key and key not in keys:
            keys.append(key)

    parts = split_contractions(language_code, token)
    for part in parts:
        _add(part)
    for piece in [normalized, *parts]:
        for candidate in candidate_lemmas(language_code, piece):
            _add(candidate)
    return keys


def surface_matches_lemma(language_code: str, surface: str, lemma: str) -> bool:
    """True when *surface* is plausibly a form of *lemma*.

    A single-word surface matches when the lemma is one of its
    :func:`lemma_lookup_keys` (which include reflexive lemmas such as "se
    lever").  A multi-word surface matches a one-word lemma when any of its
    words does ("se quedó" -> "quedarse"), and a multi-word lemma of the same
    length word by word ("tomé una decisión" -> "tomar una decisión").  A
    lemma exactly equal to the surface always matches.

    Args:
        language_code: Language of both strings.
        surface: Surface text from a sentence, one or more words.
        lemma: Stored lemma text.

    Returns:
        Whether the surface can be linked to the lemma by rule.  False
        negatives remain for irregular forms the rules do not cover and for
        split constructions (German separable verbs).
    """
    surface_words = [normalize_token(word) for word in _whitespace_tokenize(surface)]
    lemma_words = [normalize_token(word) for word in _whitespace_tokenize(lemma)]
    surface_words = [word for word in surface_words if word]
    lemma_words = [word for word in lemma_words if word]
    if not surface_words or not lemma_words:
        return False
    if surface_words == lemma_words:
        return True
    if len(surface_words) == 1:
        # Candidates may themselves be multi-word: French "lève" yields the
        # reflexive lemma "se lever" as one key.
        return " ".join(lemma_words) in lemma_lookup_keys(language_code, surface_words[0])
    if len(lemma_words) == 1:
        # A one-word lemma inside a longer surface: "se quedó" -> "quedarse",
        # "in the evening" -> "evening".
        return any(
            lemma_words[0] in lemma_lookup_keys(language_code, word) for word in surface_words
        )
    if len(lemma_words) != len(surface_words):
        return False
    return all(
        surface_word == lemma_word or lemma_word in lemma_lookup_keys(language_code, surface_word)
        for surface_word, lemma_word in zip(surface_words, lemma_words)
    )
