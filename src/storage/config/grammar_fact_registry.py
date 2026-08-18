"""Shared registry for grammar fact capabilities and release behavior.

Two independent axes
--------------------

A fact type is classified on two axes that have nothing to do with each other.
Confusing them is how facts get silently lost.

**EXPORTED** -- is it *not* derivable mechanically, in Python, from the rest of
``data/release``? If it is derivable, the release tree already contains
everything needed to recompute it and shipping it would just cache a
derivation. If it is not, it must be exported or a rebuild destroys it.
:data:`EXPORTED_FACT_TYPES` / :data:`NOT_EXPORTED_FACT_TYPES` below.

**GENERATED** -- can it be produced automatically at all, by Python *or* by an
LLM? That is the ``generatable`` flag, and it answers "can an agent fill this
in", not "may we drop it".

The pair is orthogonal, and three of the four quadrants are occupied::

                     GENERATED=no                  GENERATED=yes
    EXPORTED=yes     infinitive, plural, past,     grammatical_gender,
                     past_participle, comparative, countability, animacy,
                     superlative, feminine_form,   verb_transitivity,
                     number_type, gradability,     verb_reflexivity,
                     1s_*/3s_*/3p_* principal parts auxiliary_verb,
                                                   measure_words,
                                                   fanciful_collective
    EXPORTED=no      -- must stay empty --         declension_class

The bottom-left quadrant has to stay empty, and the test enforces it: a fact
that can neither be regenerated nor survives a rebuild could only have been
typed by a human, and the next rebuild throws it away.

The bottom-right quadrant is deliberately thin. Being GENERATED is not on its
own a reason to skip exporting -- only being *derivable in Python from the rest
of the release tree* is, and among the grammar facts exactly one thing is.

Why the axes come apart, in three worked examples:

* ``measure_words`` is GENERATED (an LLM writes it) and still EXPORTED. An LLM
  call is not a mechanical derivation -- it costs money and two runs need not
  agree, so the file is the record.
* ``grammatical_gender`` is GENERATED and EXPORTED. Nothing in Python derives
  it from the release tree, and :func:`langtools.lt.declension.decline_noun`
  *consumes* it to choose between overlapping endings, so a rebuild without it
  declines nouns by the wrong pattern.
* ``declension_class`` is GENERATED and NOT exported -- the one case that turns
  on "from the rest of ``data/release``". ``decline_noun`` computes it in pure
  Python from the noun plus its gender, both of which ship. Note the
  dependency: that holds *because* ``grammatical_gender`` is exported. If gender
  ever leaves the release tree, this one has to follow it back in.

``GrammarFactDefinition.release_sync`` is derived from the lists below, and
``src/tests/storage/test_grammar_fact_registry.py`` fails if a fact type is
missing from both, appears in both, or lands in the empty quadrant.
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
    #: GENERATED axis: can this be produced automatically, by Python or by an
    #: LLM? Independent of release_sync -- see the module docstring.
    generatable: bool = False
    #: EXPORTED axis. Derived from EXPORTED_FACT_TYPES; never set on a definition.
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
    # GENERATED, and exported anyway: an LLM writes these, which is not a
    # mechanical derivation -- regenerating costs money and two runs need not
    # agree, so the file is the record.
    "measure_words",  # zh classifiers
    "fanciful_collective",  # en ornamental collective nouns
    # GENERATED lexical classifications. No Python derives any of these from
    # the release tree, so the EXPORTED rule puts all of them here: without
    # them a rebuild has to re-run an agent, pay for it again, and accept
    # whatever the second run says.
    #
    # Two are read back by mechanical generators, the same way gender is:
    # decline_noun() takes gender, and the English form generator takes
    # countability (langtools/en/llm_forms.py:133) and number_type to decide
    # whether a plural slot exists at all.
    "grammatical_gender",  # fr, lt, es, de, pt, it; feeds decline_noun()
    "countability",  # en; feeds the English form generator
    "animacy",  # en
    "verb_transitivity",  # en
    "verb_reflexivity",  # fr, es, de, lt, it
    "auxiliary_verb",  # fr, de, it, nl; selects the compound-tense auxiliary
)

#: Fact types deliberately kept out of ``data/release``.
#: Everything here must be GENERATED -- see the module docstring's empty
#: quadrant: a fact that is neither generated nor exported cannot survive a
#: rebuild.
NOT_EXPORTED_FACT_TYPES: Tuple[str, ...] = (
    # The only true derivation among the grammar facts: decline_noun() computes
    # it in pure Python from the noun plus its gender
    # (langtools/lt/declension.py), and both of those ship, so the release tree
    # already contains everything needed to recompute it. That holds only
    # because grammatical_gender is exported -- if gender ever leaves the
    # release tree, this has to follow it back in.
    "declension_class",  # lt
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
    """Return grammar facts that can be produced automatically.

    "Automatically" spans both mechanisms: an LLM agent (most of these) and pure
    Python (``declension_class`` comes out of
    :func:`langtools.lt.declension.decline_noun`). This is the GENERATED axis in
    the module docstring, and it says nothing about whether the fact is exported
    -- see :data:`EXPORTED_FACT_TYPES` for that, and do not use this flag to
    decide it.
    """
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
