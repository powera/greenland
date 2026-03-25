"""Shared typed schema for language-specific grammatical-word subcategories."""

from typing import Final, Literal, Mapping, TypeAlias

GrammaticalSubcategory: TypeAlias = Literal[
    "personal_pronouns",
    "articles",
    "auxiliaries",
    "particles",
    "prepositions",
    "conjunctions",
    "determiners",
    "interrogatives",
    "demonstratives",
    "contractions",
]

GrammaticalWordsBySubcategory: TypeAlias = Mapping[GrammaticalSubcategory, frozenset[str]]

GRAMMATICAL_SUBCATEGORY_KEYS: Final[tuple[GrammaticalSubcategory, ...]] = (
    "personal_pronouns",
    "articles",
    "auxiliaries",
    "particles",
    "prepositions",
    "conjunctions",
    "determiners",
    "interrogatives",
    "demonstratives",
    "contractions",
)

GRAMMATICAL_ONLY_SUBCATEGORIES: Final[tuple[GrammaticalSubcategory, ...]] = (
    "personal_pronouns",
    "articles",
    "auxiliaries",
    "particles",
    "contractions",
)

ALSO_LEMMA_SUBCATEGORIES: Final[tuple[GrammaticalSubcategory, ...]] = (
    "prepositions",
    "conjunctions",
    "determiners",
    "interrogatives",
    "demonstratives",
)


def union_subcategories(
    by_subcategory: GrammaticalWordsBySubcategory,
    subcategories: tuple[GrammaticalSubcategory, ...],
) -> frozenset[str]:
    """Return the union of words from the requested *subcategories*."""
    return frozenset(
        word
        for subcategory in subcategories
        for word in by_subcategory.get(subcategory, frozenset())
    )


def build_subcategory_mapping(
    *,
    personal_pronouns: frozenset[str],
    grammatical_words: frozenset[str],
    function_words: frozenset[str],
    non_personal_pronouns: frozenset[str],
    articles: frozenset[str] = frozenset(),
    auxiliaries: frozenset[str] = frozenset(),
    particles: frozenset[str] = frozenset(),
    prepositions: frozenset[str] = frozenset(),
    conjunctions: frozenset[str] = frozenset(),
    determiners: frozenset[str] = frozenset(),
    interrogatives: frozenset[str] = frozenset(),
    demonstratives: frozenset[str] = frozenset(),
    contractions: frozenset[str] = frozenset(),
) -> dict[GrammaticalSubcategory, frozenset[str]]:
    """Build a full subcategory mapping while keeping legacy tier coverage stable."""
    normalized_articles = articles & grammatical_words
    normalized_auxiliaries = auxiliaries & grammatical_words
    normalized_contractions = contractions & grammatical_words
    normalized_particles = (
        particles & grammatical_words
        if particles
        else grammatical_words
        - normalized_articles
        - normalized_auxiliaries
        - normalized_contractions
    )

    normalized_prepositions = prepositions & function_words
    normalized_conjunctions = (
        conjunctions & function_words if conjunctions else function_words - normalized_prepositions
    )
    if not prepositions:
        normalized_prepositions = function_words - normalized_conjunctions

    normalized_interrogatives = interrogatives & non_personal_pronouns
    normalized_demonstratives = demonstratives & non_personal_pronouns
    normalized_determiners = (
        determiners & non_personal_pronouns
        if determiners
        else non_personal_pronouns - normalized_interrogatives - normalized_demonstratives
    )

    return {
        "personal_pronouns": personal_pronouns,
        "articles": normalized_articles,
        "auxiliaries": normalized_auxiliaries,
        "particles": normalized_particles,
        "prepositions": normalized_prepositions,
        "conjunctions": normalized_conjunctions,
        "determiners": normalized_determiners,
        "interrogatives": normalized_interrogatives,
        "demonstratives": normalized_demonstratives,
        "contractions": normalized_contractions,
    }
