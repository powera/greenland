"""Task modules for individual grammar fact generators.

``FACT_TASKS`` maps each single-call fact type to its prepare/interpret pair
(see ``words.grammar_fact_tasks.common``).  ``english_principal_parts`` writes
two facts from one call and is not in it.
"""

from typing import Dict

from words.grammar_fact_tasks import (
    animacy,
    auxiliary_verb,
    countability,
    declension_class,
    english_principal_parts,
    fanciful_collective,
    grammatical_gender,
    measure_words,
    verb_reflexivity,
    verb_transitivity,
)
from words.grammar_fact_tasks.common import FactTask

FACT_TASKS: Dict[str, FactTask] = {
    "animacy": animacy.TASK,
    "auxiliary_verb": auxiliary_verb.TASK,
    "countability": countability.TASK,
    "declension_class": declension_class.TASK,
    "fanciful_collective": fanciful_collective.TASK,
    "grammatical_gender": grammatical_gender.TASK,
    "measure_words": measure_words.TASK,
    "verb_reflexivity": verb_reflexivity.TASK,
    "verb_transitivity": verb_transitivity.TASK,
}

__all__ = [
    "FACT_TASKS",
    "animacy",
    "auxiliary_verb",
    "countability",
    "declension_class",
    "english_principal_parts",
    "fanciful_collective",
    "grammatical_gender",
    "measure_words",
    "verb_reflexivity",
    "verb_transitivity",
]
