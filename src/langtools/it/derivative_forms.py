"""Rule-based Italian noun/adjective derivative form generation."""

from typing import Dict, Optional

_IRREGULAR_NOUN_PLURALS: Dict[str, str] = {
    "uomo": "uomini",
    "uovo": "uova",
    "dio": "dei",
    "mano": "mani",
}

_IRREGULAR_ADJECTIVES: Dict[str, Dict[str, str]] = {
    "buono": {
        "singular_m": "buono",
        "singular_f": "buona",
        "plural_m": "buoni",
        "plural_f": "buone",
    },
    "bello": {
        "singular_m": "bello",
        "singular_f": "bella",
        "plural_m": "belli",
        "plural_f": "belle",
    },
}


def derive_noun_forms(noun: str, explicit_plural: Optional[str] = None) -> Optional[Dict[str, str]]:
    """Return singular/plural noun forms using common Italian inflection rules."""
    singular_form = noun.strip().lower()
    if not singular_form:
        return None

    if explicit_plural:
        plural_form = explicit_plural.strip().lower()
    elif singular_form in _IRREGULAR_NOUN_PLURALS:
        plural_form = _IRREGULAR_NOUN_PLURALS[singular_form]
    elif singular_form.endswith("o"):
        plural_form = singular_form[:-1] + "i"
    elif singular_form.endswith("a"):
        plural_form = singular_form[:-1] + "e"
    elif singular_form.endswith("e"):
        plural_form = singular_form[:-1] + "i"
    else:
        plural_form = singular_form

    return {"singular": singular_form, "plural": plural_form}


def derive_adjective_forms(adjective: str) -> Optional[Dict[str, str]]:
    """Return m/f and singular/plural adjective forms for standard patterns."""
    adjective_value = adjective.strip().lower()
    if not adjective_value:
        return None

    if adjective_value in _IRREGULAR_ADJECTIVES:
        return dict(_IRREGULAR_ADJECTIVES[adjective_value])

    if adjective_value.endswith("o"):
        stem = adjective_value[:-1]
        return {
            "singular_m": adjective_value,
            "singular_f": f"{stem}a",
            "plural_m": f"{stem}i",
            "plural_f": f"{stem}e",
        }

    if adjective_value.endswith("e"):
        stem = adjective_value[:-1]
        return {
            "singular_m": adjective_value,
            "singular_f": adjective_value,
            "plural_m": f"{stem}i",
            "plural_f": f"{stem}i",
        }

    return {
        "singular_m": adjective_value,
        "singular_f": adjective_value,
        "plural_m": adjective_value,
        "plural_f": adjective_value,
    }
