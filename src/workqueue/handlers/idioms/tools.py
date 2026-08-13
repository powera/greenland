"""Shared lookup helpers for idiom capability handlers."""

from __future__ import annotations

from sqlalchemy.orm import Session

from storage.crud.idiom import get_idiom_by_id
from storage.models.idiom import Idiom


def get_idiom_or_raise(session: Session, idiom_id: int) -> Idiom:
    """Retrieve an idiom by ID or raise ValueError if not found.

    Mirrors ``workqueue.tools.get_lemma_or_raise`` so a queued task naming a
    deleted idiom fails with a clear message rather than an AttributeError.
    """
    idiom = get_idiom_by_id(session, idiom_id)
    if idiom is None:
        raise ValueError(f"Idiom not found: {idiom_id}")
    return idiom
