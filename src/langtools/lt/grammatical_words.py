"""Lithuanian grammatical/function-word data.

Four tiers:

1. **personal_pronouns** – aš, tu, jis, ji, … (all case forms),
   reflexive (savęs …), possessive (mano, tavo, savo)
2. **grammatical_words** – auxiliary *būti* forms, particles (ar, ne, jau, …)
3. **function_words** – prepositions (į, iš, su, …), conjunctions (ir, bet, …)
4. **non_personal_pronouns** – demonstratives (šis, tas, …),
   interrogative / relative (kas, kuris, koks, …)

Tiers 1–2 have no analogues in data/release; tiers 3–4 do.
"""

from typing import Final

# ── tier 1: personal pronouns ──────────────────────────────────────────

LITHUANIAN_PERSONAL_PRONOUNS: Final[frozenset[str]] = frozenset(
    {
        # aš – all cases
        "aš",
        "manęs",
        "man",
        "mane",
        "manimi",
        "manyje",
        # tu – all cases
        "tu",
        "tavęs",
        "tau",
        "tave",
        "tavimi",
        "tavyje",
        # jis – all cases
        "jis",
        "jo",
        "jam",
        "jį",
        "juo",
        "jame",
        # ji – all cases
        "ji",
        "jos",
        "jai",
        "ją",
        "ja",
        "joje",
        # mes – all cases
        "mes",
        "mūsų",
        "mums",
        "mus",
        "mumis",
        "mumyse",
        # jūs – all cases
        "jūs",
        "jūsų",
        "jums",
        "jus",
        "jumis",
        "jumyse",
        # jie – all cases
        "jie",
        "jų",
        "jiems",
        "juos",
        "jais",
        "juose",
        # jos (fem. plural) – all cases
        "jos",
        "joms",
        "jas",
        "jomis",
        "jose",
        # Reflexive
        "savęs",
        "sau",
        "save",
        "savimi",
        "savyje",
        # Possessive pronouns
        "mano",
        "tavo",
        "savo",
    }
)

# ── tier 2: grammatical words (auxiliaries, particles) ────────────────

LITHUANIAN_GRAMMATICAL_WORDS: Final[frozenset[str]] = frozenset(
    {
        # Particles
        "ar",
        "ne",
        "jau",
        "dar",
        "tik",
        "net",
        "gi",
        "pat",
        "vis",
        "juk",
        "tad",
        "gal",
        "tai",
        "štai",
        "turbūt",
        "nebent",
        # Auxiliary / semi-auxiliary (būti forms)
        "būti",
        "yra",
        "buvo",
        "bus",
        "būtų",
        "būna",
    }
)

# ── tier 3: function words (prepositions, conjunctions) ───────────────

LITHUANIAN_FUNCTION_WORDS: Final[frozenset[str]] = frozenset(
    {
        # Prepositions
        "į",
        "iš",
        "su",
        "be",
        "per",
        "po",
        "ant",
        "prie",
        "nuo",
        "iki",
        "tarp",
        "dėl",
        "apie",
        "už",
        "virš",
        "šalia",
        "link",
        "prieš",
        "pagal",
        "pro",
        # Conjunctions
        "ir",
        "arba",
        "bet",
        "o",
        "tačiau",
        "nes",
        "kad",
        "jei",
        "jeigu",
        "nors",
        "kol",
        "taigi",
        "nei",
        "jog",
        "kai",
        "negu",
        "todėl",
    }
)

# ── tier 4: non-personal pronouns (demonstratives, interrogatives) ────

LITHUANIAN_NON_PERSONAL_PRONOUNS: Final[frozenset[str]] = frozenset(
    {
        # Demonstrative pronouns
        "šis",
        "ši",
        "šie",
        "šios",
        "tas",
        "ta",
        "tie",
        "tos",
        # Interrogative / relative pronouns
        "kas",
        "ko",
        "kam",
        "ką",
        "kuo",
        "kuris",
        "kuri",
        "kurie",
        "kurios",
        "koks",
        "kokia",
    }
)

# ── aggregate sets ─────────────────────────────────────────────────────

LITHUANIAN_GRAMMATICAL_ONLY: Final[frozenset[str]] = frozenset(
    LITHUANIAN_PERSONAL_PRONOUNS | LITHUANIAN_GRAMMATICAL_WORDS
)

LITHUANIAN_ALSO_LEMMA: Final[frozenset[str]] = frozenset(
    LITHUANIAN_FUNCTION_WORDS | LITHUANIAN_NON_PERSONAL_PRONOUNS
)

LITHUANIAN_ALL_TIERS: Final[frozenset[str]] = frozenset(
    LITHUANIAN_GRAMMATICAL_ONLY | LITHUANIAN_ALSO_LEMMA
)
