"""Rule-based Spanish adjective inflection helpers.

Spanish adjectives agree with their noun in gender and number.  This module
covers only the high-confidence regular endings (-o, -a, -e, -z); ambiguous
endings (most consonants, accented vowels, agent endings such as -or) return
``None`` so the caller can fall back to the LLM.
"""

from typing import Dict, Optional


def build_adjective_forms(adjective: str) -> Optional[Dict[str, str]]:
    """Build m/f × singular/plural agreement forms from the masculine singular.

    Returns ``None`` when the ending is not one of the reliably regular
    patterns, leaving those cases to the LLM.
    """
    singular_m = adjective.strip().lower()
    if not singular_m:
        return None

    # -o adjectives: four distinct forms (rojo / roja / rojos / rojas).
    if singular_m.endswith("o"):
        stem = singular_m[:-1]
        return {
            "singular_m": singular_m,
            "singular_f": stem + "a",
            "plural_m": stem + "os",
            "plural_f": stem + "as",
        }

    # -e / -a adjectives: invariant for gender, +s for plural
    # (grande / grandes, belga / belgas).
    if singular_m.endswith(("e", "a")):
        plural = singular_m + "s"
        return {
            "singular_m": singular_m,
            "singular_f": singular_m,
            "plural_m": plural,
            "plural_f": plural,
        }

    # -z adjectives: invariant for gender, z → ces for plural (feliz / felices).
    if singular_m.endswith("z"):
        plural = singular_m[:-1] + "ces"
        return {
            "singular_m": singular_m,
            "singular_f": singular_m,
            "plural_m": plural,
            "plural_f": plural,
        }

    return None
