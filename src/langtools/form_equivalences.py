"""Grammatical form string normalization and equivalence checking.

Used by benchmarks and scoring logic to identify when two different form strings
refer to the same grammatical concept, accounting for:

- Language-specific case name aliases (e.g. Lithuanian "inessive" → "locative")
- Consistent component ordering conventions (canonical: case → number → gender)

Example usage::

    from langtools.form_equivalences import (
        normalize_grammatical_form,
        are_grammatical_forms_equivalent,
    )

    # Resolves alias and reorders components
    normalize_grammatical_form("noun/lt_singular_inessive")
    # -> "noun/lt_locative_singular"

    are_grammatical_forms_equivalent(
        "noun/lt_locative_singular", "noun/lt_inessive_singular"
    )
    # -> True
"""

import re
from typing import Dict, List, Optional, Tuple

from langtools.lt.case_equivalences import LT_CASE_ALIASES

# Language-specific case term aliases: {lang_code: {alias: canonical}}
_LANG_CASE_ALIASES: Dict[str, Dict[str, str]] = {
    "lt": LT_CASE_ALIASES,
}

# Component categories used for canonical ordering: case → number → gender
_NUMBER_TERMS: frozenset = frozenset({"singular", "plural"})
_GENDER_TERMS: frozenset = frozenset({"m", "f", "n"})


def _parse_form_string(form: str) -> Optional[Tuple[str, str, List[str]]]:
    """Parse a grammatical form string into (role, lang_code, components).

    E.g. ``"noun/lt_locative_singular"`` → ``("noun", "lt", ["locative", "singular"])``.

    Returns ``None`` when the string does not match the ``role/lang_...`` pattern.
    """
    match = re.match(r"^([a-z_]+)/([a-z]{2})_(.+)$", form)
    if not match:
        return None
    role = match.group(1)
    lang = match.group(2)
    components = match.group(3).split("_")
    return role, lang, components


def _normalize_components(lang: str, components: List[str]) -> List[str]:
    """Resolve aliases and sort components to canonical order.

    Canonical ordering: case/other terms → number terms → gender terms.

    Example for ``lt`` with alias ``inessive`` → ``locative``::

        ["singular", "inessive"] → ["locative", "singular"]
        ["singular", "locative", "f"] → ["locative", "singular", "f"]
    """
    aliases = _LANG_CASE_ALIASES.get(lang, {})
    resolved = [aliases.get(c, c) for c in components]

    number_parts = [c for c in resolved if c in _NUMBER_TERMS]
    gender_parts = [c for c in resolved if c in _GENDER_TERMS]
    other_parts = [c for c in resolved if c not in _NUMBER_TERMS and c not in _GENDER_TERMS]

    return other_parts + number_parts + gender_parts


def normalize_grammatical_form(form: str) -> str:
    """Normalize a grammatical form string to canonical terminology and ordering.

    Resolves language-specific case aliases and reorders components so that the
    result is always ``case_number`` (or ``case_number_gender`` for adjectives)
    regardless of the input ordering.

    Examples::

        normalize_grammatical_form("noun/lt_inessive_singular")
        # -> "noun/lt_locative_singular"

        normalize_grammatical_form("noun/lt_singular_inessive")
        # -> "noun/lt_locative_singular"

        normalize_grammatical_form("adjective/lt_singular_inessive_f")
        # -> "adjective/lt_locative_singular_f"

        normalize_grammatical_form("noun/lt_locative_singular")
        # -> "noun/lt_locative_singular"  (unchanged)

        normalize_grammatical_form("preposition/base")
        # -> "preposition/base"  (no lang prefix; returned as-is)
    """
    form_lower = form.strip().lower()
    parsed = _parse_form_string(form_lower)
    if parsed is None:
        return form_lower
    role, lang, components = parsed
    normalized = _normalize_components(lang, components)
    return f"{role}/{lang}_{'_'.join(normalized)}"


def are_grammatical_forms_equivalent(form1: str, form2: str) -> bool:
    """Return ``True`` if two grammatical form strings refer to the same form.

    Accounts for language-specific case aliases and component ordering so that,
    for example, a Lithuanian locative and an inessive label are recognised as
    identical.

    Examples::

        are_grammatical_forms_equivalent(
            "noun/lt_locative_singular", "noun/lt_inessive_singular"
        )  # True

        are_grammatical_forms_equivalent(
            "noun/lt_locative_singular", "noun/lt_singular_inessive"
        )  # True

        are_grammatical_forms_equivalent(
            "noun/lt_locative_singular", "noun/lt_genitive_singular"
        )  # False
    """
    return normalize_grammatical_form(form1) == normalize_grammatical_form(form2)
