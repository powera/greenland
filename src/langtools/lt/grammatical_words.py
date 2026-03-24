"""Lithuanian grammatical/function-word data.

* **grammatical_only** – personal/reflexive/possessive pronouns (all case
  forms), auxiliary *būti* forms, particles.
* **also_lemma** – prepositions, conjunctions, interrogative/relative pronouns,
  and demonstratives that have (or could have) data/release entries.
"""

from typing import Final

# ── tier 1: always grammatical, never a lemma ──────────────────────────

LITHUANIAN_GRAMMATICAL_ONLY: Final[frozenset[str]] = frozenset(
    {
        # Personal pronouns — all cases
        "aš",
        "manęs",
        "man",
        "mane",
        "manimi",
        "manyje",
        "tu",
        "tavęs",
        "tau",
        "tave",
        "tavimi",
        "tavyje",
        "jis",
        "jo",
        "jam",
        "jį",
        "juo",
        "jame",
        "ji",
        "jos",
        "jai",
        "ją",
        "ja",
        "joje",
        "mes",
        "mūsų",
        "mums",
        "mus",
        "mumis",
        "mumyse",
        "jūs",
        "jūsų",
        "jums",
        "jus",
        "jumis",
        "jumyse",
        "jie",
        "jų",
        "jiems",
        "juos",
        "jais",
        "juose",
        "jos",
        "joms",
        "jas",
        "jomis",
        "jose",
        # Reflexive pronoun
        "savęs",
        "sau",
        "save",
        "savimi",
        "savyje",
        # Possessive pronouns
        "mano",
        "tavo",
        "savo",
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

# ── tier 2: function words that are (or could be) lemmas ───────────────

LITHUANIAN_ALSO_LEMMA: Final[frozenset[str]] = frozenset(
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

# ── combined set ───────────────────────────────────────────────────────

LITHUANIAN_GRAMMATICAL_WORDS: Final[frozenset[str]] = frozenset(
    LITHUANIAN_GRAMMATICAL_ONLY | LITHUANIAN_ALSO_LEMMA
)
