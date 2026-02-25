"""Grammatical form string normalization and equivalence checking.

Used by benchmarks and scoring logic to identify when two different form strings
refer to the same grammatical concept, accounting for:

- Language-specific case name aliases (e.g. Lithuanian "inessive" → "locative")
- Consistent component ordering conventions (canonical: case → number → gender)

Per-language aliases are defined in ``langtools/<lang>/case_equivalences.py``
as a module-level ``CASE_ALIASES`` dict.  The file is loaded on first use via
``importlib`` (bypassing the language package's ``__init__.py``) so that only
languages actually encountered in form strings incur any import cost.

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

import importlib.util
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Directory that contains per-language subdirectories (i.e. src/langtools/).
_LANGTOOLS_DIR = Path(__file__).parent

# Cache: lang_code -> alias dict (populated on first request per language).
_alias_cache: Dict[str, Dict[str, str]] = {}

# Component categories used for canonical ordering: case → number → gender
_NUMBER_TERMS: frozenset = frozenset({"singular", "plural"})
_GENDER_TERMS: frozenset = frozenset({"m", "f", "n"})


def _get_lang_aliases(lang: str) -> Dict[str, str]:
    """Return the case-alias map for *lang*, loading it lazily on first call.

    Reads ``langtools/<lang>/case_equivalences.py`` directly via
    ``importlib.util.spec_from_file_location`` so that the language
    package's ``__init__.py`` is never executed.  Languages with no alias
    file return an empty dict and are cached as such.
    """
    if lang in _alias_cache:
        return _alias_cache[lang]

    aliases: Dict[str, str] = {}
    alias_file = _LANGTOOLS_DIR / lang / "case_equivalences.py"
    if alias_file.exists():
        spec = importlib.util.spec_from_file_location(f"_form_alias_{lang}", alias_file)
        if spec is not None and spec.loader is not None:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore[union-attr]
            aliases = getattr(module, "CASE_ALIASES", {})

    _alias_cache[lang] = aliases
    return aliases


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
    aliases = _get_lang_aliases(lang)
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
