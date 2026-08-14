"""Compatibility imports for former Sarka-named workqueue handlers."""

from workqueue.handlers.conversations.generation import (
    handle_conversations_definitions_generate as handle_generate_definition,
    handle_conversations_generate as handle_generate_conversation,
)

__all__ = ["handle_generate_conversation", "handle_generate_definition"]
