"""Rule-based French adjective inflection helpers.

French adjectives agree with their noun in gender and number.  This module
handles a small table of common irregular adjectives plus the high-confidence
regular endings (-e, -eux, -er, -f, vowel, -t, -d).  Endings whose feminine is
unpredictable (e.g. -s, -x, -l, -n, -c, -on, -eur) return ``None`` so the caller
can fall back to the LLM.
"""

from typing import Dict, Optional

# Masculine singular → full agreement table for irregular adjectives.
_IRREGULAR: Dict[str, Dict[str, str]] = {
    "beau": {
        "singular_m": "beau",
        "singular_f": "belle",
        "plural_m": "beaux",
        "plural_f": "belles",
    },
    "nouveau": {
        "singular_m": "nouveau",
        "singular_f": "nouvelle",
        "plural_m": "nouveaux",
        "plural_f": "nouvelles",
    },
    "vieux": {
        "singular_m": "vieux",
        "singular_f": "vieille",
        "plural_m": "vieux",
        "plural_f": "vieilles",
    },
    "fou": {"singular_m": "fou", "singular_f": "folle", "plural_m": "fous", "plural_f": "folles"},
    "mou": {"singular_m": "mou", "singular_f": "molle", "plural_m": "mous", "plural_f": "molles"},
    "blanc": {
        "singular_m": "blanc",
        "singular_f": "blanche",
        "plural_m": "blancs",
        "plural_f": "blanches",
    },
    "sec": {"singular_m": "sec", "singular_f": "sèche", "plural_m": "secs", "plural_f": "sèches"},
    "doux": {"singular_m": "doux", "singular_f": "douce", "plural_m": "doux", "plural_f": "douces"},
    "faux": {
        "singular_m": "faux",
        "singular_f": "fausse",
        "plural_m": "faux",
        "plural_f": "fausses",
    },
    "roux": {
        "singular_m": "roux",
        "singular_f": "rousse",
        "plural_m": "roux",
        "plural_f": "rousses",
    },
    "long": {
        "singular_m": "long",
        "singular_f": "longue",
        "plural_m": "longs",
        "plural_f": "longues",
    },
    "frais": {
        "singular_m": "frais",
        "singular_f": "fraîche",
        "plural_m": "frais",
        "plural_f": "fraîches",
    },
    "favori": {
        "singular_m": "favori",
        "singular_f": "favorite",
        "plural_m": "favoris",
        "plural_f": "favorites",
    },
    "gentil": {
        "singular_m": "gentil",
        "singular_f": "gentille",
        "plural_m": "gentils",
        "plural_f": "gentilles",
    },
    "gros": {
        "singular_m": "gros",
        "singular_f": "grosse",
        "plural_m": "gros",
        "plural_f": "grosses",
    },
    "bas": {"singular_m": "bas", "singular_f": "basse", "plural_m": "bas", "plural_f": "basses"},
    "bon": {"singular_m": "bon", "singular_f": "bonne", "plural_m": "bons", "plural_f": "bonnes"},
    "public": {
        "singular_m": "public",
        "singular_f": "publique",
        "plural_m": "publics",
        "plural_f": "publiques",
    },
}

_VOWEL_ENDINGS = ("é", "i", "u", "ai", "y")


def _masculine_plural(singular_m: str) -> str:
    """Masculine plural: +s unless the form already ends in -s or -x."""
    if singular_m.endswith(("s", "x")):
        return singular_m
    return singular_m + "s"


def build_adjective_forms(adjective: str) -> Optional[Dict[str, str]]:
    """Build m/f × singular/plural agreement forms from the masculine singular.

    Returns ``None`` when the feminine form cannot be derived reliably,
    leaving those cases to the LLM.
    """
    singular_m = adjective.strip().lower()
    if not singular_m or len(singular_m) < 2:
        return None

    if singular_m in _IRREGULAR:
        return dict(_IRREGULAR[singular_m])

    # -eux → -euse (heureux / heureuse).
    if singular_m.endswith("eux"):
        singular_f = singular_m[:-1] + "se"
        return {
            "singular_m": singular_m,
            "singular_f": singular_f,
            "plural_m": singular_m,
            "plural_f": singular_f + "s",
        }

    # -er → -ère (cher / chère, premier / première).
    if singular_m.endswith("er"):
        singular_f = singular_m[:-2] + "ère"
        return {
            "singular_m": singular_m,
            "singular_f": singular_f,
            "plural_m": singular_m + "s",
            "plural_f": singular_f + "s",
        }

    # -f → -ve (vif / vive, actif / active).
    if singular_m.endswith("f"):
        singular_f = singular_m[:-1] + "ve"
        return {
            "singular_m": singular_m,
            "singular_f": singular_f,
            "plural_m": singular_m + "s",
            "plural_f": singular_f + "s",
        }

    # -e (not -é): invariant for gender, +s for plural (rouge / rouges).
    if singular_m.endswith("e"):
        return {
            "singular_m": singular_m,
            "singular_f": singular_m,
            "plural_m": singular_m + "s",
            "plural_f": singular_m + "s",
        }

    # Regular feminine in -e: vowel-final (joli / jolie) and -t / -d
    # (petit / petite, grand / grande).
    if singular_m.endswith(_VOWEL_ENDINGS) or singular_m.endswith(("t", "d")):
        singular_f = singular_m + "e"
        return {
            "singular_m": singular_m,
            "singular_f": singular_f,
            "plural_m": _masculine_plural(singular_m),
            "plural_f": singular_f + "s",
        }

    return None
