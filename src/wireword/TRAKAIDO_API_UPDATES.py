"""Trakaido API updates for WireWord exports.

This module documents the Conjugations mode payload added by WireWord.

Context
-------
Conjugations mode now uses per-tense tables that pass through stored
source/target forms directly from the database.

The payload exports *raw* forms by tense and slot:
- Tense keys: preferred ``pres``/``past``/``fut`` for compatibility, plus
  language-specific keys when finer tense distinctions exist (for example
  ``imparfait``, ``perfect``, ``future_i``, ``preterite``).
- Slots: ``1s``, ``2s``, ``3s``, ``1p``, ``2p``, ``3p``
"""

from __future__ import annotations

from typing import Dict, Final, TypedDict

CONJUGATION_SLOT_ORDER: Final[tuple[str, ...]] = ("1s", "2s", "3s", "1p", "2p", "3p")
CONJUGATION_RECOMMENDED_TENSE_KEYS: Final[tuple[str, ...]] = ("pres", "past", "fut")


class ConjugationRawForm(TypedDict):
    """Raw source/target conjugation values for one person/number slot."""

    source: str
    target: str


class ConjugationModePayload(TypedDict):
    """WireWord payload consumed by Trakaido Conjugations mode."""

    format: str
    tables: Dict[str, Dict[str, ConjugationRawForm]]


def payload_example() -> ConjugationModePayload:
    """Return a concrete example of the new payload shape.

    Trakaido can use this as an implementation fixture.
    """

    return {
        "format": "raw_forms_v2",
        "tables": {
            "pres": {
                "1s": {"source": "walk (1s present)", "target": "vaikštau"},
                "2s": {"source": "walk (2s present)", "target": "vaikštai"},
                "3s": {"source": "walks (3s present)", "target": "vaikšto"},
            },
            "fut": {
                "1s": {"source": "will walk (1s future)", "target": "vaikščiosiu"},
            },
        },
    }
