"""Italian grammatical/function-word data."""

from typing import Final

from langtools.grammatical_word_schema import (
    ALSO_LEMMA_SUBCATEGORIES,
    GRAMMATICAL_ONLY_SUBCATEGORIES,
    GrammaticalWordsBySubcategory,
    build_subcategory_mapping,
    union_subcategories,
)

ITALIAN_PERSONAL_PRONOUNS: Final[frozenset[str]] = frozenset(
    {
        "io",
        "tu",
        "lui",
        "lei",
        "noi",
        "voi",
        "loro",
        "mi",
        "ti",
        "ci",
        "vi",
        "me",
        "te",
        "mio",
        "mia",
        "miei",
        "mie",
        "tuo",
        "tua",
        "tuoi",
        "tue",
        "suo",
        "sua",
        "suoi",
        "sue",
        "nostro",
        "nostra",
        "nostri",
        "nostre",
        "vostro",
        "vostra",
        "vostri",
        "vostre",
    }
)

ITALIAN_GRAMMATICAL_WORDS: Final[frozenset[str]] = frozenset(
    {
        "il",
        "lo",
        "la",
        "i",
        "gli",
        "le",
        "un",
        "uno",
        "una",
        "non",
        "si",
        "ne",
        "ci",
        "c'è",
        "ce",
        "sono",
        "sei",
        "è",
        "siamo",
        "siete",
        "ero",
        "eri",
        "era",
        "erano",
        "ho",
        "hai",
        "ha",
        "abbiamo",
        "avete",
        "hanno",
        "devo",
        "devi",
        "deve",
        "dobbiamo",
        "dovete",
        "devono",
        "posso",
        "puoi",
        "può",
        "possiamo",
        "potete",
        "possono",
    }
)

ITALIAN_FUNCTION_WORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "da",
        "di",
        "in",
        "con",
        "su",
        "per",
        "tra",
        "fra",
        "come",
        "senza",
        "verso",
        "durante",
        "dopo",
        "prima",
        "e",
        "o",
        "ma",
        "perché",
        "se",
        "che",
        "quando",
        "mentre",
        "anche",
        "pure",
    }
)

ITALIAN_NON_PERSONAL_PRONOUNS: Final[frozenset[str]] = frozenset(
    {
        "questo",
        "questa",
        "questi",
        "queste",
        "quello",
        "quella",
        "quelli",
        "quelle",
        "chi",
        "che",
        "cosa",
        "quale",
        "quali",
        "quanto",
        "quanta",
        "quanti",
        "quante",
    }
)

ITALIAN_GRAMMATICAL_WORDS_BY_SUBCATEGORY: Final[GrammaticalWordsBySubcategory] = (
    build_subcategory_mapping(
        personal_pronouns=ITALIAN_PERSONAL_PRONOUNS,
        grammatical_words=ITALIAN_GRAMMATICAL_WORDS,
        function_words=ITALIAN_FUNCTION_WORDS,
        non_personal_pronouns=ITALIAN_NON_PERSONAL_PRONOUNS,
        articles=frozenset({"il", "lo", "la", "i", "gli", "le", "un", "uno", "una"}),
        auxiliaries=frozenset(
            {
                "sono",
                "sei",
                "è",
                "siamo",
                "siete",
                "ero",
                "eri",
                "era",
                "erano",
                "ho",
                "hai",
                "ha",
                "abbiamo",
                "avete",
                "hanno",
                "devo",
                "devi",
                "deve",
                "dobbiamo",
                "dovete",
                "devono",
                "posso",
                "puoi",
                "può",
                "possiamo",
                "potete",
                "possono",
            }
        ),
        contractions=frozenset({"c'è"}),
        prepositions=frozenset(
            {
                "a",
                "da",
                "di",
                "in",
                "con",
                "su",
                "per",
                "tra",
                "fra",
                "senza",
                "verso",
                "durante",
                "dopo",
                "prima",
            }
        ),
        conjunctions=frozenset(
            {"e", "o", "ma", "perché", "se", "che", "quando", "mentre", "anche", "pure", "come"}
        ),
        interrogatives=frozenset(
            {"chi", "che", "cosa", "quale", "quali", "quanto", "quanta", "quanti", "quante"}
        ),
        demonstratives=frozenset(
            {"questo", "questa", "questi", "queste", "quello", "quella", "quelli", "quelle"}
        ),
    )
)

ITALIAN_GRAMMATICAL_ONLY: Final[frozenset[str]] = union_subcategories(
    ITALIAN_GRAMMATICAL_WORDS_BY_SUBCATEGORY, GRAMMATICAL_ONLY_SUBCATEGORIES
)

ITALIAN_ALSO_LEMMA: Final[frozenset[str]] = union_subcategories(
    ITALIAN_GRAMMATICAL_WORDS_BY_SUBCATEGORY, ALSO_LEMMA_SUBCATEGORIES
)

ITALIAN_ALL_TIERS: Final[frozenset[str]] = frozenset(ITALIAN_GRAMMATICAL_ONLY | ITALIAN_ALSO_LEMMA)
