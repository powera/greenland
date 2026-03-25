"""Portuguese grammatical/function-word data."""

from typing import Final

from langtools.grammatical_word_schema import (
    ALSO_LEMMA_SUBCATEGORIES,
    GRAMMATICAL_ONLY_SUBCATEGORIES,
    GrammaticalWordsBySubcategory,
    build_subcategory_mapping,
    union_subcategories,
)

PORTUGUESE_PERSONAL_PRONOUNS: Final[frozenset[str]] = frozenset(
    {
        "eu",
        "tu",
        "você",
        "ele",
        "ela",
        "nós",
        "vós",
        "vocês",
        "eles",
        "elas",
        "me",
        "te",
        "se",
        "nos",
        "vos",
        "mim",
        "ti",
        "comigo",
        "contigo",
        "consigo",
        "meu",
        "minha",
        "meus",
        "minhas",
        "teu",
        "tua",
        "teus",
        "tuas",
        "seu",
        "sua",
        "seus",
        "suas",
        "nosso",
        "nossa",
        "nossos",
        "nossas",
        "vosso",
        "vossa",
        "vossos",
        "vossas",
    }
)

PORTUGUESE_GRAMMATICAL_WORDS: Final[frozenset[str]] = frozenset(
    {
        "o",
        "a",
        "os",
        "as",
        "um",
        "uma",
        "uns",
        "umas",
        "não",
        "já",
        "ainda",
        "só",
        "também",
        "sim",
        "ser",
        "sou",
        "é",
        "somos",
        "são",
        "era",
        "foram",
        "estar",
        "estou",
        "está",
        "estamos",
        "estão",
        "ter",
        "tenho",
        "tem",
        "temos",
        "têm",
        "haver",
        "há",
        "vai",
        "vamos",
        "podem",
        "pode",
        "deve",
        "devem",
    }
)

PORTUGUESE_FUNCTION_WORDS: Final[frozenset[str]] = frozenset(
    {
        "de",
        "em",
        "por",
        "para",
        "com",
        "sem",
        "sobre",
        "entre",
        "até",
        "desde",
        "contra",
        "e",
        "ou",
        "mas",
        "porque",
        "que",
        "se",
        "quando",
        "enquanto",
        "embora",
        "pois",
    }
)

PORTUGUESE_NON_PERSONAL_PRONOUNS: Final[frozenset[str]] = frozenset(
    {
        "isto",
        "isso",
        "aquilo",
        "este",
        "esta",
        "estes",
        "estas",
        "esse",
        "essa",
        "esses",
        "essas",
        "aquele",
        "aquela",
        "aqueles",
        "aquelas",
        "quem",
        "que",
        "qual",
        "quais",
        "quanto",
        "quanta",
        "quantos",
        "quantas",
        "algo",
        "nada",
        "ninguém",
    }
)

PORTUGUESE_GRAMMATICAL_WORDS_BY_SUBCATEGORY: Final[GrammaticalWordsBySubcategory] = (
    build_subcategory_mapping(
        personal_pronouns=PORTUGUESE_PERSONAL_PRONOUNS,
        grammatical_words=PORTUGUESE_GRAMMATICAL_WORDS,
        function_words=PORTUGUESE_FUNCTION_WORDS,
        non_personal_pronouns=PORTUGUESE_NON_PERSONAL_PRONOUNS,
        articles=frozenset({"o", "a", "os", "as", "um", "uma", "uns", "umas"}),
        auxiliaries=frozenset(
            {
                "ser",
                "sou",
                "é",
                "somos",
                "são",
                "era",
                "foram",
                "estar",
                "estou",
                "está",
                "estamos",
                "estão",
                "ter",
                "tenho",
                "tem",
                "temos",
                "têm",
                "haver",
                "há",
                "vai",
                "vamos",
                "podem",
                "pode",
                "deve",
                "devem",
            }
        ),
        particles=frozenset({"não", "já", "ainda", "só", "também", "sim"}),
        prepositions=frozenset(
            {"de", "em", "por", "para", "com", "sem", "sobre", "entre", "até", "desde", "contra"}
        ),
        conjunctions=frozenset(
            {"e", "ou", "mas", "porque", "que", "se", "quando", "enquanto", "embora", "pois"}
        ),
        determiners=frozenset({"algo", "nada", "ninguém"}),
        interrogatives=frozenset(
            {"quem", "que", "qual", "quais", "quanto", "quanta", "quantos", "quantas"}
        ),
        demonstratives=frozenset(
            {
                "isto",
                "isso",
                "aquilo",
                "este",
                "esta",
                "estes",
                "estas",
                "esse",
                "essa",
                "esses",
                "essas",
                "aquele",
                "aquela",
                "aqueles",
                "aquelas",
            }
        ),
    )
)

PORTUGUESE_GRAMMATICAL_ONLY: Final[frozenset[str]] = union_subcategories(
    PORTUGUESE_GRAMMATICAL_WORDS_BY_SUBCATEGORY, GRAMMATICAL_ONLY_SUBCATEGORIES
)

PORTUGUESE_ALSO_LEMMA: Final[frozenset[str]] = union_subcategories(
    PORTUGUESE_GRAMMATICAL_WORDS_BY_SUBCATEGORY, ALSO_LEMMA_SUBCATEGORIES
)

PORTUGUESE_ALL_TIERS: Final[frozenset[str]] = frozenset(
    PORTUGUESE_GRAMMATICAL_ONLY | PORTUGUESE_ALSO_LEMMA
)
