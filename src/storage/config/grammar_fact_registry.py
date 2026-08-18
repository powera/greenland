"""Shared registry for grammar fact capabilities and release behavior.

What gets exported
------------------

The test for whether a fact belongs in ``data/release`` is:

    can a *mechanical* generator reproduce it from what the release files
    already carry?

If yes, it is derived data and stays in the database -- a rebuild recomputes it
for free and gets the same answer. If no, it must be exported, or a rebuild
destroys it.

``generatable`` is **not** that test and must not be used as one: it means "an
LLM agent knows how to produce this". An LLM call is not reproduction -- it
costs money and two runs need not agree. ``measure_words`` is the worked
example: it is ``generatable=True`` *and* exported, because regenerating a
Chinese classifier means paying for it again and possibly getting something
else. The rule cuts across ``generatable`` in both directions.

Three groups end up exported:

* **Principal parts and overrides** -- ``infinitive``, ``plural``, ``past``,
  ``comparative`` and friends. These exist precisely because the mechanical
  rule cannot produce them; "irregular or non-derivable" is what the
  descriptions say.
* **LLM-only content** -- ``measure_words``, ``fanciful_collective``.
* **Classifications a mechanical generator consumes as input** --
  ``grammatical_gender`` is read by :func:`langtools.lt.declension.decline_noun`
  to choose between overlapping endings. Nothing derives it, and a rebuild
  without it silently declines nouns by the wrong pattern.

One group stays in the database: **outputs of the mechanical generators**.
``declension_class`` is computed by ``decline_noun`` from the noun plus its
gender, so exporting it would ship a cached derivation the importer could
recompute. Note the dependency -- that is only true *because*
``grammatical_gender`` ships.

:data:`EXPORTED_FACT_TYPES` and :data:`NOT_EXPORTED_FACT_TYPES` below are the
source of truth; ``GrammarFactDefinition.release_sync`` is derived from them,
and ``src/tests/storage/test_grammar_fact_registry.py`` fails if a fact type is
missing from both.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
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
    #: Derived from EXPORTED_FACT_TYPES; never set this on a definition.
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
    "fanciful_collective": GrammarFactDefinition(
        fact_type="fanciful_collective",
        languages=("en",),
        required_pos=("noun",),
        display_label="Fanciful Collective",
        description=(
            "Ornamental English collective noun tied to one animal (a murder of "
            "crows, a parliament of owls); decorative rather than load-bearing, "
            "since the ordinary term (a flock of crows) is always acceptable"
        ),
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
    ),
    "3s_present": GrammarFactDefinition(
        fact_type="3s_present",
        languages=("lt",),
        required_pos=("verb",),
        display_label="3rd Singular Present",
        description="Lithuanian third-person singular present principal part",
    ),
    "3s_past": GrammarFactDefinition(
        fact_type="3s_past",
        languages=("lt",),
        required_pos=("verb",),
        display_label="3rd Singular Past",
        description="Lithuanian third-person singular past principal part",
    ),
    "3p_present": GrammarFactDefinition(
        fact_type="3p_present",
        languages=("lt",),
        required_pos=("verb",),
        display_label="Legacy 3rd Person Present",
        description="Legacy Lithuanian third-person principal part; prefer 3s_present",
    ),
    "3p_past": GrammarFactDefinition(
        fact_type="3p_past",
        languages=("lt",),
        required_pos=("verb",),
        display_label="Legacy 3rd Person Past",
        description="Legacy Lithuanian third-person principal part; prefer 3s_past",
    ),
    "1s_present": GrammarFactDefinition(
        fact_type="1s_present",
        languages=("it",),
        required_pos=("verb",),
        display_label="1st Singular Present",
        description="Italian first-person singular present principal part",
    ),
    "1s_past": GrammarFactDefinition(
        fact_type="1s_past",
        languages=("it",),
        required_pos=("verb",),
        display_label="1st Singular Past",
        description="Italian first-person singular past principal part",
    ),
    "1s_future": GrammarFactDefinition(
        fact_type="1s_future",
        languages=("it",),
        required_pos=("verb",),
        display_label="1st Singular Future",
        description="Italian first-person singular future principal part",
    ),
    "plural": GrammarFactDefinition(
        fact_type="plural",
        languages=IRREGULAR_PLURAL_LANGUAGES,
        required_pos=("noun",),
        display_label="Plural",
        description="Irregular or non-derivable noun plural override",
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
    ),
    "past": GrammarFactDefinition(
        fact_type="past",
        languages=("en",),
        required_pos=("verb",),
        display_label="Past",
        description="English irregular simple past principal part",
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
    ),
    "feminine_form": GrammarFactDefinition(
        fact_type="feminine_form",
        languages=("fr",),
        required_pos=("adjective",),
        display_label="Feminine Form",
        description="French irregular or non-derivable feminine adjective form",
    ),
    "comparative": GrammarFactDefinition(
        fact_type="comparative",
        languages=COMPARISON_OVERRIDE_LANGUAGES,
        required_pos=("adjective", "adverb"),
        display_label="Comparative",
        description="Irregular comparative form",
    ),
    "superlative": GrammarFactDefinition(
        fact_type="superlative",
        languages=COMPARISON_OVERRIDE_LANGUAGES,
        required_pos=("adjective", "adverb"),
        display_label="Superlative",
        description="Irregular superlative form",
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
    ),
}


#: Fact types written to, and read back from, ``data/release/lemmas/{lang}.jsonl``.
#: Nothing mechanical reproduces these, so a rebuild without them loses data.
#: Keep the reason on each entry; see the module docstring for the rule.
EXPORTED_FACT_TYPES: Tuple[str, ...] = (
    # Principal parts. A conjugator takes these as input; they are not
    # derivable from the lemma.
    "infinitive",  # lt
    "3s_present",  # lt
    "3s_past",  # lt
    "3p_present",  # lt, legacy -- prefer 3s_present
    "3p_past",  # lt, legacy -- prefer 3s_past
    "1s_present",  # it
    "1s_past",  # it
    "1s_future",  # it
    # Overrides. These exist *because* the mechanical rule is wrong here.
    "plural",  # irregular noun plural
    "past",  # en irregular simple past
    "past_participle",  # irregular participle
    "feminine_form",  # fr irregular feminine adjective
    "comparative",  # irregular comparative
    "superlative",  # irregular superlative
    "number_type",  # exceptional number behavior (plurale tantum, etc.)
    "gradability",  # selects which comparison strategy applies at all
    # LLM-only content: regenerating costs money and need not agree with
    # itself, so the file is the record.
    "measure_words",  # zh classifiers
    "fanciful_collective",  # en ornamental collective nouns
    # An LLM classification that a mechanical generator consumes as *input*:
    # decline_noun() uses gender to disambiguate overlapping endings, so a
    # rebuild without it declines by the wrong pattern.
    "grammatical_gender",  # fr, lt, es, de, pt, it
)

#: Fact types deliberately kept out of ``data/release``.
NOT_EXPORTED_FACT_TYPES: Tuple[str, ...] = (
    # An *output* of a mechanical generator rather than an input to one:
    # decline_noun() computes it from the noun plus its gender
    # (langtools/lt/declension.py), so exporting it would ship a cached
    # derivation. Safe to omit only because grammatical_gender is exported --
    # if that ever changes, revisit this one with it.
    "declension_class",  # lt
    # The rest are LLM classifications that nothing mechanical derives, so by
    # the rule above they are export *candidates*. They are parked here rather
    # than promoted because promoting one rewrites release files, which is a
    # data decision rather than a code cleanup. countability is the strongest
    # candidate: langtools/en/llm_forms.py reads it the way decline_noun reads
    # gender.
    "countability",  # en; consumed by the English form generator
    "animacy",  # en
    "verb_transitivity",  # en
    "verb_reflexivity",  # fr, es, de, lt, it
    "auxiliary_verb",  # fr, de, it, nl; selects the compound-tense auxiliary
)

# The lists above are the source of truth; the per-definition flag follows them
# so the two cannot disagree.
GRAMMAR_FACT_DEFINITIONS = {
    fact_type: replace(definition, release_sync=fact_type in EXPORTED_FACT_TYPES)
    for fact_type, definition in GRAMMAR_FACT_DEFINITIONS.items()
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
