"""Swedish grammatical/function-word data."""

from typing import Final

from langtools.grammatical_word_schema import (
    ALSO_LEMMA_SUBCATEGORIES,
    GRAMMATICAL_ONLY_SUBCATEGORIES,
    GrammaticalWordsBySubcategory,
    build_subcategory_mapping,
    union_subcategories,
)

SWEDISH_PERSONAL_PRONOUNS: Final[frozenset[str]] = frozenset(
    {
        "jag",
        "du",
        "han",
        "hon",
        "den",
        "det",
        "vi",
        "ni",
        "de",
        "mig",
        "dig",
        "oss",
        "er",
        "min",
        "mitt",
        "mina",
        "din",
        "ditt",
        "dina",
        "hans",
        "hennes",
        "vår",
        "vårt",
        "våra",
        "er",
        "ert",
        "era",
        "deras",
        "sin",
        "sitt",
        "sina",
    }
)

SWEDISH_GRAMMATICAL_WORDS: Final[frozenset[str]] = frozenset(
    {
        "en",
        "ett",
        "den",
        "det",
        "inte",
        "ju",
        "väl",
        "också",
        "bara",
        "redan",
        "än",
        "är",
        "var",
        "vara",
        "blir",
        "blev",
        "ha",
        "har",
        "hade",
        "ska",
        "skall",
        "skulle",
        "kan",
        "kunde",
        "får",
        "fick",
        "måste",
        "må",
        "vill",
        "ville",
    }
)

SWEDISH_FUNCTION_WORDS: Final[frozenset[str]] = frozenset(
    {
        "i",
        "på",
        "med",
        "av",
        "för",
        "till",
        "från",
        "om",
        "utan",
        "under",
        "över",
        "mellan",
        "och",
        "eller",
        "men",
        "att",
        "som",
        "eftersom",
        "när",
        "ifall",
    }
)

SWEDISH_NON_PERSONAL_PRONOUNS: Final[frozenset[str]] = frozenset(
    {
        "denna",
        "detta",
        "dessa",
        "den",
        "det",
        "de",
        "vem",
        "vad",
        "vilken",
        "vilket",
        "vilka",
        "någon",
        "något",
        "några",
        "ingen",
        "inget",
        "inga",
    }
)

SWEDISH_GRAMMATICAL_WORDS_BY_SUBCATEGORY: Final[GrammaticalWordsBySubcategory] = (
    build_subcategory_mapping(
        personal_pronouns=SWEDISH_PERSONAL_PRONOUNS,
        grammatical_words=SWEDISH_GRAMMATICAL_WORDS,
        function_words=SWEDISH_FUNCTION_WORDS,
        non_personal_pronouns=SWEDISH_NON_PERSONAL_PRONOUNS,
        articles=frozenset({"en", "ett", "den", "det"}),
        auxiliaries=frozenset(
            {
                "är",
                "var",
                "vara",
                "blir",
                "blev",
                "ha",
                "har",
                "hade",
                "ska",
                "skall",
                "skulle",
                "kan",
                "kunde",
                "får",
                "fick",
                "måste",
                "må",
                "vill",
                "ville",
            }
        ),
        particles=frozenset({"inte", "ju", "väl", "också", "bara", "redan", "än"}),
        prepositions=frozenset(
            {"i", "på", "med", "av", "för", "till", "från", "om", "utan", "under", "över", "mellan"}
        ),
        conjunctions=frozenset({"och", "eller", "men", "att", "som", "eftersom", "när", "ifall"}),
        determiners=frozenset({"någon", "något", "några", "ingen", "inget", "inga"}),
        interrogatives=frozenset({"vem", "vad", "vilken", "vilket", "vilka"}),
        demonstratives=frozenset({"denna", "detta", "dessa", "den", "det", "de"}),
    )
)

SWEDISH_GRAMMATICAL_ONLY: Final[frozenset[str]] = union_subcategories(
    SWEDISH_GRAMMATICAL_WORDS_BY_SUBCATEGORY, GRAMMATICAL_ONLY_SUBCATEGORIES
)

SWEDISH_ALSO_LEMMA: Final[frozenset[str]] = union_subcategories(
    SWEDISH_GRAMMATICAL_WORDS_BY_SUBCATEGORY, ALSO_LEMMA_SUBCATEGORIES
)

SWEDISH_ALL_TIERS: Final[frozenset[str]] = frozenset(SWEDISH_GRAMMATICAL_ONLY | SWEDISH_ALSO_LEMMA)
