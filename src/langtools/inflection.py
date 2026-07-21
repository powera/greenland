"""Cross-language rule-based inflection dispatcher.

Mirrors :mod:`langtools.tokenizer` and :mod:`langtools.verb_forms`: each
language exposing mechanical inflection provides a ``langtools.<code>.inflection``
module with any of ``build_noun_forms`` / ``build_adjective_forms`` /
``build_adverb_forms``.  Every builder returns ``None`` when it is not
confident, so callers fall back to the LLM.

Grammar facts (``countability``, ``gradability``, ``irregular_plural``, ...)
are lexical properties of the lemma, not derivable from spelling.  They are
supplied either as a ``grammar_facts`` dict or as keyword arguments; each
language consumes the ones its builder declares and the dispatcher drops the
rest, so a fact English models but Spanish ignores is not an error.
"""

from functools import lru_cache
from importlib import import_module
from inspect import Parameter, signature
from typing import Callable, Dict, Optional

_POS_TO_BUILDER: Dict[str, str] = {
    "noun": "build_noun_forms",
    "adjective": "build_adjective_forms",
    "adverb": "build_adverb_forms",
}


@lru_cache(maxsize=None)
def _load_builder(
    language_code: str, pos_type: str
) -> Optional[Callable[..., Optional[Dict[str, str]]]]:
    """Return the ``build_*_forms`` callable for a language/POS, or None."""
    builder_name = _POS_TO_BUILDER.get(pos_type)
    if builder_name is None:
        return None
    try:
        module = import_module(f"langtools.{language_code}.inflection")
    except ModuleNotFoundError:
        return None
    builder = getattr(module, builder_name, None)
    return builder if callable(builder) else None


def _accepted_kwargs(
    builder: Callable[..., object], grammar_facts: Dict[str, Optional[str]]
) -> Dict[str, Optional[str]]:
    """Keep only the facts this builder declares (all, if it takes ``**kwargs``)."""
    params = signature(builder).parameters
    if any(param.kind is Parameter.VAR_KEYWORD for param in params.values()):
        return grammar_facts
    return {name: value for name, value in grammar_facts.items() if name in params}


def inflect(
    lemma: str,
    language_code: str,
    pos_type: str,
    grammar_facts: Optional[Dict[str, Optional[str]]] = None,
    **kwargs: Optional[str],
) -> Optional[Dict[str, str]]:
    """Build mechanical inflected forms for *lemma*, or ``None`` if unsure.

    Args:
        lemma: The lemma text.
        language_code: Language code (e.g. ``"en"``).
        pos_type: Part of speech (``"noun"``, ``"adjective"``, ``"adverb"``).
        grammar_facts: Optional lexical grammar facts as a dict.  Merged with
            any keyword arguments, which take precedence on conflict.
        **kwargs: Grammar facts passed individually (e.g. ``countability=...``).

    Returns:
        A mapping of inflected forms, or ``None`` when the language/POS is
        unsupported or the rules are not confident.
    """
    builder = _load_builder(
        (language_code or "").strip().lower(),
        (pos_type or "").strip().lower(),
    )
    if builder is None:
        return None
    facts: Dict[str, Optional[str]] = {**(grammar_facts or {}), **kwargs}
    return builder(lemma, **_accepted_kwargs(builder, facts))
