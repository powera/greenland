"""Storage helpers for keeping derivative-form rhyme keys in sync."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, cast

from langtools.rhyme_keys import compute_rhyme_key, rhyme_keys_available

if TYPE_CHECKING:
    from storage.models.schema import DerivativeForm


def is_derivative_form_rhyme_indexable(derivative_form: "DerivativeForm") -> bool:
    """Return ``True`` when a derivative form should receive a stored rhyme key.

    We intentionally skip rhyme indexing for multi-word periphrastic tense forms.
    Minimum enforced policy: English future-tense forms (``*_future``) that
    contain whitespace are excluded from rhyme-key storage. Fixed-phrase lemmas
    (see ``NON_LEXEME_POS_TYPES``) are never rhyme-indexed.
    """
    from storage.translation_helpers import NON_LEXEME_POS_TYPES

    parent_lemma = derivative_form.lemma
    if parent_lemma is not None and parent_lemma.pos_type in NON_LEXEME_POS_TYPES:
        return False

    form_text = derivative_form.derivative_form_text or ""
    normalized_form = form_text.strip()
    if not normalized_form:
        return False

    if len(normalized_form.split()) <= 1:
        return True

    grammatical_form = derivative_form.grammatical_form or ""
    is_english_future_form = derivative_form.language_code == "en" and grammatical_form.endswith(
        "_future"
    )
    if is_english_future_form:
        return False

    return True


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
    return cast(Optional[str], compute_rhyme_key(ipa_pronunciation, language_code))


def sync_derivative_form_rhyme_key(derivative_form: "DerivativeForm") -> Optional[str]:
    """Recompute and assign the rhyme key for a derivative form in place."""
    if not is_derivative_form_rhyme_indexable(derivative_form):
        derivative_form.rhyme_key = None
        return None

    rhyme_key = compute_rhyme_key_from_ipa(
        derivative_form.ipa_pronunciation,
        derivative_form.language_code,
    )
    derivative_form.rhyme_key = rhyme_key
    return rhyme_key
