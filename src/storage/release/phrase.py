#!/usr/bin/python3

"""Release-file serialization for phrases.

Owns the mapping between ``Phrase`` rows and the records in
``data/release/phrases/{phrase_subtype}/base.jsonl``, with no Flask or CLI
dependency.

Phrases are fixed traveler and greeting expressions. They live in their own
table rather than in ``lemmas``, so they get their own release tree, and they
are the one element type whose builder returns *two* records: secondary-language
translations go to a sibling ``secondary.jsonl`` rather than into the base file.
"""

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session, selectinload

from storage.models.schema import Phrase
from storage.release.io import write_jsonl_atomic


@dataclass(frozen=True)
class PhraseExportStats:
    """What one phrase export wrote."""

    phrases: int = 0
    files: int = 0


def to_release_records(phrase: Any) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """Build the (base, secondary) release JSONL records for a phrase.

    The base record carries RELEASE_LANGUAGES translations (+ metadata), the
    concept label/definition, subtype, and difficulty. Secondary-language
    translations, when present, go to a separate record (written to
    ``secondary.jsonl``); ``None`` when the phrase has none. Translation keys
    are emitted in RELEASE_LANGUAGES / SECONDARY_RELEASE_LANGUAGES order so the
    output is stable and matches the lemma export.

    Shared by the CLI export (``export_sqlite_to_phrase_release``) and the
    Barsukas phrase sync so both write byte-identical files.
    """
    from storage import translation_helpers

    trans_by_lang: Dict[str, Any] = {
        t.language_code: t for t in phrase.translations if t.translation and t.translation.strip()
    }

    def _metadata_for(trans_obj: Any) -> Dict[str, str]:
        meta: Dict[str, str] = {}
        # A bare "conventional" on a living language is the assumed default and
        # is not written out.
        if not translation_helpers.translation_status_is_informative(
            trans_obj.language_code,
            trans_obj.translation_status,
            trans_obj.translation_status_note,
        ):
            return meta
        meta["translation_status"] = trans_obj.translation_status
        if trans_obj.translation_status_note:
            meta["translation_status_note"] = trans_obj.translation_status_note
        return meta

    translations_dict: Dict[str, str] = {}
    translation_metadata_dict: Dict[str, Dict[str, str]] = {}
    secondary_translations_dict: Dict[str, str] = {}
    secondary_metadata_dict: Dict[str, Dict[str, str]] = {}

    for lang_code in translation_helpers.RELEASE_LANGUAGES:
        trans_obj = trans_by_lang.get(lang_code)
        if trans_obj is None:
            continue
        translations_dict[lang_code] = trans_obj.translation
        metadata = _metadata_for(trans_obj)
        if metadata:
            translation_metadata_dict[lang_code] = metadata

    for lang_code in translation_helpers.SECONDARY_RELEASE_LANGUAGES:
        trans_obj = trans_by_lang.get(lang_code)
        if trans_obj is None:
            continue
        secondary_translations_dict[lang_code] = trans_obj.translation
        metadata = _metadata_for(trans_obj)
        if metadata:
            secondary_metadata_dict[lang_code] = metadata

    base_data: Dict[str, Any] = {
        "guid": phrase.guid,
        "phrase_subtype": phrase.phrase_subtype,
        "concept_label": phrase.label,
        "concept_definition": phrase.definition,
    }
    if translations_dict:
        base_data["translations"] = translations_dict
    if translation_metadata_dict:
        base_data["translation_metadata"] = translation_metadata_dict
    if phrase.difficulty_level is not None:
        base_data["difficulty_level"] = phrase.difficulty_level

    secondary_data: Optional[Dict[str, Any]] = None
    if secondary_translations_dict:
        secondary_data = {
            "guid": phrase.guid,
            "translations": secondary_translations_dict,
        }
        if secondary_metadata_dict:
            secondary_data["translation_metadata"] = secondary_metadata_dict

    return base_data, secondary_data


def export_to_release(session: Session, release_dir: Path) -> PhraseExportStats:
    """Export phrases from SQLite to data/release/phrases format.

    Phrases (fixed traveler/greeting expressions) live in their own ``phrases``
    table (no longer in ``lemmas``), so they get their own release tree:

    Structure: {release_dir}/{phrase_subtype}/base.jsonl

    Each base record carries: guid, phrase_subtype, concept_label,
    concept_definition, translations (RELEASE_LANGUAGES), translation_metadata,
    and difficulty_level. Secondary-language translations, when present, go to a
    sibling secondary.jsonl.

    """
    from storage.utils.session import ensure_tables_exist

    ensure_tables_exist(session)
    phrases = (
        session.query(Phrase)
        .filter(Phrase.guid.isnot(None))
        .options(selectinload(Phrase.translations))
        .order_by(Phrase.guid)
        .all()
    )
    print(f"Found {len(phrases)} phrases to export")

    base_by_subtype: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    secondary_by_subtype: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for phrase in phrases:
        base_data, secondary_data = to_release_records(phrase)
        base_by_subtype[phrase.phrase_subtype].append(base_data)
        if secondary_data is not None:
            secondary_by_subtype[phrase.phrase_subtype].append(secondary_data)

    for phrase_subtype, records in base_by_subtype.items():
        category_dir = release_dir / phrase_subtype
        category_dir.mkdir(parents=True, exist_ok=True)
        records.sort(key=lambda r: r["guid"])
        print(f"Exporting {len(records)} phrases to {phrase_subtype}...")
        write_jsonl_atomic(category_dir / "base.jsonl", records)

        secondary_records = secondary_by_subtype.get(phrase_subtype)
        if secondary_records:
            secondary_records.sort(key=lambda r: r["guid"])
            write_jsonl_atomic(category_dir / "secondary.jsonl", secondary_records)

    print("Phrase export complete!")
    return PhraseExportStats(phrases=len(phrases), files=len(base_by_subtype))
