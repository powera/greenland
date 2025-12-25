#!/usr/bin/python

# Levels configuration for verbs and phrases only
# Nouns are now loaded per-level from generated structure files
levels = {
    "level_1": [
        # No verbs or phrases in level 1
    ],
    "level_2": [
        # No verbs or phrases in level 2
    ],
    "level_3": [
        # No verbs or phrases in level 3
    ],
    "level_4": [
    ],
    "level_5": [
    ],
    "level_6": [
        {"corpus": "verbs_present", "group": "Actions & Transactions"},
        {"corpus": "verbs_present", "group": "Basic Needs & Daily Life"},
        {"corpus": "verbs_present", "group": "Mental & Emotional"},
        {"corpus": "verbs_present", "group": "Sensory Perception"},
    ],
    "level_7": [
        {"corpus": "verbs_past", "group": "Mental & Emotional"},
        {"corpus": "verbs_past", "group": "Actions & Transactions"},
        {"corpus": "verbs_past", "group": "Basic Needs & Daily Life"},
        {"corpus": "verbs_past", "group": "Sensory Perception"},
    ],
    "level_8": [
    ],
    "level_9": [
    ],
    "level_10": [
        {"corpus": "phrases_one", "group": "Greetings"},
        {"corpus": "verbs_present", "group": "Learning & Knowledge"},
        {"corpus": "verbs_past", "group": "Learning & Knowledge"},
    ],
    "level_11": [
        # No verbs or phrases in level 11
    ],
    "level_12": [
        {"corpus": "verbs_future", "group": "Basic Needs & Daily Life"},
        {"corpus": "verbs_future", "group": "Mental & Emotional"},
        {"corpus": "verbs_future", "group": "Sensory Perception"},
        {"corpus": "verbs_future", "group": "Learning & Knowledge"},
        {"corpus": "verbs_future", "group": "Actions & Transactions"},
    ],
    "level_13": [
        # No verbs or phrases in level 13
    ],
    "level_14": [
        {"corpus": "verbs_future", "group": "Movement & Travel"},
        {"corpus": "verbs_present", "group": "Movement & Travel"},
        {"corpus": "verbs_past", "group": "Movement & Travel"},
    ],
    "level_15": [
        # No verbs or phrases in level 15
    ],
    "level_16": [
        # No verbs or phrases in level 16
    ],
    "level_17": [
        # No verbs or phrases in level 17
    ],
    "level_18": [
        # No verbs or phrases in level 18
    ],
    "level_19": [
        # No verbs or phrases in level 19
    ],
    "level_20": [
        {"corpus": "phrases_one", "group": "Asking for Directions"},
        {"corpus": "phrases_one", "group": "Transportation"},
        {"corpus": "phrases_one", "group": "Restaurant"},
        {"corpus": "phrases_one", "group": "Personal Comfort"},
        {"corpus": "sentences_twenty", "group": "Generated Sentences"},
    ],
}
