"""Build the paradigm of an English spelling variant.

A spelling variant is the same lexeme written differently -- "grey" for
"gray", "donut" for "doughnut".  It carries a full paradigm of its own
("greyer", "greyest"), which is why it is stored in ``variant_forms`` rather
than as a single extra row on ``derivative_forms``; see
``storage.models.variant_form``.

Generators only ever produce the variant's *base form*: an LLM asked for
alternate spellings of "gray" answers "grey", not the whole paradigm.  This
module expands that base form into the remaining slots by re-running the same
mechanical rules in :mod:`langtools.en.inflection` that produced the lemma's
own forms, seeded with the variant spelling instead of the lemma spelling.

The expansion is deliberately conservative.  Irregular words are refused
outright: their irregular forms are spelled for the lemma and no rule respells
them for the variant, so inflecting the variant mechanically would pair
"better"/"best" with a regular variant paradigm.  The underlying builders in
:mod:`langtools.en.inflection` are themselves conservative and return ``None``
whenever the spelling rules are not confident.  Anything refused here is left
for a human to enter in Barsukas.
"""

from typing import Dict, Optional

from langtools.en.conjugation import IRREGULAR_CONJUGATIONS, expand_verb_forms
from langtools.en.inflection import (
    IRREGULAR_ADVERB_COMPARISON,
    IRREGULAR_COMPARISON,
    build_adjective_forms,
    build_adverb_forms,
    build_noun_forms,
)


def _is_irregular(lemma: str, pos_type: str) -> bool:
    """Whether *lemma* inflects irregularly according to the in-code tables.

    Irregularity is a property of the word, but the tables are keyed by
    spelling, so they only ever contain the lemma's spelling -- looking up the
    variant would miss.  Mechanically inflecting the variant would then pair an
    irregular lemma paradigm with a regular variant one.
    """
    normalized = lemma.lower()
    if pos_type == "verb":
        return normalized in IRREGULAR_CONJUGATIONS
    if pos_type == "adjective":
        return normalized in IRREGULAR_COMPARISON
    if pos_type == "adverb":
        return normalized in IRREGULAR_ADVERB_COMPARISON
    return False


def build_variant_paradigm(
    lemma_text: str,
    variant_text: str,
    pos_type: str,
    *,
    countability: Optional[str] = None,
    number_type: Optional[str] = None,
    irregular_plural: Optional[str] = None,
    gradability: Optional[str] = None,
    comparative: Optional[str] = None,
    superlative: Optional[str] = None,
    past: Optional[str] = None,
    past_participle: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """Expand *variant_text* into a full paradigm, or ``None`` if unsure.

    The lexical grammar facts are those of the *lemma*: "grey" is uncountable
    exactly when "gray" is, because they are the same word.  They are applied
    unchanged to the variant spelling.

    Args:
        lemma_text: The lemma's own spelling (e.g. "gray").
        variant_text: The variant's base spelling (e.g. "grey").
        pos_type: The lemma's part of speech.
        countability: The lemma's ``countability`` grammar fact (nouns).
        number_type: The lemma's ``number_type`` grammar fact (nouns).
        irregular_plural: The lemma's ``plural`` grammar fact (nouns).
        gradability: The lemma's ``gradability`` fact (adjectives/adverbs).
        comparative: The lemma's ``comparative`` fact (adjectives/adverbs).
        superlative: The lemma's ``superlative`` fact (adjectives/adverbs).
        past: The lemma's ``past`` grammar fact (verbs).
        past_participle: The lemma's ``past_participle`` fact (verbs).

    Returns:
        A mapping of form key -> variant text, using the same keys as the
        ``build_*_forms`` helpers (e.g. ``{"positive": "grey", ...}``).
        ``None`` when the lemma inflects irregularly, or when the mechanical
        rules are not confident about the variant spelling.
    """
    normalized_pos = pos_type.lower()
    variant = variant_text.strip()
    lemma = lemma_text.strip()
    if not variant or not lemma:
        return None

    # Never mechanically inflect the variant of an irregular word.  An
    # irregular form -- whether stored as a grammar fact or held in the in-code
    # tables -- is spelled for the lemma, and no rule respells it for the
    # variant.  Applying the rules anyway would pair "better"/"best" with a
    # regularly-inflected variant.  These have to be entered by hand.
    if _is_irregular(lemma, normalized_pos):
        return None

    if normalized_pos == "noun":
        if irregular_plural:
            return None
        return build_noun_forms(variant, countability=countability, number_type=number_type)

    if normalized_pos == "adjective":
        if comparative or superlative:
            return None
        return build_adjective_forms(variant, gradability=gradability)

    if normalized_pos == "adverb":
        if comparative or superlative:
            return None
        return build_adverb_forms(variant, gradability=gradability)

    if normalized_pos == "verb":
        if past or past_participle:
            return None
        return expand_verb_forms({"infinitive": variant})

    return None


__all__ = ["build_variant_paradigm"]
