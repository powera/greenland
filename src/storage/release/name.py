"""Read and write ``data/release/names`` JSONL records.

A name is a proper noun that appears in our texts but is not vocabulary --
"George", "Fresh Mart", "Maple Street". What makes it release data rather than
scratch state is the per-language rendering: Lithuanian needs ``Džordžas``,
Chinese ``乔治``, Japanese ``ジョージ``, and those have to be identical in every
sentence that casts the character. See ``storage/models/name_entity.py``.

The record shape deliberately mirrors a lemma ``base.jsonl`` record rather than
inventing a third convention:

* ``translations`` is a flat ``{language_code: rendering}`` map, so a consumer
  that already reads lemma translations reads names with the same code;
* the extras a rendering can carry -- IPA, phonetic respelling, the romanized
  sort key, a verified flag -- live in ``translation_metadata`` keyed by the
  same language codes, exactly as translation status does for lemmas.

Names are not levelled and carry no definition, so there is no difficulty or
concept field. All names live in one file: they have a kind, but the kind is
already in the GUID prefix, and splitting a few hundred names across eight
directories would buy nothing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session, selectinload

from storage import translation_helpers
from storage.crud.name_entity import (
    create_name,
    get_name_by_guid,
    next_name_guid,
    set_name_translation,
)
from storage.models.name_entity import NAME_KINDS, Name, NameTranslation

RELEASE_FILENAME = "base.jsonl"

# Per-language extras, as (release key, model field). These are the fields a
# rendering can carry beyond the text itself; each is omitted from the record
# when unset so a hand-edited file stays readable.
_TRANSLATION_METADATA_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("ipa_pronunciation", "ipa_pronunciation"),
    ("phonetic_pronunciation", "phonetic_pronunciation"),
    ("sort_key", "sort_key"),
    ("notes", "notes"),
)


def translation_metadata_record(translation: NameTranslation) -> Dict[str, Any]:
    """Build the ``translation_metadata`` entry for one rendering (may be empty)."""
    metadata: Dict[str, Any] = {}
    for release_key, model_field in _TRANSLATION_METADATA_FIELDS:
        value = getattr(translation, model_field, None)
        if value:
            metadata[release_key] = value
    if translation.verified:
        metadata["verified"] = True
    return metadata


def name_to_release_record(name: Name) -> Dict[str, Any]:
    """Build the release JSONL record for one name.

    Languages are emitted in ``RELEASE_LANGUAGES`` order and then any remaining
    languages alphabetically, so re-exporting an unchanged database is
    byte-stable and nothing is silently dropped.
    """
    by_language: Dict[str, NameTranslation] = {
        translation.language_code: translation
        for translation in name.translations
        if translation.translation
    }
    ordered_languages: List[str] = [
        language_code
        for language_code in translation_helpers.RELEASE_LANGUAGES
        if language_code in by_language
    ]
    ordered_languages.extend(sorted(set(by_language) - set(translation_helpers.RELEASE_LANGUAGES)))

    translations: Dict[str, str] = {}
    translation_metadata: Dict[str, Dict[str, Any]] = {}
    for language_code in ordered_languages:
        translation = by_language[language_code]
        translations[language_code] = translation.translation
        metadata = translation_metadata_record(translation)
        if metadata:
            translation_metadata[language_code] = metadata

    record: Dict[str, Any] = {
        "guid": name.guid,
        "kind": name.kind,
        "name_text": name.name_text,
    }
    if name.disambiguation:
        record["disambiguation"] = name.disambiguation
    if name.gender:
        record["gender"] = name.gender
    record["translations"] = translations
    if translation_metadata:
        record["translation_metadata"] = translation_metadata
    if name.notes:
        record["notes"] = name.notes
    if name.verified:
        record["verified"] = True
    return record


def read_release_records(release_dir: Path) -> List[Dict[str, Any]]:
    """Read name records from a release directory, in file order."""
    release_file = Path(release_dir) / RELEASE_FILENAME
    if not release_file.exists():
        return []

    records: List[Dict[str, Any]] = []
    with release_file.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                records.append(json.loads(stripped))
    return records


def read_release_records_by_guid(release_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Read name records keyed by GUID, dropping any record without one."""
    return {
        str(record["guid"]): record
        for record in read_release_records(release_dir)
        if record.get("guid")
    }


def write_release_records(release_dir: Path, records: Iterable[Dict[str, Any]]) -> Path:
    """Write name records to a release directory, sorted by GUID."""
    target_dir = Path(release_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    release_file = target_dir / RELEASE_FILENAME

    ordered = sorted(records, key=lambda record: str(record.get("guid") or ""))
    with release_file.open("w", encoding="utf-8") as handle:
        for record in ordered:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return release_file


def export_names_to_release(session: Session, release_dir: Path) -> int:
    """Export every GUIDed name to the release directory. Returns the count.

    Names without a GUID are drafts - a generator proposed them but they have
    not been given a place in the release namespace - so they are skipped
    rather than assigned one here.
    """
    names = (
        session.query(Name)
        .filter(Name.guid.isnot(None))
        .options(selectinload(Name.translations))
        .order_by(Name.guid)
        .all()
    )
    write_release_records(release_dir, [name_to_release_record(name) for name in names])
    return len(names)


def apply_release_record(session: Session, record: Dict[str, Any], name: Name) -> Name:
    """Overwrite one name's fields and renderings from a release record.

    Renderings present in the record are upserted; renderings the record does
    not mention are deleted, because the release file is the whole truth about
    a name's renderings - leaving a stale one behind would make the database
    disagree with the file it was just synced from.
    """
    name.kind = record.get("kind", name.kind)
    name.name_text = record.get("name_text", name.name_text)
    name.disambiguation = record.get("disambiguation") or None
    name.gender = record.get("gender") or None
    name.notes = record.get("notes") or None
    name.verified = bool(record.get("verified", False))

    translations = record.get("translations") or {}
    metadata_by_language = record.get("translation_metadata") or {}
    for language_code, rendering in translations.items():
        if not rendering:
            continue
        metadata = metadata_by_language.get(language_code, {})
        set_name_translation(
            session,
            name,
            language_code=language_code,
            translation=rendering,
            ipa_pronunciation=metadata.get("ipa_pronunciation"),
            phonetic_pronunciation=metadata.get("phonetic_pronunciation"),
            sort_key=metadata.get("sort_key"),
            verified=bool(metadata.get("verified", False)),
        )

    for translation in list(name.translations):
        if translation.language_code not in translations:
            session.delete(translation)

    session.flush()
    return name


def import_release_record(session: Session, record: Dict[str, Any]) -> Optional[Name]:
    """Create one name (and its renderings) from a release record.

    Returns None when a name with this GUID already exists, so importing the
    same file twice is a no-op rather than a duplicate-key failure. Updating an
    existing name is a reconcile operation with its own conflict rules and
    belongs in the sync UI, matching how idioms are handled.
    """
    guid = record.get("guid")
    if guid and get_name_by_guid(session, str(guid)) is not None:
        return None

    kind = record.get("kind", "other")
    if kind not in NAME_KINDS:
        raise ValueError(f"Unknown name kind {kind!r} in release record {guid!r}")

    name = create_name(
        session,
        name_text=record["name_text"],
        kind=kind,
        disambiguation=record.get("disambiguation"),
        gender=record.get("gender"),
        notes=record.get("notes"),
        verified=bool(record.get("verified", False)),
    )
    name.guid = str(guid) if guid else next_name_guid(session, kind)

    metadata_by_language = record.get("translation_metadata") or {}
    for language_code, rendering in (record.get("translations") or {}).items():
        if not rendering:
            continue
        metadata = metadata_by_language.get(language_code, {})
        set_name_translation(
            session,
            name,
            language_code=language_code,
            translation=rendering,
            ipa_pronunciation=metadata.get("ipa_pronunciation"),
            phonetic_pronunciation=metadata.get("phonetic_pronunciation"),
            sort_key=metadata.get("sort_key"),
            verified=bool(metadata.get("verified", False)),
        )

    session.flush()
    return name


def import_names_from_release(session: Session, release_dir: Path) -> Tuple[int, int]:
    """Import a release directory into the database.

    Returns ``(imported, skipped)``, where skipped counts records whose GUID was
    already present.
    """
    imported = 0
    skipped = 0
    for record in read_release_records(release_dir):
        if import_release_record(session, record) is None:
            skipped += 1
        else:
            imported += 1
    return imported, skipped
