"""Registry of language-independent lemma fact types stored in ``lemma_facts``."""

import re
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class LemmaFactDefinition:
    fact_type: str
    allowed_values: Tuple[str, ...]
    required_pos: Tuple[str, ...]
    display_label: str
    description: str
    generatable: bool = False
    #: For free-form facts (``allowed_values`` empty): the whole value must match this.
    value_pattern: Optional[str] = None


RETIRED_LEMMA_FACT_TYPES = frozenset({"quantifiable", "has_individual_instances"})


LEMMA_FACT_DEFINITIONS: Dict[str, LemmaFactDefinition] = {
    "individuation": LemmaFactDefinition(
        fact_type="individuation",
        allowed_values=("individual", "non_individuated", "collection"),
        required_pos=("noun",),
        display_label="Individuation",
        description=(
            "How this concept is organized, independently of language: a discrete "
            "entity (cat, idea), material or a quality without inherent units "
            "(water, justice), or an aggregate of members (furniture, collected data). "
            "This does not determine grammatical countability."
        ),
        generatable=True,
    ),
    "concreteness": LemmaFactDefinition(
        fact_type="concreteness",
        allowed_values=("physical", "abstract"),
        required_pos=("noun",),
        display_label="Concreteness",
        description=(
            "Whether this concept denotes material entities/material (physical), "
            "or informational, mental, social or conceptual referents (abstract). "
            "Classify the referent, not its physical representation."
        ),
        generatable=True,
    ),
    "referent_gender": LemmaFactDefinition(
        fact_type="referent_gender",
        allowed_values=("male", "female"),
        required_pos=("noun",),
        display_label="Referent Gender",
        description=(
            "A person noun that itself names a man or a woman (boy, mother, husband). "
            "Its counterpart is a separate lemma, so it has no male/female gender "
            "variants; absent for every other noun."
        ),
    ),
    "numeral": LemmaFactDefinition(
        fact_type="numeral",
        allowed_values=(),
        required_pos=("numeral",),
        display_label="Numeral",
        description='The digits a number is written with: "one" -> 1, "one thousand" -> 1000.',
        value_pattern=r"[0-9]+",
    ),
}


def get_lemma_fact_definition(fact_type: str) -> Optional[LemmaFactDefinition]:
    return LEMMA_FACT_DEFINITIONS.get(fact_type)


def validate_lemma_fact(fact_type: str, fact_value: Optional[str]) -> Optional[str]:
    """Return an error message if the type or value is invalid, else None."""
    definition = LEMMA_FACT_DEFINITIONS.get(fact_type)
    if definition is None:
        return f"Unknown lemma fact type: {fact_type}"
    if not definition.allowed_values:
        if (
            definition.value_pattern is None
            or fact_value is None
            or re.fullmatch(definition.value_pattern, fact_value) is None
        ):
            return (
                f"Invalid value {fact_value!r} for {fact_type}; expected {definition.value_pattern}"
            )
        return None
    if fact_value not in definition.allowed_values:
        return f"Invalid value {fact_value!r} for {fact_type}; allowed: {definition.allowed_values}"
    return None
