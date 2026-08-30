"""Read and write ``data/release/lemmas`` base.jsonl records.

Lemmas are the largest release type and the only one whose data is spread over
four file kinds: ``base.jsonl`` for the concept itself, ``{lang}.jsonl`` for
derivative forms, synonyms and grammar facts, and ``secondary.jsonl`` /
``ancient.jsonl`` for the translation tiers that would otherwise make the base
record unwieldy. **This module owns only the base record.** Locating and
rewriting the files stays with the caller (``barsukas.routes.sync.release_io``
for the UI, ``storage.migrate`` for the CLI), because that part genuinely
differs between the two.

What it does own is the mapping in both directions, in one place. Before this
module there were two base-record builders -- one in the sync blueprint, one
inline in ``storage.migrate.export_sqlite_to_release`` -- and they disagreed:
the CLI wrote ``concept_label`` without the disambiguation and omitted ``qid``
and ``translation_disambiguations``, so a CLI export after any UI work stripped
those from the tree, and re-importing it then nulled the disambiguation on
every lemma, because the sense had nowhere else to live.

It has somewhere now. ``disambiguation`` is a ``{language: sense}`` map in the
base record, covering English alongside every other language; it replaces the
old English-only parenthetical and the separate ``translation_disambiguations``
key. Splitting it on import is the same split ``translations`` already makes -
``en`` is the lemma's own column, the rest are per-translation rows.

``concept_label`` is a display string and nothing parses it back apart. A
record's identity is its GUID, so two labels may coincide without ambiguity.

Concepts are deliberately not handled here. A lemma's Wikidata pairing lives in
``concept_lemma_links`` and is written by ``storage.crud.concept``; the only
piece that reaches a release file is the Q-id, which callers pass in and read
back out. See ``docs/element_types_design.md``.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from storage import translation_helpers
from storage.models.schema import Lemma, LemmaTranslation

#: Per-language translation extras, as (release key, model field). Each is
#: omitted from ``translation_metadata`` when unset so a hand-edited file stays
#: readable.
_TRANSLATION_METADATA_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("translation_status", "translation_status"),
    ("translation_status_note", "translation_status_note"),
)

#: Difficulty written when a lemma has none. ``-1`` is the release convention
#: for "not levelled yet" (see data/release/README.md).
UNLEVELLED_DIFFICULTY = -1


# ---------------------------------------------------------------------------
# Release-side readers
#
# The release record is the source of truth for these, so parsing it lives next
# to the code that writes it.
# ---------------------------------------------------------------------------


def build_concept_label(lemma_text: str, disambiguation: Optional[str]) -> str:
    """Join a headword and its optional sense into one display label.

    The result is for people to read. Nothing in the system parses it back
    apart: a sense is read from the ``disambiguation`` map, and identity is the
    GUID. Two records may legitimately share a label.
    """
    return f"{lemma_text} ({disambiguation})" if disambiguation else lemma_text


def release_lemma_text(record: Dict[str, Any]) -> str:
    """The English headword of a release record."""
    english = (record.get("translations") or {}).get("en")
    return str(english) if english else ""


def release_disambiguations(record: Dict[str, Any]) -> Dict[str, str]:
    """The ``{language: sense}`` map of a release record."""
    raw = record.get("disambiguation")
    if not isinstance(raw, dict):
        return {}
    return {
        str(language): str(sense).strip()
        for language, sense in raw.items()
        if sense and str(sense).strip()
    }


def release_disambiguation(record: Dict[str, Any], language_code: str = "en") -> Optional[str]:
    """One language's sense from a release record, or None."""
    return release_disambiguations(record).get(language_code)


def normalize_emoji_entry(item: Any) -> Optional[Dict[str, str]]:
    """Coerce one emoji-list item into a ``{type, value}`` dict, or None.

    Accepts either the canonical dict form or a bare Unicode string (legacy).
    """
    if isinstance(item, dict):
        entry_type = str(item.get("type", "")).strip()
        value = str(item.get("value", "")).strip()
        if entry_type in ("unicode", "image") and value:
            return {"type": entry_type, "value": value}
        return None
    if isinstance(item, str) and item.strip():
        return {"type": "unicode", "value": item.strip()}
    return None


def normalize_emoji_list(raw: Any) -> List[Dict[str, str]]:
    """Normalize any emoji-list shape into a list of ``{type, value}`` dicts."""
    if not isinstance(raw, list):
        return []
    entries: List[Dict[str, str]] = []
    for item in raw:
        entry = normalize_emoji_entry(item)
        if entry is not None:
            entries.append(entry)
    return entries


def decode_db_emoji(raw: Optional[str]) -> List[Dict[str, str]]:
    """Decode the JSON-encoded emoji list stored on ``Lemma.emoji``.

    Returns ``[]`` for null/empty/unparseable values so an equality check
    against a record with no ``emoji`` key treats both as "no emoji".
    """
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return normalize_emoji_list(value)


def encode_db_emoji(entries: List[Dict[str, str]]) -> Optional[str]:
    """Encode an emoji list for storage on ``Lemma.emoji`` (None when empty)."""
    return json.dumps(entries) if entries else None


def release_emoji(record: Dict[str, Any]) -> List[Dict[str, str]]:
    """The emoji list of a release record (missing -> ``[]``)."""
    return normalize_emoji_list(record.get("emoji"))


# ---------------------------------------------------------------------------
# Database -> release
# ---------------------------------------------------------------------------


def translation_metadata_record(translation: LemmaTranslation) -> Dict[str, str]:
    """Build the ``translation_metadata`` entry for one translation (may be empty).

    An uninformative ``translation_status`` - a bare ``conventional`` on a
    living language, which is what every ordinary word is - is dropped along
    with its note, so it never reaches the file. See
    ``translation_helpers.translation_status_is_informative``.
    """
    metadata: Dict[str, str] = {}
    if not translation_helpers.translation_status_is_informative(
        translation.language_code,
        translation.translation_status,
        translation.translation_status_note,
    ):
        return metadata
    for release_key, model_field in _TRANSLATION_METADATA_FIELDS:
        value = getattr(translation, model_field, None)
        if value:
            metadata[release_key] = value
    return metadata


def lemma_to_release_record(lemma: Lemma, *, qid: Optional[str] = None) -> Dict[str, Any]:
    """Build the ``base.jsonl`` record for one lemma.

    Args:
        lemma: The lemma, with ``translations`` and ``difficulty_overrides``
            loaded (both are read).
        qid: The Wikidata Q-id this lemma is paired with, or None when it is
            unpaired. Passed in rather than looked up: the pairing lives in
            ``concept_lemma_links`` and resolving it is the caller's job, which
            keeps this function free of concept queries.

    Translations are emitted in ``RELEASE_LANGUAGES`` order with ``en`` first,
    so re-exporting an unchanged database is byte-stable.
    """
    by_language: Dict[str, LemmaTranslation] = {
        translation.language_code: translation for translation in lemma.translations
    }

    translations: Dict[str, str] = {"en": lemma.lemma_text}
    disambiguations: Dict[str, str] = {}
    translation_metadata: Dict[str, Dict[str, str]] = {}

    for language_code in translation_helpers.RELEASE_LANGUAGES:
        if language_code == "en":
            continue
        translation = by_language.get(language_code)
        if translation is None or not translation.translation:
            continue
        translations[language_code] = translation.translation
        if translation.disambiguation:
            disambiguations[language_code] = translation.disambiguation
        metadata = translation_metadata_record(translation)
        if metadata:
            translation_metadata[language_code] = metadata

    release_languages = set(translation_helpers.RELEASE_LANGUAGES)
    difficulty_overrides: Dict[str, int] = {
        override.language_code: override.difficulty_level
        for override in lemma.difficulty_overrides
        if override.language_code in release_languages
    }

    record: Dict[str, Any] = {
        "guid": lemma.guid,
        "pos_type": lemma.pos_type,
        "pos_subtype": lemma.pos_subtype or "",
        "concept_label": build_concept_label(lemma.lemma_text, lemma.disambiguation),
        "concept_definition": lemma.definition_text or "",
        "translations": translations,
        "difficulty_level": (
            lemma.difficulty_level if lemma.difficulty_level is not None else UNLEVELLED_DIFFICULTY
        ),
    }

    # One {language: sense} map. English is the lemma's own column and the
    # others are per-translation, but the release presents them uniformly.
    if lemma.disambiguation:
        disambiguations["en"] = lemma.disambiguation
    if disambiguations:
        record["disambiguation"] = disambiguations
    if translation_metadata:
        record["translation_metadata"] = translation_metadata
    if difficulty_overrides:
        record["difficulty_overrides"] = difficulty_overrides
    if lemma.lexical_gap_reason:
        record["lexical_gap_reason"] = lemma.lexical_gap_reason
    if lemma.notes:
        record["notes"] = lemma.notes
    # Omitted when unrated: an absent key means nobody has judged this sense,
    # which readers treat as "common". Writing "common" for a NULL would make
    # a round-trip claim a rating that was never made.
    if lemma.sense_prominence:
        record["sense_prominence"] = lemma.sense_prominence

    emoji = decode_db_emoji(lemma.emoji)
    if emoji:
        record["emoji"] = emoji

    if qid:
        record["qid"] = qid

    return record


# ---------------------------------------------------------------------------
# Release -> database
# ---------------------------------------------------------------------------


def apply_base_fields(lemma: Lemma, record: Dict[str, Any]) -> None:
    """Overwrite a lemma's base-concept fields from a release record.

    Covers exactly the fields :func:`lemma_to_release_record` writes onto the
    ``Lemma`` row itself. Translations, grammar facts and the concept pairing
    are separate and stay with the caller.
    """
    lemma.lemma_text = release_lemma_text(record)
    lemma.disambiguation = release_disambiguation(record)
    lemma.definition_text = record.get("concept_definition", "") or ""
    lemma.notes = record.get("notes") or None
    lemma.lexical_gap_reason = record.get("lexical_gap_reason") or None
    lemma.sense_prominence = record.get("sense_prominence") or None
    lemma.emoji = encode_db_emoji(release_emoji(record))


def apply_translations(session: Session, lemma: Lemma, record: Dict[str, Any]) -> int:
    """Create or update this lemma's translations from a release record.

    English is the lemma text, not a translation row, so it is skipped. Returns
    the number of languages written.
    """
    translations = record.get("translations") or {}
    # The "en" entry belongs to the lemma row, not here; apply_base_fields
    # takes it. Everything else annotates a translation.
    disambiguations = release_disambiguations(record)
    metadata_by_language = record.get("translation_metadata") or {}

    existing_by_language: Dict[str, LemmaTranslation] = {
        translation.language_code: translation for translation in lemma.translations
    }

    written = 0
    for language_code, text in translations.items():
        if language_code == "en" or not text:
            continue
        metadata = metadata_by_language.get(language_code, {})
        translation = existing_by_language.get(language_code)
        if translation is None:
            translation = LemmaTranslation(lemma_id=lemma.id, language_code=language_code)
            session.add(translation)
        translation.translation = text
        translation.disambiguation = disambiguations.get(language_code)
        translation.translation_status = metadata.get("translation_status")
        translation.translation_status_note = metadata.get("translation_status_note")
        translation.sort_key = translation_helpers.compute_sort_key(language_code, text)
        written += 1
    return written


def import_release_record(session: Session, record: Dict[str, Any]) -> Lemma:
    """Create a new lemma (and its translations) from a release record.

    The caller is responsible for the GUID not already existing, for grammar
    facts, and for the concept pairing.
    """
    lemma = Lemma(
        guid=record.get("guid"),
        lemma_text=release_lemma_text(record),
        disambiguation=release_disambiguation(record),
        definition_text=record.get("concept_definition", "") or "",
        pos_type=record.get("pos_type", "") or "",
        pos_subtype=record.get("pos_subtype") or None,
        difficulty_level=record.get("difficulty_level"),
        notes=record.get("notes") or None,
        lexical_gap_reason=record.get("lexical_gap_reason") or None,
        sense_prominence=record.get("sense_prominence") or None,
        emoji=encode_db_emoji(release_emoji(record)),
    )
    session.add(lemma)
    session.flush()  # assign lemma.id before the translations reference it

    apply_translations(session, lemma, record)
    return lemma
