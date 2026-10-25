"""Stable audio addresses for gender variants within a lemma."""

from typing import Optional

from storage.models.variant_form import GENDER_VARIANT_KEYS


def gender_audio_slot(referent_gender: str, grammatical_form: Optional[str] = None) -> str:
    """Address variant audio in the existing grammatical_form audio key.

    Ordinary lemma audio keeps its existing NULL/base or inflection key. A
    variant needs a namespace so female and male singular audio cannot collide.
    """
    if referent_gender not in GENDER_VARIANT_KEYS:
        raise ValueError(f"Invalid gender variant key: {referent_gender!r}")
    return f"variant/gender/{referent_gender}/{grammatical_form or 'base'}"
