"""Reviewed geography senses; country associations are semantic, not derivational.

The catalog is the whole membership of levels 231-233 and 1031-1033: a word
joins them by being listed here, never by level placement.  Two tiers, each
split the same way by sense:

* main -- the 231 countries, and their people and origin adjectives at 232 and
  languages at 233;
* extended -- every other country and territory at 1031, their people and the
  ethnic groups that are not nationalities at 1032, and the remaining major
  languages at 1033.

Language names remain separate from people and origin adjectives even when the
English surface form is shared ("Greek" is three lemmas).  Associations support
language-specific promotion: a sense follows the earliest level any of its
countries reaches for a target language.

scripts/wordlists/import_geography_catalog.py adds the listed senses.
"""

from dataclasses import dataclass
from typing import Optional

from storage.models.schema import Lemma

MAIN = "main"
EXTENDED = "extended"

TIER_LEVELS: dict[str, dict[str, int]] = {
    MAIN: {"region": 231, "nationality": 232, "origin": 232, "language_name": 233},
    EXTENDED: {"region": 1031, "nationality": 1032, "origin": 1032, "language_name": 1033},
}


@dataclass(frozen=True)
class GeographySense:
    lemma_text: str
    pos_type: str
    pos_subtype: str
    definition: str
    countries: tuple[str, ...]
    tier: str = MAIN
    aliases: tuple[str, ...] = ()
    #: Required of a stored lemma to count as this sense, for a headword whose
    #: other sense shares the subtype: Georgia the country, not the US state.
    disambiguation: Optional[str] = None

    def __post_init__(self) -> None:
        if self.pos_subtype not in TIER_LEVELS.get(self.tier, {}):
            raise ValueError(f"No {self.tier!r} level for {self.pos_subtype!r}")

    @property
    def base_level(self) -> int:
        return TIER_LEVELS[self.tier][self.pos_subtype]


# country, origin adjective, person noun.  None where English has no settled
# word of its own ("New Zealand" is its own adjective) or where another row
# already supplies it.
_MAIN_COUNTRIES: tuple[tuple[str, Optional[str], Optional[str]], ...] = (
    ("Lithuania", "Lithuanian", "Lithuanian"),
    ("Latvia", "Latvian", "Latvian"),
    ("Estonia", "Estonian", "Estonian"),
    ("Poland", "Polish", "Pole"),
    ("Germany", "German", "German"),
    ("France", "French", "French person"),
    ("Spain", "Spanish", "Spaniard"),
    ("Italy", "Italian", "Italian"),
    ("Russia", "Russian", "Russian"),
    ("United Kingdom", "British", "British person"),
    # England's adjective and person are below: "English" is not "British".
    ("England", None, None),
    ("Scotland", "Scottish", "Scot"),
    ("Wales", "Welsh", "Welsh person"),
    ("Ireland", "Irish", "Irish person"),
    ("United States", "American", "American"),
    ("Canada", "Canadian", "Canadian"),
    ("Mexico", "Mexican", "Mexican"),
    ("Cuba", "Cuban", "Cuban"),
    ("Brazil", "Brazilian", "Brazilian"),
    ("Argentina", "Argentine", "Argentine"),
    ("Chile", "Chilean", "Chilean"),
    ("Peru", "Peruvian", "Peruvian"),
    ("Portugal", "Portuguese", "Portuguese person"),
    ("Netherlands", "Dutch", "Dutch person"),
    ("Belgium", "Belgian", "Belgian"),
    ("Switzerland", "Swiss", "Swiss person"),
    ("Austria", "Austrian", "Austrian"),
    ("Denmark", "Danish", "Dane"),
    ("Sweden", "Swedish", "Swede"),
    ("Norway", "Norwegian", "Norwegian"),
    ("Finland", "Finnish", "Finn"),
    ("Hungary", "Hungarian", "Hungarian"),
    ("Ukraine", "Ukrainian", "Ukrainian"),
    ("Greece", "Greek", "Greek"),
    ("Turkey", "Turkish", "Turk"),
    ("Israel", "Israeli", "Israeli"),
    ("Iran", "Iranian", "Iranian"),
    ("Iraq", "Iraqi", "Iraqi"),
    ("Saudi Arabia", "Saudi Arabian", "Saudi Arabian"),
    ("Egypt", "Egyptian", "Egyptian"),
    ("Morocco", "Moroccan", "Moroccan"),
    ("Ethiopia", "Ethiopian", "Ethiopian"),
    ("Kenya", "Kenyan", "Kenyan"),
    ("Tanzania", "Tanzanian", "Tanzanian"),
    ("Nigeria", "Nigerian", "Nigerian"),
    ("South Africa", "South African", "South African"),
    ("India", "Indian", "Indian"),
    ("China", "Chinese", "Chinese person"),
    ("Taiwan", "Taiwanese", "Taiwanese person"),
    ("Japan", "Japanese", "Japanese person"),
    ("South Korea", "South Korean", "South Korean"),
    ("Vietnam", "Vietnamese", "Vietnamese person"),
    ("Thailand", "Thai", "Thai"),
    ("Indonesia", "Indonesian", "Indonesian"),
    ("Philippines", "Filipino", "Filipino"),
    ("Australia", "Australian", "Australian"),
)

# The other UN members and observer states, plus Kosovo, by continent.
_EXTENDED_COUNTRIES: tuple[tuple[str, Optional[str], Optional[str]], ...] = (
    # Europe
    ("Albania", "Albanian", "Albanian"),
    ("Andorra", "Andorran", "Andorran"),
    ("Belarus", "Belarusian", "Belarusian"),
    ("Bosnia and Herzegovina", "Bosnian", "Bosnian"),
    ("Bulgaria", "Bulgarian", "Bulgarian"),
    ("Croatia", "Croatian", "Croat"),
    ("Cyprus", "Cypriot", "Cypriot"),
    ("Czech Republic", "Czech", "Czech"),
    ("Iceland", "Icelandic", "Icelander"),
    ("Kosovo", "Kosovar", "Kosovar"),
    ("Liechtenstein", None, "Liechtensteiner"),
    ("Luxembourg", "Luxembourgish", "Luxembourger"),
    ("Malta", "Maltese", "Maltese person"),
    ("Moldova", "Moldovan", "Moldovan"),
    ("Monaco", "Monegasque", "Monegasque"),
    ("Montenegro", "Montenegrin", "Montenegrin"),
    ("North Macedonia", "Macedonian", "Macedonian"),
    ("Romania", "Romanian", "Romanian"),
    ("San Marino", "Sammarinese", "Sammarinese"),
    ("Serbia", "Serbian", "Serb"),
    ("Slovakia", "Slovak", "Slovak"),
    ("Slovenia", "Slovenian", "Slovenian"),
    ("Vatican City", None, None),
    # Caucasus and Central Asia
    ("Armenia", "Armenian", "Armenian"),
    ("Azerbaijan", "Azerbaijani", "Azerbaijani"),
    ("Georgia", "Georgian", "Georgian"),
    ("Kazakhstan", "Kazakh", "Kazakh"),
    ("Kyrgyzstan", "Kyrgyz", "Kyrgyz"),
    ("Tajikistan", "Tajik", "Tajik"),
    ("Turkmenistan", "Turkmen", "Turkmen"),
    ("Uzbekistan", "Uzbek", "Uzbek"),
    # Middle East
    ("Bahrain", "Bahraini", "Bahraini"),
    ("Jordan", "Jordanian", "Jordanian"),
    ("Kuwait", "Kuwaiti", "Kuwaiti"),
    ("Lebanon", "Lebanese", "Lebanese person"),
    ("Oman", "Omani", "Omani"),
    ("Palestine", "Palestinian", "Palestinian"),
    ("Qatar", "Qatari", "Qatari"),
    ("Syria", "Syrian", "Syrian"),
    ("United Arab Emirates", "Emirati", "Emirati"),
    ("Yemen", "Yemeni", "Yemeni"),
    # South Asia
    ("Afghanistan", "Afghan", "Afghan"),
    ("Bangladesh", "Bangladeshi", "Bangladeshi"),
    ("Bhutan", "Bhutanese", "Bhutanese person"),
    ("Maldives", "Maldivian", "Maldivian"),
    ("Nepal", "Nepali", "Nepali"),
    ("Pakistan", "Pakistani", "Pakistani"),
    ("Sri Lanka", "Sri Lankan", "Sri Lankan"),
    # East and Southeast Asia
    ("Mongolia", "Mongolian", "Mongolian"),
    ("North Korea", "North Korean", "North Korean"),
    ("Brunei", "Bruneian", "Bruneian"),
    ("Cambodia", "Cambodian", "Cambodian"),
    ("East Timor", "Timorese", "Timorese person"),
    ("Laos", "Laotian", "Laotian"),
    ("Malaysia", "Malaysian", "Malaysian"),
    ("Myanmar", "Burmese", "Burmese person"),
    ("Singapore", "Singaporean", "Singaporean"),
    # North Africa
    ("Algeria", "Algerian", "Algerian"),
    ("Libya", "Libyan", "Libyan"),
    ("Sudan", "Sudanese", "Sudanese person"),
    ("Tunisia", "Tunisian", "Tunisian"),
    # West Africa
    ("Benin", "Beninese", "Beninese person"),
    ("Burkina Faso", "Burkinabe", "Burkinabe"),
    ("Cape Verde", "Cape Verdean", "Cape Verdean"),
    ("Gambia", "Gambian", "Gambian"),
    ("Ghana", "Ghanaian", "Ghanaian"),
    ("Guinea", "Guinean", "Guinean"),
    ("Guinea-Bissau", "Bissau-Guinean", "Bissau-Guinean"),
    ("Ivory Coast", "Ivorian", "Ivorian"),
    ("Liberia", "Liberian", "Liberian"),
    ("Mali", "Malian", "Malian"),
    ("Mauritania", "Mauritanian", "Mauritanian"),
    ("Niger", "Nigerien", "Nigerien"),
    ("Senegal", "Senegalese", "Senegalese person"),
    ("Sierra Leone", "Sierra Leonean", "Sierra Leonean"),
    ("Togo", "Togolese", "Togolese person"),
    # Central Africa
    ("Cameroon", "Cameroonian", "Cameroonian"),
    ("Central African Republic", "Central African", "Central African"),
    ("Chad", "Chadian", "Chadian"),
    ("Democratic Republic of the Congo", "Congolese", "Congolese person"),
    ("Republic of the Congo", "Congolese", "Congolese person"),
    ("Equatorial Guinea", "Equatorial Guinean", "Equatorial Guinean"),
    ("Gabon", "Gabonese", "Gabonese person"),
    ("São Tomé and Príncipe", None, None),
    # East Africa
    ("Burundi", "Burundian", "Burundian"),
    ("Comoros", "Comorian", "Comorian"),
    ("Djibouti", "Djiboutian", "Djiboutian"),
    ("Eritrea", "Eritrean", "Eritrean"),
    ("Madagascar", "Malagasy", "Malagasy"),
    ("Mauritius", "Mauritian", "Mauritian"),
    ("Rwanda", "Rwandan", "Rwandan"),
    ("Seychelles", "Seychellois", "Seychellois"),
    ("Somalia", "Somali", "Somali"),
    ("South Sudan", "South Sudanese", "South Sudanese person"),
    ("Uganda", "Ugandan", "Ugandan"),
    # Southern Africa
    ("Angola", "Angolan", "Angolan"),
    ("Botswana", "Botswanan", "Botswanan"),
    ("Eswatini", "Swazi", "Swazi"),
    ("Lesotho", None, "Mosotho"),
    ("Malawi", "Malawian", "Malawian"),
    ("Mozambique", "Mozambican", "Mozambican"),
    ("Namibia", "Namibian", "Namibian"),
    ("Zambia", "Zambian", "Zambian"),
    ("Zimbabwe", "Zimbabwean", "Zimbabwean"),
    # Central America and the Caribbean
    ("Antigua and Barbuda", "Antiguan", "Antiguan"),
    ("Bahamas", "Bahamian", "Bahamian"),
    ("Barbados", "Barbadian", "Barbadian"),
    ("Belize", "Belizean", "Belizean"),
    ("Costa Rica", "Costa Rican", "Costa Rican"),
    ("Dominica", None, None),
    ("Dominican Republic", "Dominican", "Dominican"),
    ("El Salvador", "Salvadoran", "Salvadoran"),
    ("Grenada", "Grenadian", "Grenadian"),
    ("Guatemala", "Guatemalan", "Guatemalan"),
    ("Haiti", "Haitian", "Haitian"),
    ("Honduras", "Honduran", "Honduran"),
    ("Jamaica", "Jamaican", "Jamaican"),
    ("Nicaragua", "Nicaraguan", "Nicaraguan"),
    ("Panama", "Panamanian", "Panamanian"),
    ("Saint Kitts and Nevis", None, None),
    ("Saint Lucia", "Saint Lucian", "Saint Lucian"),
    ("Saint Vincent and the Grenadines", "Vincentian", "Vincentian"),
    ("Trinidad and Tobago", "Trinidadian", "Trinidadian"),
    # South America
    ("Bolivia", "Bolivian", "Bolivian"),
    ("Colombia", "Colombian", "Colombian"),
    ("Ecuador", "Ecuadorian", "Ecuadorian"),
    ("Guyana", "Guyanese", "Guyanese person"),
    ("Paraguay", "Paraguayan", "Paraguayan"),
    ("Suriname", "Surinamese", "Surinamese person"),
    ("Uruguay", "Uruguayan", "Uruguayan"),
    ("Venezuela", "Venezuelan", "Venezuelan"),
    # Oceania
    ("New Zealand", None, "New Zealander"),
    ("Fiji", "Fijian", "Fijian"),
    ("Kiribati", None, None),
    ("Marshall Islands", "Marshallese", "Marshallese person"),
    ("Micronesia", "Micronesian", "Micronesian"),
    ("Nauru", "Nauruan", "Nauruan"),
    ("Palau", "Palauan", "Palauan"),
    ("Papua New Guinea", "Papua New Guinean", "Papua New Guinean"),
    ("Samoa", "Samoan", "Samoan"),
    ("Solomon Islands", None, "Solomon Islander"),
    ("Tonga", "Tongan", "Tongan"),
    ("Tuvalu", "Tuvaluan", "Tuvaluan"),
    ("Vanuatu", "Ni-Vanuatu", "Ni-Vanuatu"),
)

# Territories that are not countries but are learned as places of their own.
# (Hong Kong is already a lemma, as a city at 235.)
_TERRITORIES: tuple[tuple[str, Optional[str], Optional[str], str], ...] = (
    ("Puerto Rico", "Puerto Rican", "Puerto Rican", "a Caribbean territory of the United States"),
    ("Greenland", "Greenlandic", "Greenlander", "an Arctic island, an autonomous part of Denmark"),
    ("Northern Ireland", "Northern Irish", None, "the part of the United Kingdom in Ireland"),
)

# Country names whose headword has another sense under the same subtype.
_COUNTRY_DISAMBIGUATION: dict[str, str] = {"Georgia": "country"}

# City-states already learned as a city (235); a second, region lemma for the
# same place would only compete with it.  Their people and adjective still count.
_COUNTRIES_STORED_AS_CITIES: frozenset[str] = frozenset({"Singapore"})

# language, the countries it is associated with.  Chinese and Arabic are the
# general names, taught early; their varieties are extended languages.
_MAIN_LANGUAGES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Lithuanian", ("Lithuania",)),
    ("Latvian", ("Latvia",)),
    ("Estonian", ("Estonia",)),
    ("Polish", ("Poland",)),
    ("German", ("Germany", "Austria", "Switzerland")),
    ("French", ("France", "Belgium", "Switzerland", "Canada")),
    ("Spanish", ("Spain", "Mexico", "Argentina", "Chile", "Peru", "Cuba")),
    ("Italian", ("Italy", "Switzerland")),
    ("Russian", ("Russia",)),
    ("English", ("England", "United Kingdom", "United States", "Canada", "Australia", "Ireland")),
    ("Portuguese", ("Portugal", "Brazil")),
    ("Dutch", ("Netherlands", "Belgium")),
    ("Swedish", ("Sweden",)),
    ("Norwegian", ("Norway",)),
    ("Finnish", ("Finland",)),
    ("Danish", ("Denmark",)),
    ("Hungarian", ("Hungary",)),
    ("Ukrainian", ("Ukraine",)),
    ("Greek", ("Greece", "Cyprus")),
    ("Turkish", ("Turkey", "Cyprus")),
    ("Hebrew", ("Israel",)),
    ("Persian", ("Iran", "Afghanistan", "Tajikistan")),
    ("Arabic", ("Egypt", "Saudi Arabia", "Iraq", "Morocco")),
    ("Amharic", ("Ethiopia",)),
    ("Swahili", ("Tanzania", "Kenya")),
    ("Hindi", ("India",)),
    ("Chinese", ("China", "Taiwan")),
    ("Japanese", ("Japan",)),
    ("Korean", ("South Korea", "North Korea")),
    ("Vietnamese", ("Vietnam",)),
    ("Thai", ("Thailand",)),
    ("Indonesian", ("Indonesia",)),
    ("Filipino", ("Philippines",)),
    ("Irish", ("Ireland",)),
    ("Welsh", ("Wales",)),
)

# Roughly the rest of the hundred most spoken, plus the languages of the
# ethnic groups below and two classical languages English text names often.
_EXTENDED_LANGUAGES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # Varieties of Chinese and Arabic
    ("Mandarin", ("China", "Taiwan", "Singapore")),
    ("Cantonese", ("China",)),
    ("Hokkien", ("China", "Taiwan")),
    ("Hakka", ("China", "Taiwan")),
    ("Wu Chinese", ("China",)),
    ("Egyptian Arabic", ("Egypt",)),
    ("Levantine Arabic", ("Syria", "Lebanon", "Jordan", "Palestine")),
    ("Gulf Arabic", ("Saudi Arabia", "Kuwait", "United Arab Emirates", "Qatar", "Bahrain")),
    ("Moroccan Arabic", ("Morocco",)),
    ("Algerian Arabic", ("Algeria",)),
    ("Sudanese Arabic", ("Sudan",)),
    # South Asia
    ("Bengali", ("Bangladesh", "India")),
    ("Urdu", ("Pakistan", "India")),
    ("Punjabi", ("India", "Pakistan")),
    ("Marathi", ("India",)),
    ("Telugu", ("India",)),
    ("Tamil", ("India", "Sri Lanka")),
    ("Gujarati", ("India",)),
    ("Kannada", ("India",)),
    ("Malayalam", ("India",)),
    ("Odia", ("India",)),
    ("Bhojpuri", ("India", "Nepal")),
    ("Maithili", ("India", "Nepal")),
    ("Assamese", ("India",)),
    ("Sindhi", ("Pakistan", "India")),
    ("Saraiki", ("Pakistan",)),
    ("Nepali", ("Nepal",)),
    ("Sinhala", ("Sri Lanka",)),
    ("Pashto", ("Afghanistan", "Pakistan")),
    # Southeast and East Asia
    ("Malay", ("Malaysia", "Brunei", "Singapore", "Indonesia")),
    ("Javanese", ("Indonesia",)),
    ("Sundanese", ("Indonesia",)),
    ("Burmese", ("Myanmar",)),
    ("Khmer", ("Cambodia",)),
    ("Lao", ("Laos",)),
    ("Cebuano", ("Philippines",)),
    ("Ilocano", ("Philippines",)),
    ("Hmong", ("Laos", "Vietnam", "China")),
    ("Mongolian", ("Mongolia", "China")),
    ("Tibetan", ("China",)),
    ("Uyghur", ("China",)),
    ("Zhuang", ("China",)),
    # Europe
    ("Czech", ("Czech Republic",)),
    ("Slovak", ("Slovakia",)),
    ("Romanian", ("Romania", "Moldova")),
    ("Bulgarian", ("Bulgaria",)),
    ("Serbian", ("Serbia", "Bosnia and Herzegovina", "Montenegro")),
    ("Croatian", ("Croatia", "Bosnia and Herzegovina")),
    ("Bosnian", ("Bosnia and Herzegovina",)),
    ("Slovenian", ("Slovenia",)),
    ("Macedonian", ("North Macedonia",)),
    ("Albanian", ("Albania", "Kosovo")),
    ("Belarusian", ("Belarus",)),
    ("Icelandic", ("Iceland",)),
    ("Luxembourgish", ("Luxembourg",)),
    ("Maltese", ("Malta",)),
    ("Catalan", ("Spain", "Andorra")),
    ("Basque", ("Spain", "France")),
    ("Galician", ("Spain",)),
    ("Scottish Gaelic", ("Scotland",)),
    ("Yiddish", ("Israel", "United States")),
    ("Romani", ("Romania", "Hungary", "Serbia", "Bulgaria")),
    ("Sami", ("Norway", "Sweden", "Finland")),
    ("Latin", ("Vatican City", "Italy")),
    # Caucasus and Central Asia
    ("Armenian", ("Armenia",)),
    ("Georgian", ("Georgia",)),
    ("Azerbaijani", ("Azerbaijan", "Iran")),
    ("Kazakh", ("Kazakhstan",)),
    ("Uzbek", ("Uzbekistan",)),
    ("Turkmen", ("Turkmenistan",)),
    ("Kyrgyz", ("Kyrgyzstan",)),
    ("Tajik", ("Tajikistan",)),
    ("Tatar", ("Russia",)),
    ("Kurdish", ("Iraq", "Turkey", "Iran", "Syria")),
    # Africa
    ("Hausa", ("Nigeria", "Niger")),
    ("Yoruba", ("Nigeria", "Benin")),
    ("Igbo", ("Nigeria",)),
    ("Fula", ("Senegal", "Guinea", "Nigeria", "Cameroon")),
    ("Oromo", ("Ethiopia", "Kenya")),
    ("Somali", ("Somalia", "Ethiopia", "Djibouti")),
    ("Tigrinya", ("Eritrea", "Ethiopia")),
    ("Berber", ("Morocco", "Algeria")),
    ("Wolof", ("Senegal", "Gambia")),
    ("Akan", ("Ghana",)),
    ("Lingala", ("Democratic Republic of the Congo", "Republic of the Congo")),
    ("Kinyarwanda", ("Rwanda",)),
    ("Kirundi", ("Burundi",)),
    ("Luganda", ("Uganda",)),
    ("Shona", ("Zimbabwe",)),
    ("Chichewa", ("Malawi", "Zambia")),
    ("Zulu", ("South Africa",)),
    ("Xhosa", ("South Africa",)),
    ("Afrikaans", ("South Africa", "Namibia")),
    ("Sesotho", ("Lesotho", "South Africa")),
    ("Setswana", ("Botswana", "South Africa")),
    ("Malagasy", ("Madagascar",)),
    # The Americas and the Pacific
    ("Quechua", ("Peru", "Bolivia", "Ecuador")),
    ("Guarani", ("Paraguay",)),
    ("Nahuatl", ("Mexico",)),
    ("Haitian Creole", ("Haiti",)),
    ("Navajo", ("United States",)),
    ("Cherokee", ("United States",)),
    ("Greenlandic", ("Greenland",)),
    ("Hawaiian", ("United States",)),
    ("Maori", ("New Zealand",)),
    ("Samoan", ("Samoa",)),
    ("Tongan", ("Tonga",)),
    ("Tok Pisin", ("Papua New Guinea",)),
    # Classical
    ("Sanskrit", ("India",)),
)

_LANGUAGE_DEFINITIONS: dict[str, str] = {
    "Latin": "The Latin language of ancient Rome, still used in scholarship and the church.",
    "Sanskrit": "Sanskrit, the classical language of ancient India and of Hindu scripture.",
    "Berber": "The Berber (Amazigh) languages of North Africa.",
    "Sami": "The Sami languages of northern Scandinavia and Finland.",
}

_LANGUAGE_ALIASES: dict[str, tuple[str, ...]] = {
    "Persian": ("Farsi",),
    "Filipino": ("Tagalog",),
    "Berber": ("Tamazight", "Amazigh"),
    "Odia": ("Oriya",),
    "Chichewa": ("Chewa",),
}

# Ethnic groups that are not a nationality: person noun, origin adjective,
# associated countries, and the people as a definition names them.  The person
# is "X person" only where English has no noun of its own.
_ETHNIC_GROUPS: tuple[tuple[str, Optional[str], tuple[str, ...], str], ...] = (
    ("Arab", "Arab", ("Egypt", "Saudi Arabia", "Iraq", "Syria", "Morocco"), "the Arab peoples"),
    ("Kurd", "Kurdish", ("Iraq", "Turkey", "Iran", "Syria"), "the Kurdish people"),
    ("Persian", "Persian", ("Iran",), "the Persian people"),
    ("Pashtun", "Pashtun", ("Afghanistan", "Pakistan"), "the Pashtun people"),
    ("Basque", "Basque", ("Spain", "France"), "the Basque people"),
    ("Catalan", "Catalan", ("Spain",), "the Catalan people"),
    ("Fleming", "Flemish", ("Belgium",), "the Flemish people of northern Belgium"),
    ("Sami", "Sami", ("Norway", "Sweden", "Finland"), "the Sami people"),
    ("Romani", "Romani", ("Romania", "Hungary", "Serbia", "Bulgaria"), "the Romani people"),
    ("Tatar", "Tatar", ("Russia",), "the Tatar people"),
    ("Tamil", "Tamil", ("India", "Sri Lanka"), "the Tamil people"),
    ("Punjabi", "Punjabi", ("India", "Pakistan"), "the Punjabi people"),
    ("Bengali", "Bengali", ("Bangladesh", "India"), "the Bengali people"),
    ("Assamese person", "Assamese", ("India",), "the Assamese people of Assam"),
    ("Tibetan", "Tibetan", ("China",), "the Tibetan people"),
    ("Uyghur", "Uyghur", ("China",), "the Uyghur people"),
    ("Hmong", "Hmong", ("Laos", "Vietnam", "China"), "the Hmong people"),
    ("Malay", "Malay", ("Malaysia", "Indonesia", "Brunei", "Singapore"), "the Malay people"),
    ("Rohingya", "Rohingya", ("Myanmar", "Bangladesh"), "the Rohingya people"),
    ("Berber", "Berber", ("Morocco", "Algeria"), "the Berber (Amazigh) peoples"),
    ("Yoruba", "Yoruba", ("Nigeria", "Benin"), "the Yoruba people"),
    ("Igbo person", "Igbo", ("Nigeria",), "the Igbo people"),
    ("Hausa", "Hausa", ("Nigeria", "Niger"), "the Hausa people"),
    ("Fulani", "Fulani", ("Senegal", "Guinea", "Nigeria", "Cameroon"), "the Fulani people"),
    ("Oromo", "Oromo", ("Ethiopia", "Kenya"), "the Oromo people"),
    ("Zulu", "Zulu", ("South Africa",), "the Zulu people"),
    ("Xhosa", "Xhosa", ("South Africa",), "the Xhosa people"),
    ("Afrikaner", "Afrikaner", ("South Africa",), "the Afrikaners"),
    ("Hispanic", "Hispanic", ("United States",), "Spanish-speaking peoples"),
    ("Latino", "Latino", ("United States",), "people of Latin American origin"),
    (
        "Native American",
        "Native American",
        ("United States",),
        "the Indigenous peoples of the Americas",
    ),
    ("Navajo", "Navajo", ("United States",), "the Navajo people"),
    ("Cherokee", "Cherokee", ("United States",), "the Cherokee people"),
    ("Inuk", "Inuit", ("Canada", "Greenland"), "the Inuit"),
    ("Maori", "Maori", ("New Zealand",), "the Maori people"),
    ("Aboriginal Australian", None, ("Australia",), "the Aboriginal peoples of Australia"),
)


class _Builder:
    """Collects senses, merging a word listed for several countries."""

    def __init__(self) -> None:
        self._senses: dict[tuple[str, str], GeographySense] = {}

    def add(self, sense: GeographySense) -> None:
        key = (sense.lemma_text, sense.pos_subtype)
        existing = self._senses.get(key)
        if existing is None:
            self._senses[key] = sense
            return
        if existing.tier != sense.tier:
            raise ValueError(f"{sense.lemma_text!r} ({sense.pos_subtype}) is listed in two tiers")
        countries = existing.countries + tuple(
            country for country in sense.countries if country not in existing.countries
        )
        self._senses[key] = GeographySense(
            existing.lemma_text,
            existing.pos_type,
            existing.pos_subtype,
            existing.definition,
            countries,
            existing.tier,
            existing.aliases,
            existing.disambiguation,
        )

    def add_country(
        self,
        country: str,
        adjective: Optional[str],
        person: Optional[str],
        tier: str,
        description: Optional[str] = None,
    ) -> None:
        definition = f"{country}, {description}." if description else f"The country of {country}."
        if country not in _COUNTRIES_STORED_AS_CITIES:
            self.add(
                GeographySense(
                    country,
                    "noun",
                    "region",
                    definition,
                    (country,),
                    tier,
                    disambiguation=_COUNTRY_DISAMBIGUATION.get(country),
                )
            )
        if person is not None:
            self.add(
                GeographySense(
                    person,
                    "noun",
                    "nationality",
                    f"A person from {country}; a national or inhabitant of {country}.",
                    (country,),
                    tier,
                )
            )
        if adjective is not None:
            self.add(
                GeographySense(
                    adjective,
                    "adjective",
                    "origin",
                    f"Relating to {country}, its people, or its culture.",
                    (country,),
                    tier,
                )
            )

    def add_language(self, language: str, countries: tuple[str, ...], tier: str) -> None:
        self.add(
            GeographySense(
                language,
                "noun",
                "language_name",
                _LANGUAGE_DEFINITIONS.get(language, f"The {language} language."),
                countries,
                tier,
                _LANGUAGE_ALIASES.get(language, ()),
            )
        )

    def add_ethnic_group(
        self, person: str, adjective: Optional[str], countries: tuple[str, ...], people: str
    ) -> None:
        self.add(
            GeographySense(
                person,
                "noun",
                "nationality",
                f"A member of {people}; this is an ethnic group, not a citizenship.",
                countries,
                EXTENDED,
            )
        )
        if adjective is not None:
            self.add(
                GeographySense(
                    adjective,
                    "adjective",
                    "origin",
                    f"Relating to {people}, their culture, or their language.",
                    countries,
                    EXTENDED,
                )
            )

    def senses(self) -> tuple[GeographySense, ...]:
        return tuple(self._senses.values())


def _build_senses() -> tuple[GeographySense, ...]:
    builder = _Builder()
    for country, adjective, person in _MAIN_COUNTRIES:
        builder.add_country(country, adjective, person, MAIN)
    # England is a constituent country; English is not synonymous with British.
    builder.add(
        GeographySense(
            "Englishman",
            "noun",
            "nationality",
            "A person from England or of English descent.",
            ("England", "United Kingdom"),
            aliases=("English person",),
        )
    )
    builder.add(
        GeographySense(
            "English",
            "adjective",
            "origin",
            "Relating to England, its people, or its culture.",
            ("England", "United Kingdom"),
        )
    )
    for language, countries in _MAIN_LANGUAGES:
        builder.add_language(language, countries, MAIN)
    for country, adjective, person in _EXTENDED_COUNTRIES:
        builder.add_country(country, adjective, person, EXTENDED)
    for territory, adjective, person, description in _TERRITORIES:
        builder.add_country(territory, adjective, person, EXTENDED, description)
    for language, countries in _EXTENDED_LANGUAGES:
        builder.add_language(language, countries, EXTENDED)
    for person, adjective, countries, people in _ETHNIC_GROUPS:
        builder.add_ethnic_group(person, adjective, countries, people)
    return builder.senses()


GEOGRAPHY_SENSES = _build_senses()
MAIN_COUNTRY_NAMES = frozenset(
    sense.lemma_text
    for sense in GEOGRAPHY_SENSES
    if sense.pos_subtype == "region" and sense.tier == MAIN
)
#: Every country and territory a sense may be associated with, including the
#: city-states whose place lemma is a city.
CATALOG_COUNTRY_NAMES = frozenset(
    name for name, *_rest in (*_MAIN_COUNTRIES, *_EXTENDED_COUNTRIES, *_TERRITORIES)
)


def find_sense(lemma: Lemma) -> GeographySense | None:
    """Match only a reviewed sense, never a generic origin adjective."""
    for sense in GEOGRAPHY_SENSES:
        if (
            lemma.pos_type == sense.pos_type
            and lemma.pos_subtype == sense.pos_subtype
            and lemma.lemma_text in (sense.lemma_text, *sense.aliases)
            and (
                sense.disambiguation is None
                or (lemma.disambiguation or "").lower() == sense.disambiguation
            )
        ):
            return sense
    return None
