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
            {"name": "small object", "pos_type": "noun", "pos_subtype": "small_movable_object", "min_level": 1, "max_level": 10}
        ],
        "fixed_words": [
            {"lemma_text": "where", "pos_type": "pronoun"}
        ],
        "pattern_type": "question",
        "notes": "Basic question about location of an object"
    },
    {
        "pattern_id": "my_object_is_color",
        "en_template": "My [small object] is [color].",
        "slots": [
            {"name": "small object", "pos_type": "noun", "pos_subtype": "small_movable_object", "min_level": 1, "max_level": 10},
            {"name": "color", "pos_type": "adjective", "pos_subtype": "color", "min_level": 1, "max_level": 10}
        ],
        "pattern_type": "SVO",
        "notes": "Describing color of a possessed object"
    },
    {
        "pattern_id": "i_eat_food",
        "en_template": "I eat [food].",
        "slots": [
            {"name": "food", "pos_type": "noun", "pos_subtype": "food", "min_level": 1, "max_level": 10}
        ],
        "fixed_words": [
            {"lemma_text": "eat", "pos_type": "verb"}
        ],
        "pattern_type": "SVO",
        "notes": "Eating specific food"
    },
    {
        "pattern_id": "the_animal_is_quality",
        "en_template": "The [animal] is [quality].",
        "slots": [
            {"name": "animal", "pos_type": "noun", "pos_subtype": "animal", "min_level": 1, "max_level": 10},
            {"name": "quality", "pos_type": "adjective", "pos_subtype": "quality", "min_level": 1, "max_level": 10}
        ],
        "pattern_type": "SVO",
        "notes": "Describing quality/characteristic of an animal"
    },
    {
        "pattern_id": "i_have_number_objects",
        "en_template": "I have [number] [small object].",
        "slots": [
            {"name": "number", "pos_type": "numeral", "pos_subtype": None, "min_level": 1, "max_level": 5},
            {"name": "small object", "pos_type": "noun", "pos_subtype": "small_movable_object", "min_level": 1, "max_level": 10}
        ],
        "fixed_words": [
            {"lemma_text": "have", "pos_type": "verb"}
        ],
        "pattern_type": "SVO",
        "notes": "Expressing quantity of possessed items"
    },
    {
        "pattern_id": "what_is_this_object",
        "en_template": "What is this [small object]?",
        "slots": [
            {"name": "small object", "pos_type": "noun", "pos_subtype": "small_movable_object", "min_level": 1, "max_level": 10}
        ],
        "pattern_type": "question",
        "notes": "Asking to identify an object"
    },
    {
        "pattern_id": "object_is_in_place",
        "en_template": "The [small object] is in the [place].",
        "slots": [
            {"name": "small object", "pos_type": "noun", "pos_subtype": "small_movable_object", "min_level": 1, "max_level": 10},
            {"name": "place", "pos_type": "noun", "pos_subtype": "building_structure", "min_level": 1, "max_level": 10}
        ],
        "fixed_words": [
            {"lemma_text": "in", "pos_type": "preposition"}
        ],
        "pattern_type": "SVO",
        "notes": "Expressing location of an object in a building"
    },
    {
        "pattern_id": "i_want_to_verb",
        "en_template": "I want to [verb].",
        "slots": [
            {"name": "verb", "pos_type": "verb", "pos_subtype": None, "min_level": 1, "max_level": 10}
        ],
        "fixed_words": [
            {"lemma_text": "want", "pos_type": "verb"},
            {"lemma_text": "to", "pos_type": "conjunction"}
        ],
        "pattern_type": "SVO",
        "notes": "Expressing desire to perform an action"
    },
    # New patterns with 1 or 2 variables (9-20)
    {
        "pattern_id": "this_is_object",
        "en_template": "This is a [small object].",
        "slots": [
            {"name": "small object", "pos_type": "noun", "pos_subtype": "small_movable_object", "min_level": 1, "max_level": 10}
        ],
        "pattern_type": "SVO",
        "notes": "Identifying a small object"
    },
    {
        "pattern_id": "i_like_food",
        "en_template": "I like [food].",
        "slots": [
            {"name": "food", "pos_type": "noun", "pos_subtype": "food", "min_level": 1, "max_level": 10}
        ],
        "fixed_words": [
            {"lemma_text": "like", "pos_type": "verb"}
        ],
        "pattern_type": "SVO",
        "notes": "Expressing preference for food"
    },
    {
        "pattern_id": "the_animal_drinks_water",
        "en_template": "The [animal] drinks water.",
        "slots": [
            {"name": "animal", "pos_type": "noun", "pos_subtype": "animal", "min_level": 1, "max_level": 10}
        ],
        "fixed_words": [
            {"lemma_text": "drink", "pos_type": "verb"},
            {"lemma_text": "water", "pos_type": "noun"}
        ],
        "pattern_type": "SVO",
        "notes": "Animal drinking water - demonstrates verb and noun with one variable"
    },
    {
        "pattern_id": "do_you_verb",
        "en_template": "Do you [verb]?",
        "slots": [
            {"name": "verb", "pos_type": "verb", "pos_subtype": None, "min_level": 1, "max_level": 10}
        ],
        "pattern_type": "question",
        "notes": "Yes/no question about an action"
    },
    {
        "pattern_id": "i_need_tool",
        "en_template": "I need a [tool].",
        "slots": [
            {"name": "tool", "pos_type": "noun", "pos_subtype": "tool_machine", "min_level": 1, "max_level": 10}
        ],
        "fixed_words": [
            {"lemma_text": "need", "pos_type": "verb"}
        ],
        "pattern_type": "SVO",
        "notes": "Expressing necessity for a tool"
    },
    {
        "pattern_id": "object_is_color",
        "en_template": "The [small object] is [color].",
        "slots": [
            {"name": "small object", "pos_type": "noun", "pos_subtype": "small_movable_object", "min_level": 1, "max_level": 10},
            {"name": "color", "pos_type": "adjective", "pos_subtype": "color", "min_level": 1, "max_level": 10}
        ],
        "pattern_type": "SVO",
        "notes": "Describing the color of an object"
    },
    {
        "pattern_id": "i_see_animal",
        "en_template": "I see a [animal].",
        "slots": [
            {"name": "animal", "pos_type": "noun", "pos_subtype": "animal", "min_level": 1, "max_level": 10}
        ],
        "fixed_words": [
            {"lemma_text": "see", "pos_type": "verb"}
        ],
        "pattern_type": "SVO",
        "notes": "Observing an animal"
    },
    {
        "pattern_id": "i_am_quality",
        "en_template": "I am [quality].",
        "slots": [
            {"name": "quality", "pos_type": "adjective", "pos_subtype": "quality", "min_level": 1, "max_level": 10}
        ],
        "pattern_type": "SVO",
        "notes": "Describing one's quality or state"
    },
    {
        "pattern_id": "how_many_objects",
        "en_template": "How many [small object]?",
        "slots": [
            {"name": "small object", "pos_type": "noun", "pos_subtype": "small_movable_object", "min_level": 1, "max_level": 10}
        ],
        "pattern_type": "question",
        "notes": "Asking about quantity of objects"
    },
    {
        "pattern_id": "i_want_clothing",
        "en_template": "I want a [clothing].",
        "slots": [
            {"name": "clothing", "pos_type": "noun", "pos_subtype": "clothing_accessory", "min_level": 1, "max_level": 10}
        ],
        "fixed_words": [
            {"lemma_text": "want", "pos_type": "verb"}
        ],
        "pattern_type": "SVO",
        "notes": "Expressing desire for clothing"
    },
    {
        "pattern_id": "the_person_works",
        "en_template": "The [person] works.",
        "slots": [
            {"name": "person", "pos_type": "noun", "pos_subtype": "human", "min_level": 1, "max_level": 10}
        ],
        "fixed_words": [
            {"lemma_text": "work", "pos_type": "verb"}
        ],
        "pattern_type": "SVO",
        "notes": "Person (modern profession) working"
    },
    {
        "pattern_id": "my_relation_is_here",
        "en_template": "My [relation] is here.",
        "slots": [
            {"name": "relation", "pos_type": "noun", "pos_subtype": "family_relation", "min_level": 1, "max_level": 10}
        ],
        "fixed_words": [
            {"lemma_text": "be", "pos_type": "verb"},
            {"lemma_text": "here", "pos_type": "adverb"}
        ],
        "pattern_type": "SVO",
        "notes": "Family relation being present"
    },
    {
        "pattern_id": "the_occupation_helps",
        "en_template": "The [occupation] helps.",
        "slots": [
            {"name": "occupation", "pos_type": "noun", "pos_subtype": "occupation", "min_level": 1, "max_level": 10}
        ],
        "fixed_words": [
            {"lemma_text": "help", "pos_type": "verb"}
        ],
        "pattern_type": "SVO",
        "notes": "Occupation (fantasy/medieval role) performing action"
    },
    {
        "pattern_id": "where_is_building",
        "en_template": "Where is the [building]?",
        "slots": [
            {"name": "building", "pos_type": "noun", "pos_subtype": "building_structure", "min_level": 1, "max_level": 10}
        ],
        "fixed_words": [
            {"lemma_text": "where", "pos_type": "pronoun"}
        ],
        "pattern_type": "question",
        "notes": "Asking about location of a building"
    },
    # Additional patterns (21-28)
    {
        "pattern_id": "i_feel_emotion",
        "en_template": "I feel [emotion].",
        "slots": [
            {"name": "emotion", "pos_type": "noun", "pos_subtype": "emotion_feeling", "min_level": 1, "max_level": 10}
        ],
        "fixed_words": [
            {"lemma_text": "feel", "pos_type": "verb"}
        ],
        "pattern_type": "SVO",
        "notes": "Expressing an emotional state"
    },
    {
        "pattern_id": "my_body_part_hurts",
        "en_template": "My [body part] hurts.",
        "slots": [
            {"name": "body part", "pos_type": "noun", "pos_subtype": "body_part", "min_level": 1, "max_level": 10}
        ],
        "fixed_words": [
            {"lemma_text": "hurt", "pos_type": "verb"}
        ],
        "pattern_type": "SVO",
        "notes": "Expressing physical pain in a body part"
    },
    {
        "pattern_id": "i_drink_food",
        "en_template": "I drink [beverage].",
        "slots": [
            {"name": "beverage", "pos_type": "noun", "pos_subtype": "beverage", "min_level": 1, "max_level": 10}
        ],
        "fixed_words": [
            {"lemma_text": "drink", "pos_type": "verb"}
        ],
        "pattern_type": "SVO",
        "notes": "Drinking beverages"
    },
    {
        "pattern_id": "the_object_is_size",
        "en_template": "The [small object] is [size].",
        "slots": [
            {"name": "small object", "pos_type": "noun", "pos_subtype": "small_movable_object", "min_level": 1, "max_level": 10},
            {"name": "size", "pos_type": "adjective", "pos_subtype": "size", "min_level": 1, "max_level": 10}
        ],
        "pattern_type": "SVO",
        "notes": "Describing size of an object"
    },
    {
        "pattern_id": "i_go_to_place",
        "en_template": "I go to the [place].",
        "slots": [
            {"name": "place", "pos_type": "noun", "pos_subtype": "building_structure", "min_level": 1, "max_level": 10}
        ],
        "fixed_words": [
            {"lemma_text": "walk/go", "pos_type": "verb"},
            {"lemma_text": "to", "pos_type": "preposition"}
        ],
        "pattern_type": "SVO",
        "notes": "Going to a specific place"
    },
    {
        "pattern_id": "the_animal_eats_food",
        "en_template": "The [animal] eats [food].",
        "slots": [
            {"name": "animal", "pos_type": "noun", "pos_subtype": "animal", "min_level": 1, "max_level": 10},
            {"name": "food", "pos_type": "noun", "pos_subtype": "food", "min_level": 1, "max_level": 10}
        ],
        "fixed_words": [
            {"lemma_text": "eat", "pos_type": "verb"}
        ],
        "pattern_type": "SVO",
        "notes": "Animal eating specific food"
    },
    {
        "pattern_id": "i_wear_clothing",
        "en_template": "I wear [clothing].",
        "slots": [
            {"name": "clothing", "pos_type": "noun", "pos_subtype": "clothing_accessory", "min_level": 1, "max_level": 10}
        ],
        "fixed_words": [
            {"lemma_text": "wear", "pos_type": "verb"}
        ],
        "pattern_type": "SVO",
        "notes": "Wearing specific clothing"
    },
    {
        "pattern_id": "i_use_tool",
        "en_template": "I use a [tool].",
        "slots": [
            {"name": "tool", "pos_type": "noun", "pos_subtype": "tool_machine", "min_level": 1, "max_level": 10}
        ],
        "fixed_words": [
            {"lemma_text": "use", "pos_type": "verb"}
        ],
        "pattern_type": "SVO",
        "notes": "Using a specific tool"
    },
]
