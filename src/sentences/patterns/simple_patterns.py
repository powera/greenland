"""
Simple sentence patterns for language learning.

Each pattern defines a template with slots that will be filled with words
from the database to generate simple practice sentences.
"""

SIMPLE_PATTERNS = [
    {
        "pattern_id": "where_is_object",
        "en_template": "Where is the [small object]?",
        "slots": [
            {
                "name": "small object",
                "pos_type": "noun",
                "pos_subtype": "small_movable_object",
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "fixed_words": [{"lemma_text": "where", "pos_type": "pronoun"}],
        "pattern_type": "question",
        "notes": "Basic question about location of an object",
    },
    {
        "pattern_id": "what_is_this_object",
        "en_template": "What is this [small object]?",
        "slots": [
            {
                "name": "small object",
                "pos_type": "noun",
                "pos_subtype": "small_movable_object",
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "pattern_type": "question",
        "notes": "Asking to identify an object",
    },
    {
        "pattern_id": "i_want_to_verb",
        "en_template": "I want to [verb].",
        "slots": [
            {
                "name": "verb",
                "pos_type": "verb",
                "pos_subtype": None,
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "fixed_words": [
            {"lemma_text": "want", "pos_type": "verb"},
            {"lemma_text": "to", "pos_type": "conjunction"},
        ],
        "pattern_type": "SVO",
        "notes": "Expressing desire to perform an action",
    },
    # New patterns with 1 or 2 variables (9-20)
    {
        "pattern_id": "this_is_object",
        "en_template": "This is a [small object].",
        "slots": [
            {
                "name": "small object",
                "pos_type": "noun",
                "pos_subtype": "small_movable_object",
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "pattern_type": "SVO",
        "notes": "Identifying a small object",
    },
    {
        "pattern_id": "do_you_verb",
        "en_template": "Do you [verb]?",
        "slots": [
            {
                "name": "verb",
                "pos_type": "verb",
                "pos_subtype": None,
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "pattern_type": "question",
        "notes": "Yes/no question about an action",
    },
    {
        "pattern_id": "i_need_tool",
        "en_template": "I need a [tool].",
        "slots": [
            {
                "name": "tool",
                "pos_type": "noun",
                "pos_subtype": "tool_machine",
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "fixed_words": [{"lemma_text": "need", "pos_type": "verb"}],
        "pattern_type": "SVO",
        "notes": "Expressing necessity for a tool",
    },
    {
        "pattern_id": "i_am_quality",
        "en_template": "I am [quality].",
        "slots": [
            {
                "name": "quality",
                "pos_type": "adjective",
                "pos_subtype": "quality",
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "pattern_type": "SVO",
        "notes": "Describing one's quality or state",
    },
    {
        "pattern_id": "how_many_objects",
        "en_template": "How many [small object]?",
        "slots": [
            {
                "name": "small object",
                "pos_type": "noun",
                "pos_subtype": "small_movable_object",
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "pattern_type": "question",
        "notes": "Asking about quantity of objects",
    },
    {
        "pattern_id": "the_person_works",
        "en_template": "The [person] works.",
        "slots": [
            {
                "name": "person",
                "pos_type": "noun",
                "pos_subtype": "human",
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "fixed_words": [{"lemma_text": "work", "pos_type": "verb"}],
        "pattern_type": "SVO",
        "notes": "Person (modern profession) working",
    },
    {
        "pattern_id": "my_relation_is_here",
        "en_template": "My [relation] is here.",
        "slots": [
            {
                "name": "relation",
                "pos_type": "noun",
                "pos_subtype": "family_relation",
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "fixed_words": [{"lemma_text": "here", "pos_type": "adverb"}],
        "pattern_type": "SVO",
        "notes": "Family relation being present",
    },
    {
        "pattern_id": "the_occupation_helps",
        "en_template": "The [occupation] helps.",
        "slots": [
            {
                "name": "occupation",
                "pos_type": "noun",
                "pos_subtype": "occupation",
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "fixed_words": [{"lemma_text": "help", "pos_type": "verb"}],
        "pattern_type": "SVO",
        "notes": "Occupation (fantasy/medieval role) performing action",
    },
    # Additional patterns (21-28)
    {
        "pattern_id": "i_feel_emotion",
        "en_template": "I feel [emotion].",
        "slots": [
            {
                "name": "emotion",
                "pos_type": "noun",
                "pos_subtype": "emotion_feeling",
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "fixed_words": [{"lemma_text": "feel", "pos_type": "verb"}],
        "pattern_type": "SVO",
        "notes": "Expressing an emotional state",
    },
    {
        "pattern_id": "i_use_tool",
        "en_template": "I use a [tool].",
        "slots": [
            {
                "name": "tool",
                "pos_type": "noun",
                "pos_subtype": "tool_machine",
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "fixed_words": [{"lemma_text": "use", "pos_type": "verb"}],
        "pattern_type": "SVO",
        "notes": "Using a specific tool",
    },
    # Noun subtype coverage
    {
        "pattern_id": "we_discuss_concept",
        "en_template": "We discuss [concept].",
        "slots": [
            {
                "name": "concept",
                "pos_type": "noun",
                "pos_subtype": "concept_idea",
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "fixed_words": [{"lemma_text": "discuss", "pos_type": "verb"}],
        "pattern_type": "SVO",
        "notes": "Talking about an idea or concept",
    },
    {
        "pattern_id": "i_have_condition",
        "en_template": "I have [condition].",
        "slots": [
            {
                "name": "condition",
                "pos_type": "noun",
                "pos_subtype": "disease_condition",
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "fixed_words": [{"lemma_text": "have", "pos_type": "verb"}],
        "pattern_type": "SVO",
        "notes": "Stating a health condition",
    },
    {
        "pattern_id": "the_furniture_is_here",
        "en_template": "The [furniture] is here.",
        "slots": [
            {
                "name": "furniture",
                "pos_type": "noun",
                "pos_subtype": "furniture",
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "fixed_words": [{"lemma_text": "here", "pos_type": "adverb"}],
        "pattern_type": "SVO",
        "notes": "Locating furniture items",
    },
    {
        "pattern_id": "made_of_material",
        "en_template": "It is made of [material].",
        "slots": [
            {
                "name": "material",
                "pos_type": "noun",
                "pos_subtype": "material_substance",
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "fixed_words": [
            {"lemma_text": "make", "pos_type": "verb"},
            {"lemma_text": "of", "pos_type": "preposition"},
        ],
        "pattern_type": "SVO",
        "notes": "Describing a material substance",
    },
    {
        "pattern_id": "she_is_nationality",
        "en_template": "She is [nationality].",
        "slots": [
            {
                "name": "nationality",
                "pos_type": "noun",
                "pos_subtype": "nationality",
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "pattern_type": "SVO",
        "notes": "Stating a person's nationality",
    },
    {
        "pattern_id": "we_see_natural_feature",
        "en_template": "We see the [natural feature].",
        "slots": [
            {
                "name": "natural feature",
                "pos_type": "noun",
                "pos_subtype": "natural_feature",
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "fixed_words": [{"lemma_text": "see", "pos_type": "verb"}],
        "pattern_type": "SVO",
        "notes": "Observing a natural feature",
    },
    {
        "pattern_id": "my_name_is_personal_name",
        "en_template": "My name is [name].",
        "slots": [
            {
                "name": "name",
                "pos_type": "noun",
                "pos_subtype": "personal_name",
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "pattern_type": "SVO",
        "notes": "Introducing a personal name",
    },
    {
        "pattern_id": "i_live_in_place_name",
        "en_template": "I live in [place name].",
        "slots": [
            {
                "name": "place name",
                "pos_type": "noun",
                "pos_subtype": "place_name",
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "fixed_words": [
            {"lemma_text": "live", "pos_type": "verb"},
            {"lemma_text": "in", "pos_type": "preposition"},
        ],
        "pattern_type": "SVO",
        "notes": "Describing where someone lives",
    },
    {
        "pattern_id": "the_plant_grows",
        "en_template": "The [plant] grows.",
        "slots": [
            {
                "name": "plant",
                "pos_type": "noun",
                "pos_subtype": "plant",
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "fixed_words": [{"lemma_text": "grow", "pos_type": "verb"}],
        "pattern_type": "SVO",
        "notes": "Describing a plant",
    },
    {
        "pattern_id": "it_is_shape",
        "en_template": "It is a [shape].",
        "slots": [
            {
                "name": "shape",
                "pos_type": "noun",
                "pos_subtype": "shape",
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "pattern_type": "SVO",
        "notes": "Identifying a shape",
    },
    {
        "pattern_id": "today_is_temporal_name",
        "en_template": "Today is [temporal name].",
        "slots": [
            {
                "name": "temporal name",
                "pos_type": "noun",
                "pos_subtype": "temporal_name",
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "fixed_words": [{"lemma_text": "today", "pos_type": "adverb"}],
        "pattern_type": "SVO",
        "notes": "Stating a named day or month",
    },
    {
        "pattern_id": "we_wait_time_period",
        "en_template": "We wait a [time period].",
        "slots": [
            {
                "name": "time period",
                "pos_type": "noun",
                "pos_subtype": "time_period",
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "fixed_words": [{"lemma_text": "wait", "pos_type": "verb"}],
        "pattern_type": "SVO",
        "notes": "Waiting for a span of time",
    },
    {
        "pattern_id": "it_is_one_unit",
        "en_template": "It is one [unit].",
        "slots": [
            {
                "name": "unit",
                "pos_type": "noun",
                "pos_subtype": "unit_of_measurement",
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "pattern_type": "SVO",
        "notes": "Stating a unit of measurement",
    },
    {
        "pattern_id": "the_vehicle_moves",
        "en_template": "The [vehicle] moves.",
        "slots": [
            {
                "name": "vehicle",
                "pos_type": "noun",
                "pos_subtype": "vehicle",
                "min_level": 1,
                "max_level": 10,
            }
        ],
        "fixed_words": [{"lemma_text": "move", "pos_type": "verb"}],
        "pattern_type": "SVO",
        "notes": "Describing a vehicle",
    },
]
