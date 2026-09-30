"""Rule-based Spanish adjective and noun inflection helpers.

Spanish adjectives agree with their noun in gender and number.  Three
patterns cover almost the whole lexicon:

* **Four forms** — ``-o`` adjectives (``rojo``), and the gendered consonant
  endings ``-or``/``-ón``/``-án``/``-ín``/``-és`` (``hablador``, ``francés``).
* **Two forms** — everything else is invariant for gender and only marks
  number (``grande``/``grandes``, ``azul``/``azules``).
* **One form** — unstressed ``-s`` adjectives (``gratis``, ``isósceles``).

A few adjectives also have a shortened (apocopated) singular used before the
noun: ``un buen día``, ``el primer piso``, ``una gran casa``.  Those fill the
``singular_m_apocope`` / ``singular_f_apocope`` slots; every other adjective
leaves them out.  Prepositional phrases standing in for an adjective
(``de madera``) do not agree at all and repeat one form in every slot.

Noun plurals follow the same spelling rules as adjectives (``camión`` →
``camiones``, ``lápiz`` → ``lápices``).

Ambiguous input (other multi-word phrases, no vowel at all, stressed ``-í``/
``-ú`` nouns, foreign consonant endings) returns ``None`` so the caller can
fall back to the LLM.
"""

from typing import Dict, Optional, Set

from langtools.es.orthography import (
    respell_with_stress,
    stressed_nucleus,
    strip_accents,
    syllable_nuclei,
)

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


# Apocopated singulars used before the noun.  Masculine only, except gran,
# which shortens for both genders (un gran día, una gran casa).
_APOCOPE_M: Dict[str, str] = {
    "bueno": "buen",
    "malo": "mal",
    "primero": "primer",
    "tercero": "tercer",
    "postrero": "postrer",
    "grande": "gran",
}
_APOCOPE_F: Dict[str, str] = {"grande": "gran"}

# A phrase opening with one of these is a prepositional phrase (de madera,
# a mano, sin azúcar), which does not agree with its noun.
_PREPOSITIONS: Set[str] = {
    "a",
    "al",
    "bajo",
    "con",
    "de",
    "del",
    "en",
    "para",
    "por",
    "sin",
    "sobre",
}


def _invariant_phrase(phrase: str) -> Optional[Dict[str, str]]:
    """Return the one-form table for a prepositional phrase, else None."""
    words = phrase.split()
    if len(words) < 2 or words[0] not in _PREPOSITIONS:
        return None
    return _four_form(phrase, phrase, phrase, phrase)


def build_adjective_forms(adjective: str) -> Optional[Dict[str, str]]:
    """Build m/f × singular/plural agreement forms from the masculine singular.

    Adds the apocopated singulars for the few adjectives that have them.
    Returns ``None`` when the input is not an inflectable word or an invariant
    prepositional phrase, leaving those cases to the LLM.
    """
    singular_m = adjective.strip().lower()
    if " " in singular_m:
        return _invariant_phrase(singular_m)
    forms = _agreement_forms(singular_m)
    if forms is None:
        return None
    if singular_m in _APOCOPE_M:
        forms["singular_m_apocope"] = _APOCOPE_M[singular_m]
    if singular_m in _APOCOPE_F:
        forms["singular_f_apocope"] = _APOCOPE_F[singular_m]
    return forms


def _agreement_forms(singular_m: str) -> Optional[Dict[str, str]]:
    """Build the four agreement forms of a single-word adjective."""
    if not singular_m or "-" in singular_m:
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


# Native consonant endings that take -es.  Other final consonants (club,
# robot, álbum, cómic) mark loanwords whose plural varies, and go to the LLM.
_NOUN_ES_ENDINGS = "lrndj"

# The three nouns whose stress moves in the plural.
_STRESS_SHIFT_PLURALS: Dict[str, str] = {
    "régimen": "regímenes",
    "espécimen": "especímenes",
    "carácter": "caracteres",
}


def _noun_plural(noun: str) -> Optional[str]:
    """Return the plural of a single-word noun, or None when it is not regular."""
    if noun in _STRESS_SHIFT_PLURALS:
        return _STRESS_SHIFT_PLURALS[noun]
    if not any(char in "aeiouáéíóúü" for char in noun):
        return None
    last = noun[-1]

    # Unstressed vowels and stressed á/é/ó add -s (casa, taxi, sofá, café).
    if last in "aeiouáéó":
        return noun + "s"
    # Stressed -í/-ú vary (rubíes, menús).
    if last in "íú":
        return None
    if last == "z":
        return _suffix(noun, 1, "ces")
    if last in "sx":
        # Stress before the last syllable: invariant (la crisis / las crisis,
        # el lunes, el tórax).  Stress on it: -es (autobuses, países, meses).
        nuclei = syllable_nuclei(noun)
        if stressed_nucleus(noun) != nuclei[-1]:
            return noun
        return _suffix(noun, 0, "es") if last == "s" else None
    if last == "y":
        # One-syllable -y nouns add -es (rey / reyes, ley / leyes); longer
        # ones vary (jersey / jerséis).
        return noun + "es" if len(syllable_nuclei(noun)) == 1 else None
    if last in _NOUN_ES_ENDINGS:
        return _suffix(noun, 0, "es")
    return None


def build_noun_forms(
    noun: str,
    irregular_plural: Optional[str] = None,
    number_type: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """Build the singular and plural of a Spanish noun.

    *irregular_plural* is the stored ``plural`` grammar fact, which wins over
    the rules; *number_type* is the ``number_type`` fact (see the comment in
    the body for how each value fills the slots).  A "noun de noun" compound
    pluralises its head (``tarjeta de crédito`` → ``tarjetas de crédito``).
    Returns ``None`` for capitalised words (proper nouns, brands), other
    multi-word phrases and endings whose plural varies.
    """
    singular = noun.strip()
    if not singular or singular[0].isupper() or "-" in singular:
        return None
    # Same convention as langtools.en.inflection: a plurale tantum repeats the
    # word in both slots; uncountable and singulare tantum have no plural.
    if number_type == "plurale_tantum":
        return {"singular": singular, "plural": singular}
    if number_type in ("uncountable", "singulare_tantum"):
        return {"singular": singular}
    if irregular_plural:
        return {"singular": singular, "plural": irregular_plural.strip()}

    words = singular.split()
    if len(words) > 1 and words[1] not in ("de", "del", "a"):
        return None
    head_plural = _noun_plural(words[0])
    if head_plural is None:
        return None
    return {"singular": singular, "plural": " ".join([head_plural, *words[1:]])}
