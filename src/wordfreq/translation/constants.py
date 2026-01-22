#!/usr/bin/python3

"""Constants and configuration for linguistic analysis."""

from typing import Any, Dict

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
        "description": "Chinese translation in lemma form (Traditional characters)",
        "instructions": "- Chinese: Provide Traditional Chinese characters (繁體字) in base form\n  - Use natural spoken Mainland Mandarin forms (e.g., 鞋子 not bare 鞋, but 水 not 水份)\n  - Match the generality level of the English word (avoid overly specific translations)\n  - Do not include pinyin, just the characters",
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
    "portuguese": {
        "field": "portuguese_translation",
        "code": "pt",
        "description": "Portuguese translation in lemma form",
        "instructions": "- Portuguese: Provide European Portuguese (Portugal) in base form (infinitive for verbs, singular for nouns)",
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

# Regional variant configuration for pluricentric languages
# Maps base language code to regional variants with their codes and descriptions
REGIONAL_VARIANT_LANGUAGES: Dict[str, Dict[str, Any]] = {
    "en": {
        "display_name": "English",
        "base_description": "American English (default)",
        "variants": {
            "en-US": {
                "name": "American English",
                "description": "Standard American English spelling and vocabulary",
            },
            "en-GB": {
                "name": "British English",
                "description": "British English spelling (colour, favour) and vocabulary (lorry, flat)",
            },
            "en-AU": {
                "name": "Australian English",
                "description": "Australian English spelling and vocabulary",
            },
        },
    },
    "es": {
        "display_name": "Spanish",
        "base_description": "Peninsular Spanish (Spain, default)",
        "variants": {
            "es-ES": {
                "name": "Peninsular Spanish",
                "description": "Standard Castilian Spanish as spoken in Spain",
            },
            "es-MX": {
                "name": "Mexican Spanish",
                "description": "Mexican Spanish vocabulary (computadora, carro, platicar)",
            },
            "es-AR": {
                "name": "Argentine Spanish",
                "description": "Argentine Spanish vocabulary (vos forms, local terms)",
            },
        },
    },
    "pt": {
        "display_name": "Portuguese",
        "base_description": "Brazilian Portuguese (default)",
        "variants": {
            "pt-BR": {
                "name": "Brazilian Portuguese",
                "description": "Brazilian Portuguese spelling and vocabulary (ônibus, trem)",
            },
            "pt-PT": {
                "name": "European Portuguese",
                "description": "European Portuguese spelling and vocabulary (autocarro, comboio)",
            },
        },
    },
    "zh": {
        "display_name": "Chinese",
        "base_description": "Mandarin Chinese (default)",
        "variants": {
            "zh-CN": {
                "name": "Mandarin (Simplified)",
                "description": "Standard Mandarin as spoken in Mainland China",
            },
            "zh-TW": {
                "name": "Taiwanese Mandarin",
                "description": "Mandarin as spoken in Taiwan with local vocabulary",
            },
            "zh-HK": {
                "name": "Cantonese",
                "description": "Cantonese as spoken in Hong Kong (written form)",
            },
        },
    },
}
