"""Question semantics; applicability comes from the shared storage registries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from storage.config.grammar_fact_registry import GRAMMAR_FACT_DEFINITIONS
from storage.config.lemma_fact_registry import LEMMA_FACT_DEFINITIONS
from words.grammar_fact_tasks.systems import AUXILIARY_SYSTEMS, GENDER_SYSTEMS, REFLEXIVITY_SYSTEMS

Kind = Literal["classification", "principal_part", "override", "concept"]


@dataclass(frozen=True)
class FactSpec:
    fact_type: str
    kind: Kind
    instruction: str
    values: tuple[str, ...] = ()

    @property
    def completion_type(self) -> str:
        return f"{self.fact_type}_status" if self.kind == "override" else self.fact_type

    def languages(self) -> tuple[str, ...]:
        return GRAMMAR_FACT_DEFINITIONS[self.fact_type].languages

    def applies(self, pos_type: str, language_code: str | None) -> bool:
        if self.kind == "concept":
            return (
                language_code is None
                and pos_type in LEMMA_FACT_DEFINITIONS[self.fact_type].required_pos
            )
        definition = GRAMMAR_FACT_DEFINITIONS[self.fact_type]
        return pos_type in definition.required_pos and language_code in definition.languages

    def allowed_values(self, language_code: str | None) -> tuple[str, ...]:
        if self.fact_type == "grammatical_gender":
            return tuple(GENDER_SYSTEMS[str(language_code)]["genders"])
        if self.fact_type == "auxiliary_verb":
            return tuple(AUXILIARY_SYSTEMS[str(language_code)]["auxiliaries"])
        if self.fact_type == "verb_reflexivity":
            return tuple(REFLEXIVITY_SYSTEMS[str(language_code)]["values"])
        return self.values


SPECS: tuple[FactSpec, ...] = (
    FactSpec(
        "grammatical_gender",
        "classification",
        "Gender of the supplied noun in this sense. Common means one spelling taking either gender for its referent, not a pair of different words or different senses.",
    ),
    FactSpec(
        "countability",
        "classification",
        "Count/mass usage of this translation in this sense, independently of individuation and number paradigm.",
        ("countable", "uncountable", "both"),
    ),
    FactSpec(
        "number_type",
        "classification",
        "Number paradigm: regular has singular and plural; plurale_tantum is plural-only; singulare_tantum is singular-only. Mass usage alone does not imply singular-only.",
        ("regular", "plurale_tantum", "singulare_tantum"),
    ),
    FactSpec(
        "measure_words",
        "classification",
        "The preferred classifier or measure expression for this Chinese noun in this sense. Return the Chinese text without a numeral, pinyin or explanation; do not force 个 on materials or abstract concepts.",
    ),
    FactSpec(
        "animacy",
        "classification",
        "Whether the referent is animate or inanimate in this sense.",
        ("animate", "inanimate"),
    ),
    FactSpec(
        "verb_transitivity",
        "classification",
        "Argument structure of the verb in this sense, not all unrelated senses of the spelling.",
        ("transitive", "intransitive", "ditransitive", "ambitransitive"),
    ),
    FactSpec(
        "verb_reflexivity",
        "classification",
        "Reflexivity of this verb in this sense; include an explicit non_reflexive answer when appropriate.",
    ),
    FactSpec(
        "auxiliary_verb",
        "classification",
        "Compound-tense auxiliary for this verb in this sense; return the ordinary auxiliary explicitly too.",
    ),
    FactSpec(
        "gradability",
        "classification",
        "Comparison strategy in this sense: synthetic (-er/-est, including irregular synthetic forms), periphrastic (more/most), or non_gradable.",
        ("synthetic", "periphrastic", "non_gradable"),
    ),
    FactSpec("past", "principal_part", "Canonical simple past, even when regular."),
    FactSpec(
        "past_participle",
        "principal_part",
        "Canonical past participle (perfect-form principal part), even when regular; preserve the language's required spelling.",
    ),
    FactSpec("infinitive", "principal_part", "Canonical infinitive principal part."),
    FactSpec(
        "3s_present", "principal_part", "Canonical third-person singular present principal part."
    ),
    FactSpec("3s_past", "principal_part", "Canonical third-person singular past principal part."),
    FactSpec(
        "1s_present", "principal_part", "Canonical first-person singular present principal part."
    ),
    FactSpec(
        "1s_past",
        "principal_part",
        "Canonical first-person singular past principal part (Italian: passato remoto).",
    ),
    FactSpec(
        "1s_future", "principal_part", "Canonical first-person singular future principal part."
    ),
    FactSpec(
        "plural",
        "override",
        "Canonical plural of this noun in this sense, including regular plurals. Empty only for a singular-only paradigm; for plural-only nouns return the supplied plural form.",
    ),
    FactSpec(
        "feminine_form",
        "override",
        "French adjective's feminine singular, even when identical to the masculine or mechanically regular.",
    ),
    FactSpec(
        "comparative",
        "override",
        "Canonical comparative, including a regular or periphrastic form. Empty only when this sense cannot be compared.",
    ),
    FactSpec(
        "superlative",
        "override",
        "Canonical superlative, including a regular or periphrastic form. Empty only when this sense cannot be compared.",
    ),
    *(
        FactSpec(fact_type, "concept", definition.description, definition.allowed_values)
        for fact_type, definition in LEMMA_FACT_DEFINITIONS.items()
        if definition.generatable
    ),
)

CATALOG = {spec.fact_type: spec for spec in SPECS}
