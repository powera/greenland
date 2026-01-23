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

# Default languages and their configurations
# Note: For pluricentric languages (Chinese, Spanish, Portuguese), use the explicit regional
# variants (e.g., "chinese_mainland", "spanish_spain") instead of the deprecated base entries.
DEFAULT_TRANSLATION_LANGUAGES = {
    "lithuanian": {
        "field": "lithuanian_translation",
        "code": "lt",
        "description": "Lithuanian translation in lemma form",
        "instructions": "- Lithuanian: Provide standard Lithuanian in base form (infinitive for verbs, singular nominative for nouns)",
    },
    # Chinese - DEPRECATED base entry (use regional variants below)
    "chinese": {
        "field": "chinese_translation",
        "code": "zh",
        "description": "Chinese translation in lemma form (Traditional characters)",
        "instructions": "- Chinese: Provide Traditional Chinese characters (繁體字) in base form\n  - Use natural spoken Mainland Mandarin forms (e.g., 鞋子 not bare 鞋, but 水 not 水份)\n  - Match the generality level of the English word (avoid overly specific translations)\n  - Do not include pinyin, just the characters",
        "deprecated": True,
    },
    # Chinese regional variants (explicit codes)
    "chinese_mainland": {
        "field": "chinese_mainland_translation",
        "code": "zh-CN",
        "description": "Mainland Chinese (Simplified characters, Mandarin vocabulary)",
        "instructions": "- Chinese (Mainland): Provide Simplified Chinese characters (简体字) using Mainland Mandarin vocabulary\n  - Use natural spoken Mainland forms (e.g., 土豆 for potato, 出租车 for taxi)\n  - Match the generality level of the English word\n  - Do not include pinyin, just the characters",
    },
    "chinese_taiwan": {
        "field": "chinese_taiwan_translation",
        "code": "zh-TW",
        "description": "Taiwanese Mandarin (Traditional characters, Taiwan vocabulary)",
        "instructions": "- Chinese (Taiwan): Provide Traditional Chinese characters (繁體字) using Taiwanese Mandarin vocabulary\n  - Use Taiwan-specific terms where different (e.g., 馬鈴薯 for potato, 計程車 for taxi)\n  - Match the generality level of the English word\n  - Do not include pinyin/zhuyin, just the characters",
    },
    "cantonese": {
        "field": "cantonese_translation",
        "code": "zh-HK",
        "description": "Cantonese (Traditional characters, Hong Kong written form)",
        "instructions": "- Cantonese (Hong Kong): Provide Traditional Chinese characters (繁體字) as written in Hong Kong\n  - Use Cantonese-specific vocabulary and written conventions\n  - Include Cantonese-specific characters where appropriate (e.g., 嘅, 係)\n  - Do not include romanization, just the characters",
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
    # Spanish - DEPRECATED base entry (use regional variants below)
    "spanish": {
        "field": "spanish_translation",
        "code": "es",
        "description": "Spanish translation in lemma form",
        "instructions": "- Spanish: Provide Peninsular Spanish (Spain) in base form (infinitive for verbs, singular for nouns)",
        "deprecated": True,
    },
    # Spanish regional variants (explicit codes)
    "spanish_spain": {
        "field": "spanish_spain_translation",
        "code": "es-ES",
        "description": "Castilian Spanish (Spain)",
        "instructions": "- Spanish (Spain): Provide Peninsular/Castilian Spanish in base form\n  - Use Spain-specific vocabulary (e.g., ordenador, coche, conducir)\n  - Infinitive for verbs, singular for nouns",
    },
    "spanish_latam": {
        "field": "spanish_latam_translation",
        "code": "es-419",
        "description": "Latin American Spanish (general)",
        "instructions": "- Spanish (Latin America): Provide general Latin American Spanish in base form\n  - Use widely understood Latin American vocabulary (e.g., computadora, carro, manejar)\n  - Avoid country-specific slang; prefer pan-Latin American terms\n  - Infinitive for verbs, singular for nouns",
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
    # Portuguese - DEPRECATED base entry (use regional variants below)
    "portuguese": {
        "field": "portuguese_translation",
        "code": "pt",
        "description": "Portuguese translation in lemma form",
        "instructions": "- Portuguese: Provide European Portuguese (Portugal) in base form (infinitive for verbs, singular for nouns)",
        "deprecated": True,
    },
    # Portuguese regional variants (explicit codes)
    "portuguese_brazil": {
        "field": "portuguese_brazil_translation",
        "code": "pt-BR",
        "description": "Brazilian Portuguese",
        "instructions": "- Portuguese (Brazil): Provide Brazilian Portuguese in base form\n  - Use Brazilian vocabulary and spelling (e.g., ônibus, trem, celular)\n  - Infinitive for verbs, singular for nouns",
    },
    "portuguese_portugal": {
        "field": "portuguese_portugal_translation",
        "code": "pt-PT",
        "description": "European Portuguese (Portugal)",
        "instructions": "- Portuguese (Portugal): Provide European Portuguese in base form\n  - Use Portugal vocabulary and spelling (e.g., autocarro, comboio, telemóvel)\n  - Infinitive for verbs, singular for nouns",
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
}
