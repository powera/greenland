"""Trakaido API updates for WireWord exports.

This module documents the Conjugations mode payload added by WireWord.

Context
-------
Conjugations mode now uses a de-normalized export that passes through the
stored per-slot forms directly from the database.

The payload exports *raw* forms per slot:
- EN/source: ``walk / walk / walks``
- Target: corresponding raw target forms

Redundancy is expected and supported. If all six slots are identical, all six are
still exported.
"""

from __future__ import annotations

from typing import Dict, Final, TypedDict

CONJUGATION_SLOT_ORDER: Final[tuple[str, ...]] = ("1s", "2s", "3s", "1p", "2p", "3p")


class ConjugationRawForm(TypedDict):
    """Raw source/target conjugation values for one person/number slot."""

    source: str
    target: str


class ConjugationModePayload(TypedDict):
    """WireWord payload consumed by Trakaido Conjugations mode."""

    format: str
    forms: Dict[str, ConjugationRawForm]


def payload_example() -> ConjugationModePayload:
    """Return a concrete example of the new payload shape.

    Trakaido can use this as an implementation fixture.
    """

    return {
        "format": "raw_forms_v1",
        "forms": {
            "1s": {"source": "walk", "target": "vaikštau"},
            "2s": {"source": "walk", "target": "vaikštai"},
            "3s": {"source": "walks", "target": "vaikšto"},
            "1p": {"source": "walk", "target": "vaikštome"},
            "2p": {"source": "walk", "target": "vaikštote"},
            "3p": {"source": "walk", "target": "vaikšto"},
        },
    }
