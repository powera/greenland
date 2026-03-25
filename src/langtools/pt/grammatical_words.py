"""Portuguese grammatical/function-word data."""

from typing import Final

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

PORTUGUESE_GRAMMATICAL_ONLY: Final[frozenset[str]] = frozenset(
    PORTUGUESE_PERSONAL_PRONOUNS | PORTUGUESE_GRAMMATICAL_WORDS
)

PORTUGUESE_ALSO_LEMMA: Final[frozenset[str]] = frozenset(
    PORTUGUESE_FUNCTION_WORDS | PORTUGUESE_NON_PERSONAL_PRONOUNS
)

PORTUGUESE_ALL_TIERS: Final[frozenset[str]] = frozenset(
    PORTUGUESE_GRAMMATICAL_ONLY | PORTUGUESE_ALSO_LEMMA
)
