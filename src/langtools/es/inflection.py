"""Rule-based Spanish adjective inflection helpers.

Spanish adjectives agree with their noun in gender and number.  Three
patterns cover almost the whole lexicon:

* **Four forms** — ``-o`` adjectives (``rojo``), and the gendered consonant
  endings ``-or``/``-ón``/``-án``/``-ín``/``-és`` (``hablador``, ``francés``).
* **Two forms** — everything else is invariant for gender and only marks
  number (``grande``/``grandes``, ``azul``/``azules``).
* **One form** — unstressed ``-s`` adjectives (``gratis``, ``isósceles``).

Ambiguous input (multiple words, no vowel at all) returns ``None`` so the
caller can fall back to the LLM.
"""

from typing import Dict, Optional, Set

from langtools.es.orthography import respell_with_stress, stressed_nucleus, strip_accents

# Comparatives and Latin-derived ``-or``/``-ior`` adjectives keep one form for
# both genders: ``el hermano mayor`` / ``la hermana mayor``.
INVARIANT_OR_ADJECTIVES: Set[str] = {
    "anterior",
    "exterior",
    "inferior",
    "interior",
    "mayor",
    "mejor",
    "menor",
    "peor",
    "posterior",
    "superior",
    "ulterior",
}

# ``-és`` is otherwise a reliable gendered ending (``francés``/``francesa``).
INVARIANT_ES_ADJECTIVES: Set[str] = {"cortés", "descortés"}

# ``-ón`` is gendered (``llorón``/``llorona``) apart from a few colour terms.
INVARIANT_ON_ADJECTIVES: Set[str] = {"marrón", "bombón"}

# Gendered consonant endings: the feminine adds ``-a`` to the unaccented stem.
_GENDERED_ENDINGS = ("or", "ón", "án", "ín", "és")

# Consonant-final adjectives outside those endings are normally invariant for
# gender; these few are not.
GENDERED_CONSONANT_ADJECTIVES: Set[str] = {"andaluz", "español", "mongol"}

_VOWEL_ENDINGS = "aeiouáéó"


def _suffix(adjective: str, stem_trim: int, ending: str) -> str:
    """Attach ``ending`` to ``adjective``, keeping the stress where it was.

    The written accent is recomputed because adding a syllable can move a word
    across the accent rules: ``joven`` → ``jóvenes``, ``común`` → ``comunes``.
    """
    stressed_index = stressed_nucleus(adjective)
    stem = strip_accents(adjective)
    if stem_trim:
        stem = stem[:-stem_trim]
    combined = stem + ending
    if stressed_index is None:
        return combined
    return respell_with_stress(combined, stressed_index)


def _consonant_plural(adjective: str) -> str:
    """Return the plural of a consonant-final adjective (``-es``, ``z`` → ``ces``)."""
    if adjective.endswith("z"):
        return _suffix(adjective, 1, "ces")
    return _suffix(adjective, 0, "es")


def _gendered_forms(singular_m: str) -> Dict[str, str]:
    """Build the four forms of a consonant-final adjective that marks gender."""
    singular_f = _suffix(singular_m, 0, "a")
    return _four_form(
        singular_m,
        singular_f,
        _consonant_plural(singular_m),
        singular_f + "s",
    )


def _two_form(singular: str, plural: str) -> Dict[str, str]:
    """Build the agreement table for an adjective invariant in gender."""
    return {
        "singular_m": singular,
        "singular_f": singular,
        "plural_m": plural,
        "plural_f": plural,
    }


def _four_form(singular_m: str, singular_f: str, plural_m: str, plural_f: str) -> Dict[str, str]:
    """Build the agreement table for an adjective that marks gender."""
    return {
        "singular_m": singular_m,
        "singular_f": singular_f,
        "plural_m": plural_m,
        "plural_f": plural_f,
    }


def build_adjective_forms(adjective: str) -> Optional[Dict[str, str]]:
    """Build m/f × singular/plural agreement forms from the masculine singular.

    Returns ``None`` when the input is not a single inflectable word, leaving
    those cases to the LLM.
    """
    singular_m = adjective.strip().lower()
    if not singular_m or " " in singular_m or "-" in singular_m:
        return None
    if not any(char in "aeiouáéíóúü" for char in singular_m):
        return None

    # -o adjectives: four distinct forms (rojo / roja / rojos / rojas).
    if singular_m.endswith("o"):
        stem = singular_m[:-1]
        return _four_form(singular_m, stem + "a", stem + "os", stem + "as")

    # Gendered consonant endings: hablador / habladora, francés / francesa.
    if singular_m in GENDERED_CONSONANT_ADJECTIVES:
        return _gendered_forms(singular_m)
    if singular_m.endswith(_GENDERED_ENDINGS):
        if (
            singular_m not in INVARIANT_OR_ADJECTIVES
            and singular_m not in INVARIANT_ES_ADJECTIVES
            and singular_m not in INVARIANT_ON_ADJECTIVES
        ):
            return _gendered_forms(singular_m)

    # Stressed -í / -ú take -es in the plural (marroquí / marroquíes).
    if singular_m.endswith(("í", "ú")):
        return _two_form(singular_m, singular_m + "es")

    # Other vowel endings: invariant for gender, +s for the plural
    # (grande / grandes, belga / belgas).
    if singular_m[-1] in _VOWEL_ENDINGS:
        return _two_form(singular_m, singular_m + "s")

    # -z adjectives: z → ces in the plural (feliz / felices).
    if singular_m.endswith("z"):
        return _two_form(singular_m, _consonant_plural(singular_m))

    # An unstressed final -s is invariant in both number and gender
    # (gratis, isósceles); a stressed one takes -es (corteses).
    if singular_m.endswith("s"):
        nucleus = stressed_nucleus(singular_m)
        nuclei_after_stress = sum(
            1 for char in singular_m[(nucleus or 0) + 1 :] if char in "aeiouáéíóú"
        )
        if nuclei_after_stress:
            return _two_form(singular_m, singular_m)

    # Remaining consonant endings are invariant for gender and add -es
    # (azul / azules, joven / jóvenes, común / comunes).
    return _two_form(singular_m, _consonant_plural(singular_m))
