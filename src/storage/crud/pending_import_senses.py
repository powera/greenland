#!/usr/bin/python3

"""Read and write the sense detail carried on a staged pending import.

``PendingImport.translations`` and ``PendingImport.example_sentences`` hold the
parts of an LLM sense response that have nowhere else to live until the term
becomes a lemma. Both are JSON text columns, in the same style as
``Lemma.tags``: NULL means "nothing was carried", and a malformed value is
logged and treated as empty rather than raising, since a staged row is review
material and must stay readable.

The point of storing them is cost. The staging call already returned a full
translation set and example sentences for the sense; without these columns the
approval step re-queries the LLM for translations it has already been paid for,
and can come back with a different answer than the one the reviewer saw.
"""

import json
from typing import Any, Dict, List, Mapping, Optional, Sequence

from storage.models.imports import PendingImport
from util.logging_config import get_logger

logger = get_logger(__name__)


def decode_translations(raw: Optional[str], context: str = "row") -> Dict[str, str]:
    """Decode a stored translations column into a language code -> text mapping.

    NULL, the empty object and anything unparseable all yield ``{}``. Entries
    with a non-string value or an empty text are dropped: a blank translation
    is the same as an absent one, and storing both shapes would make
    "untranslated" ambiguous.
    """
    if not raw:
        return {}

    try:
        parsed: Any = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("%s has non-JSON translations %r; ignoring them", context, raw)
        return {}

    if not isinstance(parsed, dict):
        logger.warning("%s has unexpected translations JSON %r; ignoring them", context, raw)
        return {}

    decoded: Dict[str, str] = {}
    for lang_code, value in parsed.items():
        if not isinstance(value, str):
            continue
        text = value.strip()
        if text:
            decoded[str(lang_code)] = text
    return decoded


def decode_example_sentences(raw: Optional[str], context: str = "row") -> List[str]:
    """Decode a stored example-sentences column into a list of strings.

    NULL, the empty array and anything unparseable all yield ``[]``. Blank and
    non-string entries are dropped.
    """
    if not raw:
        return []

    try:
        parsed: Any = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("%s has non-JSON example sentences %r; ignoring them", context, raw)
        return []

    if not isinstance(parsed, list):
        logger.warning("%s has unexpected example sentences JSON %r; ignoring them", context, raw)
        return []

    return [item.strip() for item in parsed if isinstance(item, str) and item.strip()]


def read_pending_import_translations(pending_import: PendingImport) -> Dict[str, str]:
    """Return a staged import's carried translations as a mapping."""
    return decode_translations(
        pending_import.translations, context=f"PendingImport {pending_import.id}"
    )


def read_pending_import_example_sentences(pending_import: PendingImport) -> List[str]:
    """Return a staged import's carried example sentences as a list."""
    return decode_example_sentences(
        pending_import.example_sentences, context=f"PendingImport {pending_import.id}"
    )


def serialize_translations(translations: Mapping[str, str]) -> Optional[str]:
    """Encode translations for storage, collapsing the empty mapping to NULL.

    Blank values are dropped before encoding so that "no translation" has one
    representation rather than two.
    """
    cleaned = {
        str(lang_code): value.strip()
        for lang_code, value in translations.items()
        if isinstance(value, str) and value.strip()
    }
    if not cleaned:
        return None
    return json.dumps(cleaned, ensure_ascii=False)


def serialize_example_sentences(sentences: Sequence[str]) -> Optional[str]:
    """Encode example sentences for storage, collapsing the empty list to NULL."""
    cleaned = [item.strip() for item in sentences if isinstance(item, str) and item.strip()]
    if not cleaned:
        return None
    return json.dumps(cleaned, ensure_ascii=False)
