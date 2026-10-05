"""Per-language value sets for the grammar facts that depend on the language.

Read by the task modules' prepare functions and exposed on GrammarFactService
under the same names for its existing callers.
"""

from typing import Any, Dict

from langtools.es import gender as es_gender
from langtools.fr import gender as fr_gender

# Language-specific gender systems configuration
GENDER_SYSTEMS: Dict[str, Dict[str, Any]] = {
    "fr": {
        "name": "French",
        "genders": fr_gender.GENDERS,
        "description": fr_gender.GENDER_SYSTEM_DESCRIPTION,
    },
    "lt": {
        "name": "Lithuanian",
        "genders": ["masculine", "feminine"],
        "description": "2-way system (masculine/feminine)",
    },
    "es": {
        "name": "Spanish (Spain)",
        "genders": es_gender.GENDERS,
        "description": es_gender.GENDER_SYSTEM_DESCRIPTION_SPAIN,
    },
    "es-419": {
        "name": "Spanish (Latin America)",
        "genders": es_gender.GENDERS,
        "description": es_gender.GENDER_SYSTEM_DESCRIPTION_LATIN_AMERICA,
    },
    "de": {
        "name": "German",
        "genders": ["masculine", "feminine", "neuter"],
        "description": "3-way system (masculine/feminine/neuter)",
    },
    "pt": {
        "name": "Portuguese",
        "genders": ["masculine", "feminine"],
        "description": "2-way system (masculine/feminine)",
    },
    "it": {
        "name": "Italian",
        "genders": ["masculine", "feminine"],
        "description": "2-way system (masculine/feminine)",
    },
}

# Language-specific auxiliary verb systems
AUXILIARY_SYSTEMS: Dict[str, Dict[str, Any]] = {
    "fr": {
        "name": "French",
        "auxiliaries": ["avoir", "être"],
        "description": "avoir (most verbs) or être (motion/reflexive verbs)",
    },
    "de": {
        "name": "German",
        "auxiliaries": ["haben", "sein"],
        "description": "haben (most verbs) or sein (motion/state change verbs)",
    },
    "it": {
        "name": "Italian",
        "auxiliaries": ["avere", "essere"],
        "description": "avere (most verbs) or essere (motion/reflexive verbs)",
    },
    "nl": {
        "name": "Dutch",
        "auxiliaries": ["hebben", "zijn"],
        "description": "hebben (most verbs) or zijn (motion/state change verbs)",
    },
}

# Language-specific reflexivity systems
REFLEXIVITY_SYSTEMS: Dict[str, Dict[str, Any]] = {
    "fr": {
        "name": "French",
        "values": ["inherently_reflexive", "optionally_reflexive", "non_reflexive"],
        "description": "se + verb for reflexive forms",
    },
    "es": {
        "name": "Spanish",
        "values": ["inherently_reflexive", "optionally_reflexive", "non_reflexive"],
        "description": "se + verb for reflexive forms",
    },
    "de": {
        "name": "German",
        "values": ["inherently_reflexive", "optionally_reflexive", "non_reflexive"],
        "description": "sich + verb for reflexive forms",
    },
    "lt": {
        "name": "Lithuanian",
        "values": ["inherently_reflexive", "optionally_reflexive", "non_reflexive"],
        "description": "-si/-tis suffix for reflexive forms",
    },
    "it": {
        "name": "Italian",
        "values": ["inherently_reflexive", "optionally_reflexive", "non_reflexive"],
        "description": "si + verb for reflexive forms",
    },
}
