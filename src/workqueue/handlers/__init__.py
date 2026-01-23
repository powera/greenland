"""Workqueue handlers organized by agent.

Each module in this package contains the workqueue handler(s) for a specific agent.
Handler functions are named handle_{task_type} and take (session, payload) arguments.
"""

from workqueue.handlers.lape import handle_generate_grammar_fact
from workqueue.handlers.papuga import handle_generate_pronunciations
from workqueue.handlers.sarka import handle_generate_conversation
from workqueue.handlers.sernas import handle_generate_synonyms
from workqueue.handlers.vieversys import handle_generate_audio, handle_generate_sentence_audio
from workqueue.handlers.vilkas import handle_generate_forms
from workqueue.handlers.voras import handle_add_missing_translations
from workqueue.handlers.zvirblis import handle_translate_sentence

__all__ = [
    "handle_add_missing_translations",
    "handle_generate_audio",
    "handle_generate_conversation",
    "handle_generate_forms",
    "handle_generate_grammar_fact",
    "handle_generate_pronunciations",
    "handle_generate_sentence_audio",
    "handle_generate_synonyms",
    "handle_translate_sentence",
]
