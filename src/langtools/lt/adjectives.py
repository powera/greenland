"""Rule-based Lithuanian adjective declension and adverb degrees.

Adjectives are declined by their nominative-singular-masculine ending:

    -as   geras      (a/o-stem)
    -ias  žalias     (ia/io-stem; the stem keeps its softening "i")
    -us   gražus     (u/i-stem)
    -is   medinis    (io/ė-stem; "didelis" is the one plural exception)
    -ęs   pavargęs   (past active participle)
    -antis / -intis  sergantis  (present active participle)

Only the plain adjective classes -as, -ias and -us get comparative/superlative
forms, plus "didelis".  Relational -is adjectives ("medinis", "paskutinis") do
not compare, and participles compare periphrastically ("labiau pavargęs").

Anything else -- pronominal (definite) forms like "kairysis", the short
participle "-ąs", multi-word or capitalized words -- is declined to ``None`` so
it keeps whatever forms it has stored.

A final t/d palatalizes to č/dž before an "i" that is followed by a back vowel
("plačios", "sergančio"), but not before "ie" or a bare "i": "platiems",
"sergantiems", "plati".
"""

from typing import Dict, List, Optional, Tuple

from langtools.lt.utils import palatalize_final

GRADABILITY_NON_GRADABLE = "non_gradable"

# Case order shared by every table below; vocative equals nominative for
# adjectives, but is listed so each table reads as a full column.
_CASES: Tuple[str, ...] = (
    "nominative",
    "genitive",
    "dative",
    "accusative",
    "instrumental",
    "locative",
    "vocative",
)

# (masc sg, masc pl, fem sg, fem pl) endings, one per case in _CASES order.
_Table = Tuple[List[str], List[str], List[str], List[str]]

_AS_TABLE: _Table = (
    "as o am ą u ame as".split(),
    "i ų iems us ais uose i".split(),
    "a os ai ą a oje a".split(),
    "os ų oms as omis ose os".split(),
)

_US_TABLE: _Table = (
    "us aus iam ų iu iame us".split(),
    "ūs ių iems ius iais iuose ūs".split(),
    "i ios iai ią ia ioje i".split(),
    "ios ių ioms ias iomis iose ios".split(),
)

_IS_TABLE: _Table = (
    "is io iam į iu iame is".split(),
    "iai ių iams ius iais iuose iai".split(),
    "ė ės ei ę e ėje ė".split(),
    "ės ių ėms es ėmis ėse ės".split(),
)

_PRESENT_PARTICIPLE_TABLE: _Table = (
    "is io iam į iu iame is".split(),
    "ys ių iems ius iais iuose ys".split(),
    "i ios iai ią ia ioje i".split(),
    "ios ių ioms ias iomis iose ios".split(),
)

_PAST_PARTICIPLE_TABLE: _Table = (
    "ęs usio usiam usį usiu usiame ęs".split(),
    "ę usių usiems usius usiais usiuose ę".split(),
    "usi usios usiai usią usia usioje usi".split(),
    "usios usių usioms usias usiomis usiose usios".split(),
)

# Forms the class table gets wrong, keyed by adjective then form key.
# "didelis" takes the ia-stem plural (dideli, dideliems) rather than the
# io-stem one (*dideliai, *dideliams).
_IRREGULAR_FORMS: Dict[str, Dict[str, str]] = {
    "didelis": {
        "nominative_plural_m": "dideli",
        "dative_plural_m": "dideliems",
        "vocative_plural_m": "dideli",
    },
}

# Comparison stems for -is adjectives that do compare: didelis -> didesnis,
# didžiausias.
_IRREGULAR_COMPARISON_STEMS: Dict[str, str] = {"didelis": "did"}

# Pronoun-like adjectives that decline as -as but have no degrees.
NON_GRADABLE_ADJECTIVES = frozenset({"kitas", "savas", "visas", "tas", "šitas", "anas"})

# Endings that mark a form this module does not build.
_REFUSED_ENDINGS: Tuple[str, ...] = (
    "ysis",  # pronominal: kairysis
    "asis",  # pronominal: pastarasis
    "usis",  # pronominal: gražusis
    "ęsis",  # reflexive participle
    "ąs",  # short present participle
    "ius",  # ambiguous between -us and a palatalized -ius
)

_BACK_VOWELS = frozenset("aąouų")

_DEGREE_SLOTS: Tuple[Tuple[str, str, str], ...] = tuple(
    (case, number, gender)
    for case in ("nominative", "accusative")
    for number in ("singular", "plural")
    for gender in ("m", "f")
)

_COMPARATIVE_ENDINGS: Dict[Tuple[str, str, str], str] = dict(
    zip(_DEGREE_SLOTS, "esnis esnė esni esnės esnį esnę esnius esnes".split())
)
_SUPERLATIVE_ENDINGS: Dict[Tuple[str, str, str], str] = dict(
    zip(_DEGREE_SLOTS, "iausias iausia iausi iausios iausią iausią iausius iausias".split())
)


def _is_safe_word(word: str) -> bool:
    return bool(word) and " " not in word and word == word.lower() and word.isalpha()


def _attach(stem: str, suffix: str, palatalizes: bool) -> str:
    """Join *stem* and *suffix*, applying t/d palatalization where it is written.

    A stem that already ends in its softening "i" (žali-) absorbs the
    suffix's leading "i" (žali + iems -> žaliems).
    """
    if stem.endswith("i") and suffix.startswith("i"):
        return stem + suffix[1:]
    if palatalizes and len(suffix) > 1 and suffix[0] == "i" and suffix[1] in _BACK_VOWELS:
        return palatalize_final(stem) + suffix
    return stem + suffix


def _depalatalize(stem: str) -> str:
    """plokšč -> plokšt, ž-final stems are left alone (only dž reverts)."""
    if stem.endswith("dž"):
        return stem[:-2] + "d"
    if stem.endswith("č"):
        return stem[:-1] + "t"
    return stem


def _classify(adjective: str) -> Optional[Tuple[str, _Table, bool, Optional[str]]]:
    """Return (stem, table, palatalizes, comparison_base) or None.

    comparison_base is the stem degree forms are built from, or None when
    the class does not compare.
    """
    if adjective.endswith(_REFUSED_ENDINGS):
        return None
    if adjective.endswith(("antis", "intis")):
        return adjective[:-2], _PRESENT_PARTICIPLE_TABLE, True, None
    if adjective.endswith("ęs"):
        return adjective[:-2], _PAST_PARTICIPLE_TABLE, False, None
    if adjective.endswith("ias"):
        stem = adjective[:-2]
        return stem, _AS_TABLE, False, _depalatalize(stem[:-1])
    if adjective.endswith("as"):
        stem = adjective[:-2]
        return stem, _AS_TABLE, False, stem
    if adjective.endswith("us"):
        stem = adjective[:-2]
        return stem, _US_TABLE, True, stem
    if adjective.endswith("is"):
        stem = adjective[:-2]
        return stem, _IS_TABLE, True, _IRREGULAR_COMPARISON_STEMS.get(adjective)
    return None


def decline_adjective(
    adjective: str, gradability: Optional[str] = None
) -> Optional[Dict[str, str]]:
    """Build the Lithuanian adjective paradigm, or None when the rules decline.

    Args:
        adjective: Nominative singular masculine ("geras", "gražus").
        gradability: The lemma's ``gradability`` fact in Lithuanian, if any;
            ``"non_gradable"`` suppresses the comparative and superlative.

    Returns:
        Form key ("genitive_singular_f", "comparative_accusative_plural_m")
        -> text.  Degree forms are only present for adjectives that compare.
    """
    adjective = adjective.strip()
    if not _is_safe_word(adjective):
        return None
    classified = _classify(adjective)
    if classified is None:
        return None
    stem, table, palatalizes, comparison_base = classified
    if len(stem) < 2:
        return None

    forms: Dict[str, str] = {}
    columns = (
        ("singular", "m", table[0]),
        ("plural", "m", table[1]),
        ("singular", "f", table[2]),
        ("plural", "f", table[3]),
    )
    for number, gender, endings in columns:
        for case, ending in zip(_CASES, endings):
            forms[f"{case}_{number}_{gender}"] = _attach(stem, ending, palatalizes)
    forms.update(_IRREGULAR_FORMS.get(adjective, {}))

    gradable = (
        comparison_base is not None
        and gradability != GRADABILITY_NON_GRADABLE
        and adjective not in NON_GRADABLE_ADJECTIVES
    )
    if gradable and comparison_base:
        superlative_stem = palatalize_final(comparison_base)
        for slot in _DEGREE_SLOTS:
            case, number, gender = slot
            suffix = f"{case}_{number}_{gender}"
            forms[f"comparative_{suffix}"] = comparison_base + _COMPARATIVE_ENDINGS[slot]
            forms[f"superlative_{suffix}"] = superlative_stem + _SUPERLATIVE_ENDINGS[slot]

    return forms


# Adverbs whose -ai/-i ending looks derived from a gradable adjective, but whose
# sense does not compare: "paprastai" is "usually", not "simply".
NON_GRADABLE_ADVERBS = frozenset(
    {
        "amžinai",
        "galiausiai",
        "neseniai",
        "pakankamai",
        "paprastai",
        "tikrai",
        "visai",
        "visiškai",
    }
)


def _adverb_comparison_stem(adverb: str) -> Optional[str]:
    """The palatalized stem degree endings attach to, or None if not derived.

    gražiai -> graž, greitai -> greič, toli -> tol, arti -> arč.
    """
    if adverb.endswith(("iau", "iausiai", "iškai")):
        # Already a degree form (daugiau, mažiausiai), or a manner adverb from
        # an -iškas adjective (lietuviškai) -- neither compares.
        return None
    if adverb.endswith("iai"):
        return adverb[:-3]
    if adverb.endswith("ai"):
        return palatalize_final(adverb[:-2])
    if adverb.endswith("i"):
        return palatalize_final(adverb[:-1])
    return None


def build_adverb_degrees(
    adverb: str, gradability: Optional[str] = None
) -> Optional[Dict[str, str]]:
    """Build ``positive``/``comparative``/``superlative`` for a Lithuanian adverb.

    Args:
        adverb: The adverb ("greitai", "toli", "dabar").
        gradability: The lemma's ``gradability`` fact in Lithuanian, if any.

    Returns:
        ``positive`` always; ``comparative`` and ``superlative`` for adverbs
        formed from an adjective (-ai, -iai, -i) that compare.  None for
        multi-word or capitalized input.
    """
    adverb = adverb.strip()
    if not _is_safe_word(adverb):
        return None

    forms: Dict[str, str] = {"positive": adverb}
    if gradability == GRADABILITY_NON_GRADABLE or adverb in NON_GRADABLE_ADVERBS:
        return forms

    stem = _adverb_comparison_stem(adverb)
    if stem is None or len(stem) < 2:
        return forms

    forms["comparative"] = stem + "iau"
    forms["superlative"] = stem + "iausiai"
    return forms
