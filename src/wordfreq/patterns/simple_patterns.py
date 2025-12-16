"""
Simple sentence patterns for language learning.

Each pattern defines a template with slots that will be filled with words
from the database to generate simple practice sentences.
"""

SIMPLE_PATTERNS = [
    {
        "pattern_id": "where_is_noun",
        "en_template": "Where is the [noun]?",
        "slots": [
            {"name": "noun", "pos_type": "noun", "min_level": 1, "max_level": 10}
        ],
        "pattern_type": "question",
        "notes": "Basic question about location of an object"
    },
    {
        "pattern_id": "my_noun_is_color",
        "en_template": "My [noun] is [color].",
        "slots": [
            {"name": "noun", "pos_type": "noun", "min_level": 1, "max_level": 10},
            {"name": "color", "pos_type": "adjective", "pos_subtype": "color", "min_level": 1, "max_level": 10}
        ],
        "pattern_type": "SVO",
        "notes": "Describing color of a possessed object"
    },
    {
        "pattern_id": "pronoun_is_occupation",
        "en_template": "[Pronoun] is a [occupation].",
        "slots": [
            {"name": "pronoun", "pos_type": "pronoun", "min_level": 1, "max_level": 5},
            {"name": "occupation", "pos_type": "noun", "pos_subtype": "occupation", "min_level": 1, "max_level": 15}
        ],
        "pattern_type": "SVO",
        "notes": "Identifying someone's profession"
    },
    {
        "pattern_id": "the_noun_is_adjective",
        "en_template": "The [noun] is [adjective].",
        "slots": [
            {"name": "noun", "pos_type": "noun", "min_level": 1, "max_level": 10},
            {"name": "adjective", "pos_type": "adjective", "min_level": 1, "max_level": 10}
        ],
        "pattern_type": "SVO",
        "notes": "Basic description of an object"
    },
    {
        "pattern_id": "i_have_number_noun",
        "en_template": "I have [number] [noun].",
        "slots": [
            {"name": "number", "pos_type": "numeral", "min_level": 1, "max_level": 5},
            {"name": "noun", "pos_type": "noun", "min_level": 1, "max_level": 10}
        ],
        "pattern_type": "SVO",
        "notes": "Expressing quantity of possessed items"
    },
    {
        "pattern_id": "what_is_this",
        "en_template": "What is this [noun]?",
        "slots": [
            {"name": "noun", "pos_type": "noun", "min_level": 1, "max_level": 10}
        ],
        "pattern_type": "question",
        "notes": "Asking to identify an object"
    },
    {
        "pattern_id": "noun_is_in_place",
        "en_template": "The [noun] is in the [place].",
        "slots": [
            {"name": "noun", "pos_type": "noun", "min_level": 1, "max_level": 10},
            {"name": "place", "pos_type": "noun", "pos_subtype": "place", "min_level": 1, "max_level": 10}
        ],
        "pattern_type": "SVO",
        "notes": "Expressing location of an object"
    },
    {
        "pattern_id": "i_want_to_verb",
        "en_template": "I want to [verb].",
        "slots": [
            {"name": "verb", "pos_type": "verb", "min_level": 1, "max_level": 10}
        ],
        "pattern_type": "SVO",
        "notes": "Expressing desire to perform an action"
    },
]
