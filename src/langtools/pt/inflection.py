"""Rule-based Portuguese noun/adjective inflection helpers."""

from typing import Dict, Optional


_NOUN_IRREGULAR_PLURALS: Dict[str, str] = {
    "cão": "cães",
    "mão": "mãos",
    "alemão": "alemães",
    "capitão": "capitães",
    "pão": "pães",
}

_ADJECTIVE_IRREGULAR_FEMININE: Dict[str, str] = {
    "bom": "boa",
    "mau": "má",
}

_ADJECTIVE_IRREGULAR_PLURALS: Dict[str, str] = {
    "bom": "bons",
    "boa": "boas",
    "mau": "maus",
    "má": "más",
}


def pluralize_noun(noun: str) -> Optional[str]:
    """Return a noun plural for common European Portuguese rules."""
    singular = noun.strip().lower()
    if not singular:
        return None

    irregular_plural = _NOUN_IRREGULAR_PLURALS.get(singular)
    if irregular_plural is not None:
        return irregular_plural

    if singular.endswith(("r", "z", "n")):
        return singular + "es"
    if singular.endswith("m"):
        return singular[:-1] + "ns"
    if singular.endswith("l"):
        return singular[:-1] + "is"
    if singular.endswith("ão"):
        return singular[:-2] + "ões"
    if singular.endswith(("s", "x")):
        return singular
    return singular + "s"


def build_noun_forms(noun: str) -> Optional[Dict[str, str]]:
    """Build singular/plural noun forms from a base singular noun."""
    singular = noun.strip().lower()
    if not singular:
        return None
    plural = pluralize_noun(singular)
    if plural is None:
        return None
    return {"singular": singular, "plural": plural}


def _adjective_feminine(singular_m: str) -> str:
    irregular_form = _ADJECTIVE_IRREGULAR_FEMININE.get(singular_m)
    if irregular_form is not None:
        return irregular_form
    if singular_m.endswith("o"):
        return singular_m[:-1] + "a"
    return singular_m


def _adjective_plural(base: str) -> str:
    irregular_form = _ADJECTIVE_IRREGULAR_PLURALS.get(base)
    if irregular_form is not None:
        return irregular_form

    if base.endswith(("r", "z", "n")):
        return base + "es"
    if base.endswith("m"):
        return base[:-1] + "ns"
    if base.endswith("l"):
        return base[:-1] + "is"
    if base.endswith("ão"):
        return base[:-2] + "ões"
    if base.endswith(("s", "x")):
        return base
    return base + "s"


def build_adjective_forms(adjective: str) -> Optional[Dict[str, str]]:
    """Build core adjective agreement forms (m/f × singular/plural)."""
    singular_m = adjective.strip().lower()
    if not singular_m:
        return None

    singular_f = _adjective_feminine(singular_m)
    plural_m = _adjective_plural(singular_m)
    plural_f = _adjective_plural(singular_f)

    return {
        "singular_m": singular_m,
        "singular_f": singular_f,
        "plural_m": plural_m,
        "plural_f": plural_f,
    }
