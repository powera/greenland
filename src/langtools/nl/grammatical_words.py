"""Dutch grammatical/function-word data."""

from typing import Final

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

DUTCH_GRAMMATICAL_ONLY: Final[frozenset[str]] = frozenset(
    DUTCH_PERSONAL_PRONOUNS | DUTCH_GRAMMATICAL_WORDS
)

DUTCH_ALSO_LEMMA: Final[frozenset[str]] = frozenset(
    DUTCH_FUNCTION_WORDS | DUTCH_NON_PERSONAL_PRONOUNS
)

DUTCH_ALL_TIERS: Final[frozenset[str]] = frozenset(DUTCH_GRAMMATICAL_ONLY | DUTCH_ALSO_LEMMA)
