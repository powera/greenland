"""Storage helpers for keeping derivative-form rhyme keys in sync."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from langtools.rhyme_keys import compute_rhyme_key, rhyme_keys_available

if TYPE_CHECKING:
    from storage.models.schema import DerivativeForm


def compute_rhyme_key_from_ipa(
    ipa_pronunciation: Optional[str],
    language_code: str,
) -> Optional[str]:
    """Return the stored rhyme key for a derivative form pronunciation.

    Only languages advertised by ``rhyme_keys_available()`` produce stored
    rhyme keys. Other languages, or empty pronunciations, return ``None``.
    """
    if not rhyme_keys_available(language_code):
        return None
    if not ipa_pronunciation or not ipa_pronunciation.strip():
        return None
    return compute_rhyme_key(ipa_pronunciation, language_code)


def sync_derivative_form_rhyme_key(derivative_form: "DerivativeForm") -> Optional[str]:
    """Recompute and assign the rhyme key for a derivative form in place."""
    rhyme_key = compute_rhyme_key_from_ipa(
        derivative_form.ipa_pronunciation,
        derivative_form.language_code,
    )
    derivative_form.rhyme_key = rhyme_key
    return rhyme_key
