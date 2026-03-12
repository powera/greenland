"""WireWord manifest grammar metadata for de."""

from __future__ import annotations

from typing import Any


_CONJUGATION_CONFIG: dict[str, Any] = {
    "tenses": [
        {
            "id": "past",
            "label": "Präteritum",
            "order": 1,
            "has_persons": True,
            "person_slots": ["1s", "2s", "3s", "1p", "2p", "3p"],
            "description": "Simple past tense forms.",
        },
        {
            "id": "pres",
            "label": "Präsens",
            "order": 2,
            "has_persons": True,
            "person_slots": ["1s", "2s", "3s", "1p", "2p", "3p"],
            "description": "Present tense conjugations.",
        },
        {
            "id": "fut",
            "label": "Futur I",
            "order": 3,
            "has_persons": True,
            "person_slots": ["1s", "2s", "3s", "1p", "2p", "3p"],
            "description": "Future tense conjugations.",
        },
    ]
}


def get_conjugation_manifest_config() -> dict[str, Any]:
    """Return language-specific conjugation metadata for WireWord manifests."""
    return _CONJUGATION_CONFIG
