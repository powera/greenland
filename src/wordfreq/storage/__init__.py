"""Storage layer for linguistic data - database models and connections."""

from wordfreq.storage.connection_pool import ConnectionPool, get_session, close_thread_sessions
from wordfreq.storage.database import (
    create_database_session,
    ensure_tables_exist,
    add_word_token,
    add_lemma,
    add_derivative_form,
    add_complete_word_entry,
    get_word_token_by_text,
    get_lemmas_by_subtype,
)

__all__ = [
    "ConnectionPool",
    "get_session",
    "close_thread_sessions",
    "create_database_session",
    "ensure_tables_exist",
    "add_word_token",
    "add_lemma",
    "add_derivative_form",
    "add_complete_word_entry",
    "get_word_token_by_text",
    "get_lemmas_by_subtype",
]
