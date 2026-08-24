#!/usr/bin/python3

"""Constants and configuration for linguistic analysis."""

import constants

# Common model information
DEFAULT_MODEL = constants.DEFAULT_MODEL
RETRY_COUNT = 3
RETRY_DELAY = 2  # seconds

# Valid parts of speech
VALID_POS_TYPES = {
    "noun",
    "verb",
    "adjective",
    "adverb",
    "pronoun",
    "preposition",
    "conjunction",
    "interjection",
    "determiner",
    "article",
    "numeral",
    "auxiliary",
    "modal",
}

# Define major parts of speech as a set for efficient lookup
MAJOR_POS_TYPES = {"noun", "verb", "adjective", "adverb"}

# Default languages and their configurations.
# This carries prompt-specific data (description, instructions) needed by the
# translation LLM path; the storage-side source of truth is LANGUAGE_FIELDS in
# storage/translation_helpers.py. When adding/removing a language here, make the
# matching change in LANGUAGE_FIELDS (and LLM_FIELD_TO_LANG_CODE) there, or the
# active query_translations path will skip it as "unknown".
DEFAULT_TRANSLATION_LANGUAGES = {
    "lithuanian": {
        "field": "lithuanian_translation",
        "code": "lt",
        "description": "Lithuanian translation in lemma form",
        "instructions": "- Lithuanian: Provide standard Lithuanian in base form (infinitive for verbs, singular nominative for nouns)",
    },
    "chinese": {
        "field": "chinese_translation",
        "code": "zh",
        "description": "Mainland Chinese (普通话) translation in lemma form (Simplified characters)",
        "instructions": "- Chinese: Provide Simplified Chinese characters (简体字) for Mainland Chinese (普通话) in base form\n  - Use natural spoken Mainland Mandarin forms (e.g., 鞋子 not bare 鞋, but 水 not 水份)\n  - Match the generality level of the English word (avoid overly specific translations)\n  - Do not include pinyin, just the characters",
    },
    "korean": {
        "field": "korean_translation",
        "code": "ko",
        "description": "Korean translation in lemma form (Hangul)",
        "instructions": "- Korean: Provide Hangul in base form",
    },
    "french": {
        "field": "french_translation",
        "code": "fr",
        "description": "French translation in lemma form",
        "instructions": "- French: Provide Metropolitan French (France) in base form (infinitive for verbs, singular for nouns)",
    },
    "spanish": {
        "field": "spanish_translation",
        "code": "es",
        "description": "Spanish translation in lemma form",
        "instructions": "- Spanish: Provide Peninsular Spanish (Spain) in base form (infinitive for verbs, singular for nouns)",
    },
    "spanish (latin america)": {
        "field": "spanish_latam_translation",
        "code": "es-419",
        "description": "Latin American Spanish translation in lemma form",
        "instructions": "- Spanish (Latin America): Provide neutral Latin American Spanish (español latinoamericano) in base form (infinitive for verbs, singular for nouns)\n  - Use the pan-regional standard taught in textbooks and used for dubbing, not the Spanish of any single country\n  - Prefer vocabulary understood across Latin America over Peninsular-only terms (computadora not ordenador, carro/auto not coche, jugo not zumo, papa not patata)\n  - Where the Latin American and Peninsular words are the same, give that word; do not invent a difference\n  - Avoid country-specific slang",
    },
    "german": {
        "field": "german_translation",
        "code": "de",
        "description": "German translation in lemma form",
        "instructions": "- German: Provide Standard German (Germany) in base form (infinitive for verbs, singular nominative for nouns without an article)",
    },
    "japanese": {
        "field": "japanese_translation",
        "code": "ja",
        "description": "Japanese translation in lemma form",
        "instructions": "- Japanese: Provide standard Japanese in base form (dictionary form, singular for nouns)",
    },
    "latin": {
        "field": "latin_translation",
        "code": "la",
        "description": "Latin translation in lemma form",
        "instructions": "- Latin: Provide Classical Latin in base form (present active infinitive for verbs, nominative singular for nouns)\n  - Use Classical (not Ecclesiastical or Medieval) orthography and vocabulary\n  - For modern concepts with no Classical word, use the established Neo-Latin term and mark it as late_construction, modern_loan, descriptive, modern_reimagining, or uncertain",
    },
    "sanskrit": {
        "field": "sanskrit_translation",
        "code": "sa",
        "description": "Sanskrit translation in lemma form (Devanagari script)",
        "instructions": "- Sanskrit: Provide Sanskrit in Devanagari script in base form (root/stem form for verbs, nominative singular for nouns)\n  - Do not include IAST transliteration, just the Devanagari characters\n  - For modern concepts, use the established Sanskrit coinage where one exists, and mark it as late_construction, modern_loan, descriptive, modern_reimagining, or uncertain\n  - A word attested only in mythological or epic contexts is not conventional vocabulary for a modern concept; mark such a reuse modern_reimagining (e.g. विमानम् as 'airplane')",
    },
    "ancient greek": {
        "field": "ancient_greek_translation",
        "code": "grc",
        "description": "Ancient Greek translation in lemma form (Greek script)",
        "instructions": "- Ancient Greek: Provide Ancient Greek in Greek script, targeting classical/pre-modern usage rather than Modern Greek\n  - Prefer Classical Attic/Ionic vocabulary and dictionary headwords where available; common Koine is acceptable when it is the historically established form\n  - Use dictionary lemma forms (first-person singular present active indicative for verbs when that is the standard headword, nominative singular for nouns)\n  - Do not include transliteration, just the Greek script\n  - For later or modern concepts, use an established learned construction only when useful and mark it as late_construction, modern_loan, descriptive, modern_reimagining, or uncertain",
    },
    "classical arabic": {
        "field": "classical_arabic_translation",
        "code": "ar-classical",
        "description": "Classical Arabic (pre-1200) translation in lemma form (Arabic script)",
        "instructions": "- Classical Arabic: Provide Classical Arabic in Arabic script, targeting pre-1200 usage, not Modern Standard Arabic or a modern national variety\n  - Use historically attested Classical/Qur'anic/early literary vocabulary where available\n  - Use dictionary lemma forms (third-person masculine singular perfect for verbs where appropriate, singular for nouns)\n  - Do not include transliteration, just the Arabic script\n  - For post-1200 or modern concepts, do not silently use Modern Standard Arabic; use an established learned construction only when useful and mark it as late_construction, modern_loan, descriptive, modern_reimagining, or uncertain",
    },
    "old norse": {
        "field": "old_norse_translation",
        "code": "non",
        "description": "Old Norse translation in normalized lemma form",
        "instructions": "- Old Norse: Provide normalized Old Norse / Old Icelandic dictionary forms, not Modern Icelandic, Norwegian, Danish, or Swedish\n  - Use conventional normalized spelling with diacritics where appropriate\n  - Use lemma forms (infinitive for verbs, nominative singular for nouns)\n  - For later or modern concepts, use an established scholarly construction only when useful and mark it as late_construction, modern_loan, descriptive, modern_reimagining, or uncertain",
    },
    "italian": {
        "field": "italian_translation",
        "code": "it",
        "description": "Italian translation in lemma form",
        "instructions": "- Italian: Provide standard Italian in base form (infinitive for verbs, singular for nouns)",
    },
    "dutch": {
        "field": "dutch_translation",
        "code": "nl",
        "description": "Dutch translation in lemma form",
        "instructions": "- Dutch: Provide standard Dutch in base form (infinitive for verbs, singular for nouns)",
    },
    "portuguese": {
        "field": "portuguese_translation",
        "code": "pt",
        "description": "Portuguese translation in lemma form",
        "instructions": "- Portuguese: Provide European Portuguese (Portugal) in base form (infinitive for verbs, singular for nouns)",
    },
    "portuguese (brazil)": {
        "field": "portuguese_brazil_translation",
        "code": "pt-br",
        "description": "Brazilian Portuguese translation in lemma form",
        "instructions": "- Portuguese (Brazil): Provide Brazilian Portuguese in base form (infinitive for verbs, singular for nouns)\n  - Use Brazilian vocabulary and spelling where it differs from European Portuguese (ônibus not autocarro, trem not comboio, celular not telemóvel, café da manhã not pequeno-almoço)\n  - Where the Brazilian and European words are the same, give that word; do not invent a difference",
    },
    "swahili": {
        "field": "swahili_translation",
        "code": "sw",
        "description": "Swahili translation in lemma form",
        "instructions": "- Swahili: Provide standard Swahili in base form",
    },
    "swedish": {
        "field": "swedish_translation",
        "code": "sv",
        "description": "Swedish translation in lemma form",
        "instructions": "- Swedish: Provide standard Swedish in base form (infinitive for verbs, singular for nouns)",
    },
    "vietnamese": {
        "field": "vietnamese_translation",
        "code": "vi",
        "description": "Vietnamese translation in lemma form",
        "instructions": "- Vietnamese: Provide standard Vietnamese in base form",
    },
    "romanian": {
        "field": "romanian_translation",
        "code": "ro",
        "description": "Romanian translation in lemma form",
        "instructions": "- Romanian: Provide standard Romanian in base form (infinitive for verbs, singular indefinite for nouns)",
    },
    "polish": {
        "field": "polish_translation",
        "code": "pl",
        "description": "Polish translation in lemma form",
        "instructions": "- Polish: Provide standard Polish in base form (infinitive for verbs, singular nominative for nouns)",
    },
    "tamil": {
        "field": "tamil_translation",
        "code": "ta",
        "description": "Tamil translation in lemma form",
        "instructions": "- Tamil: Provide standard Tamil in base form (infinitive for verbs, singular for nouns)",
    },
    "telugu": {
        "field": "telugu_translation",
        "code": "te",
        "description": "Telugu translation in lemma form",
        "instructions": "- Telugu: Provide standard Telugu in base form (infinitive for verbs, singular for nouns)",
    },
    "kannada": {
        "field": "kannada_translation",
        "code": "kn",
        "description": "Kannada translation in lemma form",
        "instructions": "- Kannada: Provide standard Kannada in base form (infinitive for verbs, singular for nouns)",
    },
    "malayalam": {
        "field": "malayalam_translation",
        "code": "ml",
        "description": "Malayalam translation in lemma form",
        "instructions": "- Malayalam: Provide standard Malayalam in base form (infinitive for verbs, singular for nouns)",
    },
    "sinhala": {
        "field": "sinhala_translation",
        "code": "si",
        "description": "Sinhala translation in lemma form",
        "instructions": "- Sinhala: Provide standard Sinhala in base form (infinitive for verbs, singular for nouns)",
    },
    "chinese (taiwan)": {
        "field": "chinese_taiwan_translation",
        "code": "zh-tw",
        "description": "Taiwan Chinese (國語) translation in lemma form (Traditional characters)",
        "instructions": "- Chinese (Taiwan): Provide Traditional Chinese characters (繁體字) for Taiwan Chinese (國語) in base form\n  - Use natural spoken Taiwan Mandarin forms\n  - Match the generality level of the English word (avoid overly specific translations)\n  - Do not include pinyin or zhuyin, just the characters",
    },
    "thai": {
        "field": "thai_translation",
        "code": "th",
        "description": "Thai translation in lemma form",
        "instructions": "- Thai: Provide standard Thai in base form",
    },
    "malay": {
        "field": "malay_translation",
        "code": "ms",
        "description": "Malay translation in lemma form",
        "instructions": "- Malay: Provide standard Malay (Bahasa Melayu) in base form",
    },
    "burmese": {
        "field": "burmese_translation",
        "code": "my",
        "description": "Burmese translation in lemma form",
        "instructions": "- Burmese: Provide standard Burmese in base form",
    },
    "khmer": {
        "field": "khmer_translation",
        "code": "km",
        "description": "Khmer translation in lemma form",
        "instructions": "- Khmer: Provide standard Khmer in base form",
    },
    "lao": {
        "field": "lao_translation",
        "code": "lo",
        "description": "Lao translation in lemma form",
        "instructions": "- Lao: Provide standard Lao in base form",
    },
    "filipino": {
        "field": "filipino_translation",
        "code": "tl",
        "description": "Filipino translation in lemma form",
        "instructions": "- Filipino: Provide standard Filipino in base form (infinitive for verbs, singular for nouns)",
    },
    "hausa": {
        "field": "hausa_translation",
        "code": "ha",
        "description": "Hausa translation in lemma form",
        "instructions": "- Hausa: Provide standard Hausa in base form",
    },
    "yoruba": {
        "field": "yoruba_translation",
        "code": "yo",
        "description": "Yoruba translation in lemma form",
        "instructions": "- Yoruba: Provide standard Yoruba with tone marks in base form",
    },
    "igbo": {
        "field": "igbo_translation",
        "code": "ig",
        "description": "Igbo translation in lemma form",
        "instructions": "- Igbo: Provide standard Igbo in base form",
    },
    "amharic": {
        "field": "amharic_translation",
        "code": "am",
        "description": "Amharic translation in lemma form (Ge'ez script)",
        "instructions": "- Amharic: Provide standard Amharic in Ge'ez script in base form",
    },
    "zulu": {
        "field": "zulu_translation",
        "code": "zu",
        "description": "Zulu translation in lemma form",
        "instructions": "- Zulu: Provide standard Zulu in base form",
    },
    "oromo": {
        "field": "oromo_translation",
        "code": "om",
        "description": "Oromo translation in lemma form",
        "instructions": "- Oromo: Provide standard Oromo in base form",
    },
    "somali": {
        "field": "somali_translation",
        "code": "so",
        "description": "Somali translation in lemma form",
        "instructions": "- Somali: Provide standard Somali in base form",
    },
    "xhosa": {
        "field": "xhosa_translation",
        "code": "xh",
        "description": "Xhosa translation in lemma form",
        "instructions": "- Xhosa: Provide standard Xhosa in base form",
    },
    "shona": {
        "field": "shona_translation",
        "code": "sn",
        "description": "Shona translation in lemma form",
        "instructions": "- Shona: Provide standard Shona in base form",
    },
    "hindi": {
        "field": "hindi_translation",
        "code": "hi",
        "description": "Hindi translation in lemma form (Devanagari script)",
        "instructions": "- Hindi: Provide standard Hindi in Devanagari script in base form (infinitive for verbs, singular for nouns)\n  - Use Modern Standard Hindi as spoken in India\n  - Do not include transliteration, just the Devanagari characters",
    },
    "punjabi": {
        "field": "punjabi_translation",
        "code": "pa",
        "description": "Punjabi translation in lemma form (Gurmukhi script)",
        "instructions": "- Punjabi: Provide standard Punjabi in Gurmukhi script in base form (infinitive for verbs, singular for nouns)\n  - Use Eastern (Indian) Punjabi as spoken in Indian Punjab\n  - Use the Gurmukhi script, not Shahmukhi/Perso-Arabic\n  - Do not include transliteration, just the Gurmukhi characters",
    },
    "bengali": {
        "field": "bengali_translation",
        "code": "bn",
        "description": "Bengali translation in lemma form (Bengali script)",
        "instructions": "- Bengali: Provide standard Bengali in Bengali script in base form (infinitive for verbs, singular for nouns)\n  - Use standard Bangladeshi/West Bengali literary form\n  - Do not include transliteration, just the Bengali characters",
    },
    "pashto": {
        "field": "pashto_translation",
        "code": "ps",
        "description": "Pashto translation in lemma form (Arabic script)",
        "instructions": "- Pashto: Provide standard Pashto in Arabic script in base form (masdar for verbs, singular for nouns)\n  - Use the standard Afghan Pashto dialect\n  - Do not include transliteration, just the Pashto script",
    },
    "persian": {
        "field": "persian_translation",
        "code": "fa",
        "description": "Persian (Farsi) translation in lemma form (Perso-Arabic script)",
        "instructions": "- Persian: Provide standard Iranian Persian (Farsi) in Perso-Arabic script in base form (masdar for verbs, singular for nouns)\n  - Use Iranian Persian vocabulary and forms\n  - Do not include transliteration, just the Perso-Arabic characters",
    },
    "georgian": {
        "field": "georgian_translation",
        "code": "ka",
        "description": "Georgian translation in lemma form (Mkhedruli script)",
        "instructions": "- Georgian: Provide standard Georgian in Mkhedruli script in base form (masdar/infinitive for verbs, nominative singular for nouns)\n  - Do not include transliteration, just the Georgian characters",
    },
    "armenian": {
        "field": "armenian_translation",
        "code": "hy",
        "description": "Armenian translation in lemma form (Armenian script)",
        "instructions": "- Armenian: Provide standard Eastern Armenian in Armenian script in base form (infinitive for verbs, nominative singular for nouns)\n  - Use Eastern Armenian as the standard variant\n  - Do not include transliteration, just the Armenian characters",
    },
    "azerbaijani": {
        "field": "azerbaijani_translation",
        "code": "az",
        "description": "Azerbaijani translation in lemma form (Latin script)",
        "instructions": "- Azerbaijani: Provide standard Azerbaijani in Latin script in base form (infinitive for verbs ending in -maq/-mek, singular for nouns)",
    },
    "turkish": {
        "field": "turkish_translation",
        "code": "tr",
        "description": "Turkish translation in lemma form",
        "instructions": "- Turkish: Provide standard Turkish (Turkey) in base form (infinitive for verbs ending in -mak/-mek, singular for nouns)",
    },
    "ukrainian": {
        "field": "ukrainian_translation",
        "code": "uk",
        "description": "Ukrainian translation in lemma form (Cyrillic script)",
        "instructions": "- Ukrainian: Provide standard Ukrainian in Cyrillic script in base form (infinitive for verbs, singular nominative for nouns)\n  - Use standard Ukrainian, not surzhyk or Russian loanwords\n  - Do not include transliteration, just the Cyrillic characters",
    },
    "bulgarian": {
        "field": "bulgarian_translation",
        "code": "bg",
        "description": "Bulgarian translation in lemma form (Cyrillic script)",
        "instructions": "- Bulgarian: Provide standard Bulgarian in Cyrillic script in base form (infinitive/da-construction for verbs, singular indefinite for nouns)\n  - Do not include transliteration, just the Cyrillic characters",
    },
    "greek": {
        "field": "greek_translation",
        "code": "el",
        "description": "Greek translation in lemma form (Greek script)",
        "instructions": "- Greek: Provide standard Modern Greek in Greek script in base form (infinitive-equivalent dictionary form for verbs, singular nominative for nouns)\n  - Do not include transliteration, just the Greek characters",
    },
    "croatian": {
        "field": "croatian_translation",
        "code": "hr",
        "description": "Croatian translation in lemma form (Latin script)",
        "instructions": "- Croatian: Provide standard Croatian in Latin script in base form (infinitive for verbs, singular nominative for nouns)",
    },
    "serbian": {
        "field": "serbian_translation",
        "code": "sr",
        "description": "Serbian translation in lemma form (Cyrillic script)",
        "instructions": "- Serbian: Provide standard Serbian in Cyrillic script in base form (infinitive for verbs, singular nominative for nouns)\n  - Do not include transliteration, just the Cyrillic characters",
    },
    "bosnian": {
        "field": "bosnian_translation",
        "code": "bs",
        "description": "Bosnian translation in lemma form (Latin script)",
        "instructions": "- Bosnian: Provide standard Bosnian in Latin script in base form (infinitive for verbs, singular nominative for nouns)",
    },
    "slovenian": {
        "field": "slovenian_translation",
        "code": "sl",
        "description": "Slovenian translation in lemma form",
        "instructions": "- Slovenian: Provide standard Slovenian in base form (infinitive for verbs, singular nominative for nouns)",
    },
    "albanian": {
        "field": "albanian_translation",
        "code": "sq",
        "description": "Albanian translation in lemma form",
        "instructions": "- Albanian: Provide standard Albanian (Tosk-based standard) in base form (lemma for verbs, singular indefinite for nouns)",
    },
}

# Index by language code for fast lookup. Built from DEFAULT_TRANSLATION_LANGUAGES.
DEFAULT_TRANSLATION_LANGUAGES_BY_CODE = {
    config["code"]: config for config in DEFAULT_TRANSLATION_LANGUAGES.values()
}
