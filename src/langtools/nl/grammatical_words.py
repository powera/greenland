"""Dutch grammatical/function-word data."""

from typing import Final

from langtools.grammatical_word_schema import (
    ALSO_LEMMA_SUBCATEGORIES,
    GRAMMATICAL_ONLY_SUBCATEGORIES,
    GrammaticalWordsBySubcategory,
    build_subcategory_mapping,
    union_subcategories,
)

DUTCH_PERSONAL_PRONOUNS: Final[frozenset[str]] = frozenset(
    {
        "ik",
        "jij",
        "je",
        "u",
        "hij",
        "zij",
        "ze",
        "het",
        "wij",
        "we",
        "jullie",
        "hen",
        "hun",
        "mij",
        "me",
        "jou",
        "ons",
        "mijn",
        "mijne",
        "jouw",
        "jouwe",
        "uw",
        "zijn",
        "haar",
        "ons",
        "onze",
        "jullie",
        "hun",
    }
)

DUTCH_GRAMMATICAL_WORDS: Final[frozenset[str]] = frozenset(
    {
        "de",
        "het",
        "een",
        "niet",
        "wel",
        "al",
        "nog",
        "ook",
        "maar",
        "er",
        "hier",
        "daar",
        "is",
        "ben",
        "bent",
        "zijn",
        "was",
        "waren",
        "heb",
        "hebt",
        "heeft",
        "hebben",
        "had",
        "hadden",
        "zal",
        "zullen",
        "zou",
        "zouden",
        "kan",
        "kunnen",
        "kon",
        "konden",
        "moet",
        "moeten",
        "moest",
        "moesten",
        "mag",
        "mogen",
        "wil",
        "willen",
    }
)

DUTCH_FUNCTION_WORDS: Final[frozenset[str]] = frozenset(
    {
        "in",
        "op",
        "aan",
        "uit",
        "bij",
        "met",
        "voor",
        "van",
        "naar",
        "over",
        "onder",
        "tussen",
        "zonder",
        "door",
        "en",
        "of",
        "want",
        "omdat",
        "als",
        "dat",
        "terwijl",
        "indien",
        "hoewel",
    }
)

DUTCH_NON_PERSONAL_PRONOUNS: Final[frozenset[str]] = frozenset(
    {
        "dit",
        "dat",
        "deze",
        "die",
        "degene",
        "wie",
        "wat",
        "welke",
        "welk",
        "welken",
        "iets",
        "niets",
        "iedereen",
        "niemand",
    }
)

DUTCH_GRAMMATICAL_WORDS_BY_SUBCATEGORY: Final[GrammaticalWordsBySubcategory] = (
    build_subcategory_mapping(
        personal_pronouns=DUTCH_PERSONAL_PRONOUNS,
        grammatical_words=DUTCH_GRAMMATICAL_WORDS,
        function_words=DUTCH_FUNCTION_WORDS,
        non_personal_pronouns=DUTCH_NON_PERSONAL_PRONOUNS,
        articles=frozenset({"de", "het", "een"}),
        auxiliaries=frozenset(
            {
                "is",
                "ben",
                "bent",
                "zijn",
                "was",
                "waren",
                "heb",
                "hebt",
                "heeft",
                "hebben",
                "had",
                "hadden",
                "zal",
                "zullen",
                "zou",
                "zouden",
                "kan",
                "kunnen",
                "kon",
                "konden",
                "moet",
                "moeten",
                "moest",
                "moesten",
                "mag",
                "mogen",
                "wil",
                "willen",
            }
        ),
        particles=frozenset({"niet", "wel", "al", "nog", "ook", "maar", "er", "hier", "daar"}),
        prepositions=frozenset(
            {
                "in",
                "op",
                "aan",
                "uit",
                "bij",
                "met",
                "voor",
                "van",
                "naar",
                "over",
                "onder",
                "tussen",
                "zonder",
                "door",
            }
        ),
        conjunctions=frozenset(
            {"en", "of", "want", "omdat", "als", "dat", "terwijl", "indien", "hoewel"}
        ),
        determiners=frozenset({"iets", "niets", "iedereen", "niemand"}),
        interrogatives=frozenset({"wie", "wat", "welke", "welk", "welken"}),
        demonstratives=frozenset({"dit", "dat", "deze", "die", "degene"}),
    )
)

DUTCH_GRAMMATICAL_ONLY: Final[frozenset[str]] = union_subcategories(
    DUTCH_GRAMMATICAL_WORDS_BY_SUBCATEGORY, GRAMMATICAL_ONLY_SUBCATEGORIES
)

DUTCH_ALSO_LEMMA: Final[frozenset[str]] = union_subcategories(
    DUTCH_GRAMMATICAL_WORDS_BY_SUBCATEGORY, ALSO_LEMMA_SUBCATEGORIES
)

DUTCH_ALL_TIERS: Final[frozenset[str]] = frozenset(DUTCH_GRAMMATICAL_ONLY | DUTCH_ALSO_LEMMA)
