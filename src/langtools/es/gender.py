"""Spanish noun gender predicted from the ending.

This is a cross-check, not a source of facts.  Gender is stored as a
``grammatical_gender`` grammar fact decided by the LLM (see
``words.grammar_fact_tasks.grammatical_gender``); the prediction here only
flags an LLM answer that contradicts a reliable ending, so a reviewer can look
at it.

Only endings that are right for nearly every noun are listed.  Anything else
returns ``None`` -- a missing prediction costs nothing, while a wrong one sends
a correct fact to review.
"""

from typing import Optional, Set, Tuple

# Feminine suffixes with essentially no exceptions among common nouns.
_FEMININE_ENDINGS: Tuple[str, ...] = ("ción", "sión", "dad", "tad", "tud", "umbre", "itis")

# Masculine suffixes, each with a short exception list below.
_MASCULINE_ENDINGS: Tuple[str, ...] = ("aje", "or", "o")

# -o nouns that are feminine (mostly clipped forms: la foto(grafía)).
_FEMININE_O: Set[str] = {"mano", "foto", "moto", "radio", "libido", "seo", "dinamo", "nao"}

# -or nouns that are feminine.
_FEMININE_OR: Set[str] = {"flor", "labor", "coliflor", "sor"}

# -a nouns that are masculine.  -ma (el problema, but la cama) and -ista
# (el/la artista) are left out of the -a rule altogether.
_MASCULINE_A: Set[str] = {
    "día",
    "mapa",
    "planeta",
    "cometa",
    "poeta",
    "atleta",
    "tranvía",
    "papa",
    "profeta",
    "pirata",
    "guardia",
    "policía",
}


def _head_noun(noun: str) -> Optional[str]:
    """Return the head of *noun*: the first word, since Spanish is head-first.

    Capitalised input (a proper noun or brand, "Keytruda") has no predictable
    gender and returns ``None``.
    """
    text = noun.strip()
    if not text or text[0].isupper():
        return None
    head = text.split()[0]
    return head if head.isalpha() else None


def predict_gender(noun: str) -> Optional[str]:
    """Return ``"masculine"`` or ``"feminine"`` for a reliable ending, else ``None``."""
    head = _head_noun(noun)
    if head is None:
        return None

    if head.endswith(_FEMININE_ENDINGS):
        return "feminine"

    if head.endswith(_MASCULINE_ENDINGS):
        if head in _FEMININE_O or head in _FEMININE_OR:
            return "feminine"
        return "masculine"

    if head.endswith("a") and not head.endswith(("ma", "ista")):
        if head in _MASCULINE_A:
            return "masculine"
        return "feminine"

    return None
