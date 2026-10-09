"""Reviewed geography senses; country associations are semantic, not derivational.

This is a starter inventory, not a claim to rank the world's top 150 countries.
Language names remain separate from people and origin adjectives even when the
English surface form is shared. Associations support language-specific promotion.
"""

from dataclasses import dataclass
from storage.models.schema import Lemma


@dataclass(frozen=True)
class GeographySense:
    lemma_text: str
    pos_type: str
    pos_subtype: str
    definition: str
    countries: tuple[str, ...]
    base_level: int = 231
    aliases: tuple[str, ...] = ()


# country, origin adjective, person noun, language (None for extra countries).
_COUNTRY_WORDS: tuple[tuple[str, str, str, str | None], ...] = (
    ("Lithuania", "Lithuanian", "Lithuanian", "Lithuanian"),
    ("Latvia", "Latvian", "Latvian", "Latvian"),
    ("Estonia", "Estonian", "Estonian", "Estonian"),
    ("Poland", "Polish", "Pole", "Polish"),
    ("Germany", "German", "German", "German"),
    ("France", "French", "French person", "French"),
    ("Spain", "Spanish", "Spaniard", "Spanish"),
    ("Italy", "Italian", "Italian", "Italian"),
    ("Russia", "Russian", "Russian", "Russian"),
    ("United Kingdom", "British", "British person", "English"),
    ("United States", "American", "American", None),
    ("Canada", "Canadian", "Canadian", None),
    ("Portugal", "Portuguese", "Portuguese person", "Portuguese"),
    ("Brazil", "Brazilian", "Brazilian", None),
    ("Netherlands", "Dutch", "Dutch person", "Dutch"),
    ("Sweden", "Swedish", "Swede", "Swedish"),
    ("Norway", "Norwegian", "Norwegian", "Norwegian"),
    ("Finland", "Finnish", "Finn", "Finnish"),
    ("China", "Chinese", "Chinese person", "Chinese"),
    ("Taiwan", "Taiwanese", "Taiwanese person", None),
    ("Japan", "Japanese", "Japanese person", "Japanese"),
    ("South Korea", "South Korean", "South Korean", "Korean"),
    ("Vietnam", "Vietnamese", "Vietnamese person", "Vietnamese"),
    ("Tanzania", "Tanzanian", "Tanzanian", "Swahili"),
    ("Kenya", "Kenyan", "Kenyan", None),
    ("Nigeria", "Nigerian", "Nigerian", None),
    ("India", "Indian", "Indian", "Hindi"),
    ("Egypt", "Egyptian", "Egyptian", "Arabic"),
    ("Saudi Arabia", "Saudi Arabian", "Saudi Arabian", None),
    ("Mongolia", "Mongolian", "Mongolian", None),
)


def _build_senses() -> tuple[GeographySense, ...]:
    senses: list[GeographySense] = []
    for country, adjective, person, language in _COUNTRY_WORDS:
        level = 1031 if country == "Mongolia" else 231
        senses.extend(
            (
                GeographySense(
                    country,
                    "noun",
                    "region",
                    f"The country or political territory of {country}.",
                    (country,),
                    level,
                ),
                GeographySense(
                    person,
                    "noun",
                    "nationality",
                    f"A person from {country}; a national or inhabitant of {country}.",
                    (country,),
                    level,
                ),
                GeographySense(
                    adjective,
                    "adjective",
                    "origin",
                    f"Relating to {country}, its people, or its culture.",
                    (country,),
                    level,
                ),
            )
        )
        if language is not None:
            associated = {
                "English": ("England", "United Kingdom", "United States", "Canada"),
                "French": ("France", "Canada"),
                "Portuguese": ("Portugal", "Brazil"),
                "Chinese": ("China", "Taiwan"),
                "Swahili": ("Tanzania", "Kenya"),
                "Arabic": ("Egypt", "Saudi Arabia"),
            }.get(language, (country,))
            senses.append(
                GeographySense(
                    language,
                    "noun",
                    "communication_information",
                    f"The {language} language.",
                    associated,
                )
            )
    # England is a constituent country; English is not synonymous with British.
    senses.extend(
        (
            GeographySense(
                "Englishman",
                "noun",
                "nationality",
                "A person from England or of English descent.",
                ("England", "United Kingdom"),
                aliases=("English person",),
            ),
            GeographySense(
                "English",
                "adjective",
                "origin",
                "Relating to England, its people, or its culture.",
                ("England", "United Kingdom"),
            ),
            GeographySense(
                "Igbo",
                "noun",
                "communication_information",
                "The Igbo language spoken mainly in southeastern Nigeria.",
                ("Nigeria",),
                1031,
            ),
            GeographySense(
                "Assamese",
                "noun",
                "communication_information",
                "The Assamese language spoken mainly in Assam, India.",
                ("India",),
                1031,
            ),
            GeographySense(
                "Mongolian",
                "noun",
                "communication_information",
                "The Mongolian language.",
                ("Mongolia", "China"),
                1031,
            ),
            GeographySense(
                "Igbo person",
                "noun",
                "nationality",
                "A member of the Igbo ethnic group; this is an ethnicity, not Nigerian citizenship.",
                ("Nigeria",),
                1031,
            ),
            GeographySense(
                "Assamese person",
                "noun",
                "nationality",
                "A member of the Assamese people of Assam; this is a regional and cultural identity, not Indian citizenship.",
                ("India",),
                1031,
            ),
            GeographySense(
                "Igbo",
                "adjective",
                "origin",
                "Relating to the Igbo people, culture, or language.",
                ("Nigeria",),
                1031,
            ),
            GeographySense(
                "Assamese",
                "adjective",
                "origin",
                "Relating to Assam, the Assamese people, or their language.",
                ("India",),
                1031,
            ),
        )
    )
    return tuple(senses)


GEOGRAPHY_SENSES = _build_senses()
MAIN_COUNTRY_NAMES = frozenset(
    sense.lemma_text
    for sense in GEOGRAPHY_SENSES
    if sense.pos_subtype == "region" and sense.base_level == 231
)


def find_sense(lemma: Lemma) -> GeographySense | None:
    """Match only a reviewed sense, never a generic origin adjective."""
    for sense in GEOGRAPHY_SENSES:
        if (
            lemma.pos_type == sense.pos_type
            and lemma.pos_subtype == sense.pos_subtype
            and lemma.lemma_text in (sense.lemma_text, *sense.aliases)
        ):
            return sense
    return None
