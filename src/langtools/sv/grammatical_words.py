"""Swedish grammatical/function-word data."""

from typing import Final

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

SWEDISH_GRAMMATICAL_ONLY: Final[frozenset[str]] = frozenset(
    SWEDISH_PERSONAL_PRONOUNS | SWEDISH_GRAMMATICAL_WORDS
)

SWEDISH_ALSO_LEMMA: Final[frozenset[str]] = frozenset(
    SWEDISH_FUNCTION_WORDS | SWEDISH_NON_PERSONAL_PRONOUNS
)

SWEDISH_ALL_TIERS: Final[frozenset[str]] = frozenset(SWEDISH_GRAMMATICAL_ONLY | SWEDISH_ALSO_LEMMA)
