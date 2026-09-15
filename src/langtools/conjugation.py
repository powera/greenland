"""Cross-language rule-based verb conjugation dispatcher.

Mirrors :mod:`langtools.inflection`: each language exposing mechanical
conjugation provides a ``langtools.<code>.conjugation`` module with a
``conjugate`` function taking the infinitive/lemma as its first argument and
returning the full person/tense table, or ``None`` when not confident.

A language whose dialects conjugate differently may also provide
``conjugate_for_dialect(lemma, language_code, ...)``, which the dispatcher
prefers and hands the *unresolved* code: es-419 needs to know it is es-419, not
that its parent is es.

Some languages need extra base forms that cannot be derived from the
infinitive (Lithuanian's ``present_3`` / ``past_3``, for example).  These are
supplied as a ``grammar_facts`` dict or as keyword arguments; the dispatcher
passes through only the ones the language's ``conjugate`` declares.  When a
language requires a base form that was not supplied, it yields ``None`` rather
than raising, so callers can fall back to the LLM.
"""

from functools import lru_cache
from importlib import import_module
from inspect import Parameter, signature
from typing import Callable, Dict, Optional

from langtools.dialect_overrides import get_base_language


@lru_cache(maxsize=None)
def _load_conjugator(
    language_code: str,
) -> Optional[Callable[..., Optional[Dict[str, str]]]]:
    """Return the ``conjugate`` callable for a language, or None if unavailable."""
    # A dialect conjugates like its parent (pt-br -> pt), and langtools has no
    # per-dialect packages.
    try:
        module = import_module(f"langtools.{get_base_language(language_code)}.conjugation")
    except ModuleNotFoundError:
        return None
    conjugator = getattr(module, "conjugate", None)
    return conjugator if callable(conjugator) else None


@lru_cache(maxsize=None)
def _load_dialect_conjugator(
    language_code: str,
) -> Optional[Callable[..., Optional[Dict[str, str]]]]:
    """Return the language's dialect-aware ``conjugate_for_dialect``, if it has one."""
    try:
        module = import_module(f"langtools.{get_base_language(language_code)}.conjugation")
    except ModuleNotFoundError:
        return None
    conjugator = getattr(module, "conjugate_for_dialect", None)
    return conjugator if callable(conjugator) else None


def _accepted_kwargs(
    conjugator: Callable[..., object],
    grammar_facts: Dict[str, Optional[str]],
    skip_positional: int = 1,
) -> Dict[str, Optional[str]]:
    """Keep only the facts this conjugator declares, skipping its positional args."""
    params = list(signature(conjugator).parameters.values())
    if any(param.kind is Parameter.VAR_KEYWORD for param in params):
        return grammar_facts
    accepted_names = {param.name for param in params[skip_positional:]}
    return {name: value for name, value in grammar_facts.items() if name in accepted_names}


def conjugate(
    lemma: str,
    language_code: str,
    grammar_facts: Optional[Dict[str, Optional[str]]] = None,
    **kwargs: Optional[str],
) -> Optional[Dict[str, str]]:
    """Conjugate *lemma* mechanically, or return ``None`` if unsupported/unsure.

    Args:
        lemma: The infinitive / lemma text.
        language_code: Language code (e.g. ``"en"``).
        grammar_facts: Optional extra base forms as a dict (e.g.
            ``{"present_3": ..., "past_3": ...}``).  Merged with keyword
            arguments, which take precedence on conflict.
        **kwargs: Extra base forms passed individually.

    Returns:
        The person/tense conjugation table, or ``None`` when the language is
        unsupported, a required base form is missing, or the rules are not
        confident.
    """
    normalized_code = (language_code or "").strip().lower()
    facts: Dict[str, Optional[str]] = {**(grammar_facts or {}), **kwargs}

    dialect_conjugator = _load_dialect_conjugator(normalized_code)
    if dialect_conjugator is not None:
        # Takes the code as its second positional argument, so the facts it
        # accepts start one parameter later.
        accepted = _accepted_kwargs(dialect_conjugator, facts, skip_positional=2)
        try:
            return dialect_conjugator(lemma, normalized_code, **accepted)
        except TypeError:
            return None

    conjugator = _load_conjugator(normalized_code)
    if conjugator is None:
        return None
    try:
        return conjugator(lemma, **_accepted_kwargs(conjugator, facts))
    except TypeError:
        # A required base form (e.g. Lithuanian present_3/past_3) was not
        # supplied; defer to the caller's fallback rather than raising.
        return None
