"""Compatibility imports for the former Sarka CLI module."""

from sentences.conversation_cli import (
    enqueue_definition_work,
    enqueue_level_work,
    get_argument_parser,
    get_conversation_queue_stats,
    get_sarka_queue_stats,
    main,
    show_level_words,
)

__all__ = [
    "enqueue_definition_work",
    "enqueue_level_work",
    "get_argument_parser",
    "get_conversation_queue_stats",
    "get_sarka_queue_stats",
    "main",
    "show_level_words",
]
