"""Rule-based English noun, adjective and adverb inflection.

This module contains **spelling rules only**.  Whether a particular word is
uncountable, plurale tantum, non-gradable, or takes an irregular plural is a
lexical property of the *lemma*, not of the spelling: "iron" the metal is
uncountable while "iron" the appliance is not, and no surface-text table can
tell the two apart.  Those properties live in the ``grammar_facts`` table,
keyed per lemma GUID, and are passed in to the builders here as parameters.

The only word lists kept are the handful of suppletive comparison paradigms
(``IRREGULAR_COMPARISON``, ``IRREGULAR_ADVERB_COMPARISON``) which are short,
closed and genuinely spelling-keyed, plus :data:`HARD_CH_NOUNS`, which encodes
a pronunciation-driven spelling exception rather than a lexical fact.

Every public builder returns ``None`` when it is *not* confident, so the
caller (``langtools.en.llm_forms``) can fall back to the LLM.  Producing
nothing is always preferred to producing a plausible-looking wrong form such
as ``informations`` or ``beautifuler``.  With the lexical tables gone, more
words legitimately fall through until their grammar facts are populated.

Rules used
----------
Nouns (``build_noun_forms``)
    1. Multi-word lemmas, lemmas with punctuation/parentheses and capitalised
       (proper) nouns fall through - their plural is a lexical question.
    2. An explicit ``irregular_plural`` (the stored ``plural`` grammar fact)
       is used verbatim and wins over every rule.
    3. ``number_type="plurale_tantum"`` repeats the lemma in both slots rather
       than producing ``jeanses``.  ``"uncountable"`` and ``"singulare_tantum"``
       produce ``singular`` only, as does ``countability="uncountable"``.
    4. Spellings that are systematically ambiguous in English - any lemma
       ending in ``-f``/``-fe``, ``-o``, ``-s``, ``-is``, ``-us``, ``-um``,
       ``-ex`` or ``-ix`` with no stored plural - fall through rather than
       guess between ``roofs``/``rooves`` or ``cactuses``/``cacti``.  ``-ss``,
       ``-ff``, ``-ffe``, ``-oo``, ``-io`` and ``-eo`` are exempt: their
       plurals really are regular.
    5. Everything else takes the regular ``-s``/``-es``/``-ies`` rule.

Adjectives (``build_adjective_forms``)
    1. Explicit ``comparative``/``superlative`` facts win outright; a lemma in
       :data:`IRREGULAR_COMPARISON` is used when no facts were supplied.
    2. ``gradability="non_gradable"`` produces ``positive`` only;
       ``"periphrastic"`` forces ``more``/``most``; ``"synthetic"`` forces
       ``-er``/``-est``.
    3. With no gradability fact: one-syllable adjectives and two-syllable
       adjectives ending in ``-y`` take synthetic ``-er``/``-est``.
    4. Adjectives with three or more syllables, and two-syllable adjectives
       with the endings listed in :data:`PERIPHRASTIC_SUFFIXES` (``-ful``,
       ``-ous``, ``-ive``, ``-ing``, ``-ed``, ...), take ``more``/``most``.
    5. Anything else - notably unsuffixed two-syllable adjectives such as
       "common", "polite", "stubborn" - falls through, because English
       usage genuinely varies there.

Adverbs (``build_adverb_forms``)
    Same shape as adjectives, with :data:`IRREGULAR_ADVERB_COMPARISON` as the
    in-code fallback.  Without a gradability fact, an ``-ly`` adverb takes
    ``more``/``most`` and everything else falls through.
"""

from typing import Dict, Optional, Set, Tuple

from langtools.en.utils import (
    generate_comparative,
    generate_regular_plural,
    generate_superlative,
    should_double_final_consonant,
)

# Values of the "number_type" grammar fact that suppress the plural slot.
_SINGULAR_ONLY_NUMBER_TYPES: Tuple[str, ...] = ("uncountable", "singulare_tantum")

# Values of the "gradability" grammar fact.
GRADABILITY_SYNTHETIC = "synthetic"
GRADABILITY_PERIPHRASTIC = "periphrastic"
GRADABILITY_NON_GRADABLE = "non_gradable"

# ---------------------------------------------------------------------------
# Nouns
# ---------------------------------------------------------------------------

# Nouns ending in "-ch" pronounced /k/, which take a plain "-s" rather than
# the sibilant "-es" ("stomach" -> "stomachs", not "stomaches").  This is a
# pronunciation-driven spelling exception, not a lexical property.
HARD_CH_NOUNS: Set[str] = {
    "epoch",
    "eunuch",
    "loch",
    "monarch",
    "patriarch",
    "stomach",
}

# Endings whose plural is not predictable from spelling.  Any lemma with one
# of these endings and no stored "plural" grammar fact falls through to the
# LLM rather than being guessed (roof/roofs vs. hoof/hooves, cactus/cacti vs.
# bus/buses, piano/pianos vs. potato/potatoes).
AMBIGUOUS_PLURAL_ENDINGS: Tuple[str, ...] = ("f", "fe", "o", "is", "us", "um", "ex", "ix", "s")

# Endings exempt from the AMBIGUOUS_PLURAL_ENDINGS check because their plural
# really is regular (-oo/-io/-eo take -s; -ff/-ffe never take -ves).
_REGULAR_DESPITE_AMBIGUOUS_ENDING: Tuple[str, ...] = (
    "oo",
    "io",
    "eo",
    "ff",
    "ffe",
    "ss",
)


def _is_mechanically_safe_lemma(lemma: str) -> bool:
    """Whether *lemma* is a single, lowercase, alphabetic word.

    Multi-word lemmas ("air conditioner"), lemmas carrying a disambiguation
    ("head (of cattle)"), and proper nouns ("Amsterdam", "Mr.") are left to
    the LLM: their inflection is a lexical or editorial question.
    """
    if not lemma:
        return False
    if lemma != lemma.lower():
        return False
    return lemma.isalpha()


def build_noun_forms(
    noun: str,
    countability: Optional[str] = None,
    number_type: Optional[str] = None,
    irregular_plural: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """Build ``singular``/``plural`` for *noun*, or ``None`` if unsure.

    All three lexical parameters come from the lemma's stored grammar facts;
    none of them can be derived from the spelling.

    Args:
        noun: The lemma text.
        countability: The ``countability`` fact (``"countable"``,
            ``"uncountable"`` or ``"both"``).
        number_type: The ``number_type`` fact (``"uncountable"``,
            ``"plurale_tantum"``, ``"singulare_tantum"`` or ``"both"``).
        irregular_plural: The ``plural`` fact, used verbatim when present.

    Returns:
        A mapping with ``singular`` and usually ``plural``; uncountable and
        singulare-tantum nouns get ``singular`` only.  ``None`` when the rules
        are not confident.
    """
    singular = noun.strip()
    if not _is_mechanically_safe_lemma(singular):
        return None

    if number_type == "plurale_tantum":
        # Already plural in form; "a pair of scissors" is the citation form.
        return {"singular": singular, "plural": singular}

    if number_type in _SINGULAR_ONLY_NUMBER_TYPES or countability == "uncountable":
        return {"singular": singular}

    if irregular_plural:
        return {"singular": singular, "plural": irregular_plural.strip()}

    if singular.endswith(AMBIGUOUS_PLURAL_ENDINGS) and not singular.endswith(
        _REGULAR_DESPITE_AMBIGUOUS_ENDING
    ):
        return None

    # "-ch" is only a sibilant when pronounced /tʃ/: "church" -> "churches" but
    # "stomach" -> "stomachs".  Spelling cannot tell them apart, so the /k/
    # cases are listed.
    if singular.endswith("ch") and singular in HARD_CH_NOUNS:
        return {"singular": singular, "plural": singular + "s"}

    # The "-ff"/"-ffe" -> "-s" rule (giraffe -> giraffes, not girafves) lives in
    # generate_regular_plural; the AMBIGUOUS_PLURAL_ENDINGS check above already
    # let these through rather than deferring them to the LLM.
    return {"singular": singular, "plural": generate_regular_plural(singular)}


# ---------------------------------------------------------------------------
# Adjectives
# ---------------------------------------------------------------------------

# Suppletive / stem-changing comparison.  Short, closed and unambiguous across
# senses, so it stays in code as the fallback when no grammar facts exist.
IRREGULAR_COMPARISON: Dict[str, Dict[str, str]] = {
    "bad": {"comparative": "worse", "superlative": "worst"},
    "far": {"comparative": "farther", "superlative": "farthest"},
    "good": {"comparative": "better", "superlative": "best"},
    "ill": {"comparative": "worse", "superlative": "worst"},
    "late": {"comparative": "later", "superlative": "latest"},
    "little": {"comparative": "less", "superlative": "least"},
    "many": {"comparative": "more", "superlative": "most"},
    "much": {"comparative": "more", "superlative": "most"},
    "old": {"comparative": "older", "superlative": "oldest"},
    "well": {"comparative": "better", "superlative": "best"},
    "worse": {"comparative": "worse", "superlative": "worst"},
}

# Two-syllable endings that reliably force more/most rather than -er/-est.
PERIPHRASTIC_SUFFIXES: Tuple[str, ...] = (
    "ful",
    "ous",
    "ive",
    "ish",
    "ic",
    "ing",
    "ed",
    "al",
    "ant",
    "ent",
    "ial",
    "ary",
    "less",
)

_VOWELS = "aeiouy"


def count_syllables(word: str) -> int:
    """Approximate the syllable count of *word* by counting vowel runs.

    A trailing silent ``-e`` ("large", "wide") is not counted, but ``-le``
    after a consonant ("simple", "gentle") is.  Accurate enough to separate
    monosyllables from polysyllables, which is all the comparison rules need.
    """
    lowered = word.lower()
    if not lowered:
        return 0

    groups = 0
    in_vowel_run = False
    for char in lowered:
        if char in _VOWELS:
            if not in_vowel_run:
                groups += 1
                in_vowel_run = True
        else:
            in_vowel_run = False

    # Silent final -e ("large"), but "-le" after a consonant keeps its syllable.
    if lowered.endswith("e") and not lowered.endswith(("le", "ee", "ye", "oe")):
        groups -= 1
    elif lowered.endswith("le") and len(lowered) > 2 and lowered[-3] in _VOWELS:
        # "-ale", "-ile": the e is silent ("whole", "mile").
        groups -= 1

    return max(groups, 1)


def _periphrastic(positive: str) -> Dict[str, str]:
    return {
        "positive": positive,
        "comparative": f"more {positive}",
        "superlative": f"most {positive}",
    }


def _synthetic(positive: str) -> Dict[str, str]:
    """Build ``-er``/``-est`` forms, doubling the final consonant when due.

    ``generate_comparative`` / ``generate_superlative`` only double after
    ``b d g p t``, which misses "thin" -> "thinner" and "dim" -> "dimmer";
    :func:`should_double_final_consonant` applies the full stressed-CVC rule.
    """
    if should_double_final_consonant(positive):
        stem = positive + positive[-1]
        return {
            "positive": positive,
            "comparative": stem + "er",
            "superlative": stem + "est",
        }
    return {
        "positive": positive,
        "comparative": generate_comparative(positive),
        "superlative": generate_superlative(positive),
    }


def _explicit_comparison(
    positive: str,
    gradability: Optional[str],
    comparative: Optional[str],
    superlative: Optional[str],
    irregular_table: Dict[str, Dict[str, str]],
) -> Optional[Dict[str, str]]:
    """Resolve the parts of comparison that come from lexical facts.

    Returns a complete mapping when the facts settle the question, and
    ``None`` when the caller must continue with the spelling rules.
    """
    if gradability == GRADABILITY_NON_GRADABLE:
        return {"positive": positive}

    if comparative and superlative:
        return {
            "positive": positive,
            "comparative": comparative.strip(),
            "superlative": superlative.strip(),
        }

    if comparative or superlative:
        # A half-populated pair is not enough to emit a form confidently.
        return None

    if positive in irregular_table:
        return {"positive": positive, **irregular_table[positive]}

    if gradability == GRADABILITY_PERIPHRASTIC:
        return _periphrastic(positive)
    if gradability == GRADABILITY_SYNTHETIC:
        return _synthetic(positive)

    return None


def build_adjective_forms(
    adjective: str,
    gradability: Optional[str] = None,
    comparative: Optional[str] = None,
    superlative: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """Build ``positive``/``comparative``/``superlative``, or ``None``.

    Args:
        adjective: The lemma text.
        gradability: The ``gradability`` fact (``"synthetic"``,
            ``"periphrastic"`` or ``"non_gradable"``).
        comparative: The ``comparative`` fact, used verbatim when paired with
            *superlative*.
        superlative: The ``superlative`` fact.

    Returns:
        A mapping of degree forms; non-gradable adjectives get ``positive``
        only.  ``None`` when the rules are not confident.
    """
    positive = adjective.strip()
    if not _is_mechanically_safe_lemma(positive):
        return None

    from_facts = _explicit_comparison(
        positive, gradability, comparative, superlative, IRREGULAR_COMPARISON
    )
    if from_facts is not None:
        return from_facts
    if comparative or superlative:
        return None

    syllables = count_syllables(positive)

    if syllables == 1:
        return _synthetic(positive)

    if syllables >= 3:
        return _periphrastic(positive)

    # Two syllables: -y adjectives take -er/-est ("happy" -> "happier");
    # clearly derived endings take more/most; the rest is genuinely variable
    # in English usage, so fall through.
    if positive.endswith("y"):
        return _synthetic(positive)
    if positive.endswith(PERIPHRASTIC_SUFFIXES):
        return _periphrastic(positive)
    return None


# ---------------------------------------------------------------------------
# Adverbs
# ---------------------------------------------------------------------------

IRREGULAR_ADVERB_COMPARISON: Dict[str, Dict[str, str]] = {
    "badly": {"comparative": "worse", "superlative": "worst"},
    "far": {"comparative": "farther", "superlative": "farthest"},
    "little": {"comparative": "less", "superlative": "least"},
    "much": {"comparative": "more", "superlative": "most"},
    "well": {"comparative": "better", "superlative": "best"},
}


def build_adverb_forms(
    adverb: str,
    gradability: Optional[str] = None,
    comparative: Optional[str] = None,
    superlative: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """Build ``positive``/``comparative``/``superlative``, or ``None``.

    Args:
        adverb: The lemma text.
        gradability: The ``gradability`` fact (``"synthetic"``,
            ``"periphrastic"`` or ``"non_gradable"``).  ``"synthetic"`` covers
            the flat adverbs ("fast" -> "faster").
        comparative: The ``comparative`` fact, used verbatim when paired with
            *superlative*.
        superlative: The ``superlative`` fact.

    Returns:
        A mapping of degree forms; non-gradable adverbs get ``positive`` only.
        ``None`` when the rules are not confident.
    """
    positive = adverb.strip()
    if not positive or positive != positive.lower():
        return None

    from_facts = _explicit_comparison(
        positive, gradability, comparative, superlative, IRREGULAR_ADVERB_COMPARISON
    )
    if from_facts is not None:
        return from_facts
    if comparative or superlative:
        return None

    if not positive.isalpha():
        return None

    if positive.endswith("ly"):
        # Manner adverbs derived from a gradable adjective compare with
        # more/most ("quickly" -> "more quickly").  Whether the underlying
        # adjective is gradable at all is a lexical fact, supplied by the
        # caller as *gradability*.
        return _periphrastic(positive)

    return None
