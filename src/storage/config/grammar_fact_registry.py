"""Shared registry for grammar fact capabilities and release behavior."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Tuple

from storage.translation_helpers import TIER_1_LANGUAGES, TIER_2_LANGUAGES

VERB_FORM_OVERRIDE_PREFIX = "verb_form_"
TIER_1_2_LANGUAGES: Tuple[str, ...] = tuple(TIER_1_LANGUAGES + TIER_2_LANGUAGES)
IRREGULAR_PLURAL_LANGUAGES: Tuple[str, ...] = (
    "en",
    "es",
    "fr",
    "de",
    "it",
    "pt",
    "nl",
    "sv",
)
NUMBER_TYPE_LANGUAGES: Tuple[str, ...] = (
    "en",
    "es",
    "fr",
    "de",
    "it",
    "lt",
    "pt",
    "nl",
    "sv",
)
PARTICIPLE_OVERRIDE_LANGUAGES: Tuple[str, ...] = (
    "en",
    "fr",
    "de",
    "it",
    "es",
    "pt",
    "nl",
    "sv",
)
COMPARISON_OVERRIDE_LANGUAGES: Tuple[str, ...] = (
    "en",
    "fr",
    "de",
    "it",
    "es",
    "pt",
    "nl",
    "sv",
)


@dataclass(frozen=True)
class GrammarFactDefinition:
    """Definition for one grammar fact type exposed by agents and sync."""

    fact_type: str
    languages: Tuple[str, ...]
    required_pos: Tuple[str, ...]
    display_label: str
    description: str
    generatable: bool = False
    release_sync: bool = False


GRAMMAR_FACT_DEFINITIONS: Dict[str, GrammarFactDefinition] = {
    "measure_words": GrammarFactDefinition(
        fact_type="measure_words",
        languages=("zh",),
        required_pos=("noun",),
        display_label="Measure Words",
        description="Chinese measure words/classifiers for nouns",
        generatable=True,
    ),
    "grammatical_gender": GrammarFactDefinition(
        fact_type="grammatical_gender",
        languages=("fr", "lt", "es", "de", "pt", "it"),
        required_pos=("noun",),
        display_label="Grammatical Gender",
        description="Determine grammatical gender (masculine, feminine, neuter)",
        generatable=True,
    ),
    "verb_transitivity": GrammarFactDefinition(
        fact_type="verb_transitivity",
        languages=("en",),
        required_pos=("verb",),
        display_label="Verb Transitivity",
        description="Classify verbs as transitive, intransitive, ditransitive, or ambitransitive",
        generatable=True,
    ),
    "verb_reflexivity": GrammarFactDefinition(
        fact_type="verb_reflexivity",
        languages=("fr", "es", "de", "lt", "it"),
        required_pos=("verb",),
        display_label="Verb Reflexivity",
        description="Identify inherently reflexive, optionally reflexive, or non-reflexive verbs",
        generatable=True,
    ),
    "countability": GrammarFactDefinition(
        fact_type="countability",
        languages=("en",),
        required_pos=("noun",),
        display_label="Countability",
        description="Classify nouns as countable, uncountable, or both",
        generatable=True,
    ),
    "declension_class": GrammarFactDefinition(
        fact_type="declension_class",
        languages=("lt",),
        required_pos=("noun",),
        display_label="Declension Class",
        description="Determine declension class for Lithuanian nouns",
        generatable=True,
    ),
    "auxiliary_verb": GrammarFactDefinition(
        fact_type="auxiliary_verb",
        languages=("fr", "de", "it", "nl"),
        required_pos=("verb",),
        display_label="Auxiliary Verb",
        description="Identify auxiliary verb used in compound tenses",
        generatable=True,
    ),
    "animacy": GrammarFactDefinition(
        fact_type="animacy",
        languages=("en",),
        required_pos=("noun",),
        display_label="Animacy",
        description="Classify nouns as animate or inanimate",
        generatable=True,
    ),
    "infinitive": GrammarFactDefinition(
        fact_type="infinitive",
        languages=("lt",),
        required_pos=("verb",),
        display_label="Infinitive",
        description="Lithuanian verb infinitive principal part",
        release_sync=True,
    ),
    "3s_present": GrammarFactDefinition(
        fact_type="3s_present",
        languages=("lt",),
        required_pos=("verb",),
        display_label="3rd Singular Present",
        description="Lithuanian third-person singular present principal part",
        release_sync=True,
    ),
    "3s_past": GrammarFactDefinition(
        fact_type="3s_past",
        languages=("lt",),
        required_pos=("verb",),
        display_label="3rd Singular Past",
        description="Lithuanian third-person singular past principal part",
        release_sync=True,
    ),
    "3p_present": GrammarFactDefinition(
        fact_type="3p_present",
        languages=("lt",),
        required_pos=("verb",),
        display_label="Legacy 3rd Person Present",
        description="Legacy Lithuanian third-person principal part; prefer 3s_present",
        release_sync=True,
    ),
    "3p_past": GrammarFactDefinition(
        fact_type="3p_past",
        languages=("lt",),
        required_pos=("verb",),
        display_label="Legacy 3rd Person Past",
        description="Legacy Lithuanian third-person principal part; prefer 3s_past",
        release_sync=True,
    ),
    "1s_present": GrammarFactDefinition(
        fact_type="1s_present",
        languages=("it",),
        required_pos=("verb",),
        display_label="1st Singular Present",
        description="Italian first-person singular present principal part",
        release_sync=True,
    ),
    "1s_past": GrammarFactDefinition(
        fact_type="1s_past",
        languages=("it",),
        required_pos=("verb",),
        display_label="1st Singular Past",
        description="Italian first-person singular past principal part",
        release_sync=True,
    ),
    "1s_future": GrammarFactDefinition(
        fact_type="1s_future",
        languages=("it",),
        required_pos=("verb",),
        display_label="1st Singular Future",
        description="Italian first-person singular future principal part",
        release_sync=True,
    ),
    "plural": GrammarFactDefinition(
        fact_type="plural",
        languages=IRREGULAR_PLURAL_LANGUAGES,
        required_pos=("noun",),
        display_label="Plural",
        description="Irregular or non-derivable noun plural override",
        release_sync=True,
    ),
    "number_type": GrammarFactDefinition(
        fact_type="number_type",
        languages=NUMBER_TYPE_LANGUAGES,
        required_pos=("noun",),
        display_label="Number Type",
        description=(
            "Exceptional noun number behavior: uncountable, plurale_tantum, "
            "singulare_tantum, or both"
        ),
        release_sync=True,
    ),
    "past": GrammarFactDefinition(
        fact_type="past",
        languages=("en",),
        required_pos=("verb",),
        display_label="Past",
        description="English irregular simple past principal part",
        release_sync=True,
    ),
    "past_participle": GrammarFactDefinition(
        fact_type="past_participle",
        languages=PARTICIPLE_OVERRIDE_LANGUAGES,
        required_pos=("verb",),
        display_label="Past Participle",
        description=(
            "Irregular or non-derivable past participle principal part; for Swedish, "
            "stores the generator-required perfect-form principal part"
        ),
        release_sync=True,
    ),
    "feminine_form": GrammarFactDefinition(
        fact_type="feminine_form",
        languages=("fr",),
        required_pos=("adjective",),
        display_label="Feminine Form",
        description="French irregular or non-derivable feminine adjective form",
        release_sync=True,
    ),
    "comparative": GrammarFactDefinition(
        fact_type="comparative",
        languages=COMPARISON_OVERRIDE_LANGUAGES,
        required_pos=("adjective", "adverb"),
        display_label="Comparative",
        description="Irregular comparative form",
        release_sync=True,
    ),
    "superlative": GrammarFactDefinition(
        fact_type="superlative",
        languages=COMPARISON_OVERRIDE_LANGUAGES,
        required_pos=("adjective", "adverb"),
        display_label="Superlative",
        description="Irregular superlative form",
        release_sync=True,
    ),
    "gradability": GrammarFactDefinition(
        fact_type="gradability",
        languages=("en",),
        required_pos=("adjective", "adverb"),
        display_label="Gradability",
        description=(
            "Whether an adjective/adverb compares synthetically (-er/-est), "
            "periphrastically (more/most), or not at all: synthetic, "
            "periphrastic, or non_gradable"
        ),
        release_sync=True,
    ),
}


RELEASE_GRAMMAR_FACT_TYPES: Dict[str, set[str]] = {}
for _definition in GRAMMAR_FACT_DEFINITIONS.values():
    if not _definition.release_sync:
        continue
    for _language_code in _definition.languages:
        RELEASE_GRAMMAR_FACT_TYPES.setdefault(_language_code, set()).add(_definition.fact_type)

RELEASE_GRAMMAR_FACT_PREFIXES: Dict[str, Tuple[str, ...]] = {
    language_code: (VERB_FORM_OVERRIDE_PREFIX,) for language_code in TIER_1_2_LANGUAGES
}


def get_generatable_fact_definitions() -> Dict[str, GrammarFactDefinition]:
    """Return grammar facts that have implemented LLM generation."""
    return {
        fact_type: definition
        for fact_type, definition in GRAMMAR_FACT_DEFINITIONS.items()
        if definition.generatable
    }


def legacy_supported_fact_types() -> Dict[str, Dict[str, Any]]:
    """Return the historical dict shape consumed by Lape and workqueue code."""
    return {
        fact_type: {
            "languages": list(definition.languages),
            "required_pos": list(definition.required_pos),
            "description": definition.description,
        }
        for fact_type, definition in get_generatable_fact_definitions().items()
    }


def is_release_grammar_fact_type(language_code: str, fact_type: str) -> bool:
    """Return whether a grammar fact should be imported/synced from release files."""
    if fact_type in RELEASE_GRAMMAR_FACT_TYPES.get(language_code, set()):
        return True
    return any(
        fact_type.startswith(prefix)
        for prefix in RELEASE_GRAMMAR_FACT_PREFIXES.get(language_code, ())
    )


def get_release_grammar_fact_languages() -> Tuple[str, ...]:
    """Return languages that may contain release-synced grammar facts."""
    languages = set(RELEASE_GRAMMAR_FACT_TYPES)
    languages.update(RELEASE_GRAMMAR_FACT_PREFIXES)
    return tuple(sorted(languages))


def iter_language_fact_definitions(
    language_code: str, pos_type: str | None = None, generatable_only: bool = False
) -> Iterable[GrammarFactDefinition]:
    """Yield fact definitions applicable to a language and optional POS."""
    definitions: Mapping[str, GrammarFactDefinition]
    if generatable_only:
        definitions = get_generatable_fact_definitions()
    else:
        definitions = GRAMMAR_FACT_DEFINITIONS
    for definition in definitions.values():
        if language_code not in definition.languages:
            continue
        if pos_type is not None and pos_type not in definition.required_pos:
            continue
        yield definition
