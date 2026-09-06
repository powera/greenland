"""Read and write ``data/release/idioms`` JSONL records.

The record shape is fixed by ``docs/element_types_design.md``: an idiom is a
source-language expression plus a shared meaning, and its equivalents are
arrays keyed by target language - arrays even when there is exactly one, so a
consumer never has to branch on cardinality.

Two absences are deliberately distinguished:

* a language key missing from ``equivalents`` means *not assessed*;
* a language key present with an empty array means *assessed, no equivalent
  exists in this language*.

Collapsing those would let unfinished work read as a linguistic claim. The
storage schema cannot yet express the second case (see the design doc's
deferred decisions), so imports preserve it in the file and exports emit only
what the database can back.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session, selectinload

from storage import translation_helpers
from storage.crud.idiom import add_idiom_equivalent, create_idiom
from storage.models.idiom import Idiom, IdiomEquivalent

# The release file keeps camelCase for multi-word keys, matching the design doc
# and the Trakaido-facing contract, while the ORM uses snake_case.
_EQUIVALENT_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("literalGloss", "literal_gloss"),
    ("usageNote", "usage_note"),
    ("register", "register"),
    ("region", "region"),
)

RELEASE_FILENAME = "base.jsonl"


def equivalent_to_release_record(equivalent: IdiomEquivalent) -> Dict[str, Any]:
    """Build one equivalent's release record.

    ``expression`` and ``kind`` are always present; the optional fields are
    omitted rather than emitted as null, so a hand-edited file stays readable.
    """
    record: Dict[str, Any] = {
        "expression": equivalent.expression,
        "kind": equivalent.equivalence_kind,
    }
    for release_key, model_field in _EQUIVALENT_FIELDS:
        value = getattr(equivalent, model_field, None)
        if value:
            record[release_key] = value
    if equivalent.verified:
        record["verified"] = True
    return record


def idiom_to_release_record(idiom: Idiom) -> Dict[str, Any]:
    """Build the release JSONL record for one idiom.

    Equivalents are grouped by language and sorted within a language by kind
    then expression, so re-exporting an unchanged database is byte-stable.
    """
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for equivalent in sorted(
        idiom.equivalents,
        key=lambda row: (row.equivalence_kind, row.expression),
    ):
        grouped.setdefault(equivalent.language_code, []).append(
            equivalent_to_release_record(equivalent)
        )

    # Emit languages in RELEASE_LANGUAGES order, matching every other release
    # file, then any remaining languages alphabetically so nothing is dropped.
    equivalents_by_language: Dict[str, List[Dict[str, Any]]] = {
        language_code: grouped[language_code]
        for language_code in translation_helpers.RELEASE_LANGUAGES
        if language_code in grouped
    }
    for language_code in sorted(set(grouped) - set(translation_helpers.RELEASE_LANGUAGES)):
        equivalents_by_language[language_code] = grouped[language_code]

    record: Dict[str, Any] = {
        "guid": idiom.guid,
        "source": {
            "language": idiom.source_language_code,
            "expression": idiom.expression,
        },
        "meaning": idiom.meaning,
        "equivalents": equivalents_by_language,
    }
    if idiom.usage_note:
        record["usageNote"] = idiom.usage_note
    if idiom.register:
        record["register"] = idiom.register
    if idiom.region:
        record["region"] = idiom.region
    if idiom.difficulty_level is not None:
        record["difficulty_level"] = idiom.difficulty_level
    if idiom.verified:
        record["verified"] = True
    return record


def read_release_records(release_dir: Path) -> List[Dict[str, Any]]:
    """Read idiom records from a release directory, in file order."""
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


def write_release_records(release_dir: Path, records: Iterable[Dict[str, Any]]) -> Path:
    """Write idiom records to a release directory, sorted by GUID.

    Sorting by GUID matches the convention for every other release file: new
    entries append at the end of the namespace and removed GUIDs leave gaps.
    """
    target_dir = Path(release_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    release_file = target_dir / RELEASE_FILENAME

    ordered = sorted(records, key=lambda record: str(record.get("guid") or ""))
    with release_file.open("w", encoding="utf-8") as handle:
        for record in ordered:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return release_file


def export_idioms_to_release(session: Session, release_dir: Path) -> int:
    """Export every GUIDed idiom to the release directory. Returns the count.

    Idioms without a GUID are drafts that have not been assigned a place in the
    release namespace, so they are skipped rather than given one here.
    """
    idioms = (
        session.query(Idiom)
        .filter(Idiom.guid.isnot(None))
        .options(selectinload(Idiom.equivalents))
        .order_by(Idiom.guid)
        .all()
    )
    write_release_records(release_dir, [idiom_to_release_record(idiom) for idiom in idioms])
    return len(idioms)


def read_release_records_by_guid(release_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Read idiom records keyed by GUID, dropping any record without one."""
    return {
        str(record["guid"]): record
        for record in read_release_records(release_dir)
        if record.get("guid")
    }


def apply_release_record(session: Session, record: Dict[str, Any], idiom: Idiom) -> Idiom:
    """Overwrite one idiom's fields and equivalents from a release record.

    Equivalents are replaced wholesale rather than merged. An equivalent is
    identified by (language, expression), so a corrected spelling would merge as
    an *addition* and leave the old wording behind; replacing avoids inventing a
    second equivalent nobody asked for. The reverse direction - writing the
    database's idiom into the file - goes through
    :func:`idiom_to_release_record`, so the two stay symmetric.
    """
    source = record.get("source") or {}
    idiom.source_language_code = source.get("language", idiom.source_language_code)
    idiom.expression = source.get("expression", idiom.expression)
    idiom.meaning = record.get("meaning", idiom.meaning)
    idiom.usage_note = record.get("usageNote") or None
    idiom.register = record.get("register") or None
    idiom.region = record.get("region") or None
    idiom.difficulty_level = record.get("difficulty_level")
    idiom.verified = bool(record.get("verified", False))

    for existing_equivalent in list(idiom.equivalents):
        session.delete(existing_equivalent)
    session.flush()

    # A separate name from the ORM rows deleted above: these are release
    # records (dicts), and reusing one name for both types is what let the
    # dict lookups below be read as attribute access on IdiomEquivalent.
    for language_code, equivalent_records in (record.get("equivalents") or {}).items():
        for equivalent_record in equivalent_records:
            add_idiom_equivalent(
                session,
                idiom,
                language_code=language_code,
                expression=equivalent_record["expression"],
                equivalence_kind=equivalent_record["kind"],
                literal_gloss=equivalent_record.get("literalGloss"),
                usage_note=equivalent_record.get("usageNote"),
                register=equivalent_record.get("register"),
                region=equivalent_record.get("region"),
                verified=bool(equivalent_record.get("verified", False)),
            )

    session.flush()
    return idiom


def import_release_record(session: Session, record: Dict[str, Any]) -> Optional[Idiom]:
    """Create one idiom (and its equivalents) from a release record.

    Returns None when an idiom with this GUID already exists, so importing the
    same file twice is a no-op rather than a duplicate-key failure. Updating an
    existing idiom from a release file is deliberately not done here: that is a
    reconcile operation with its own conflict rules, which belongs in the sync
    UI alongside the equivalent phrase and sentence flows.
    """
    guid = record.get("guid")
    if guid and session.query(Idiom).filter(Idiom.guid == guid).first() is not None:
        return None

    source = record.get("source") or {}
    idiom = create_idiom(
        session,
        source_language_code=source["language"],
        expression=source["expression"],
        meaning=record["meaning"],
        usage_note=record.get("usageNote"),
        register=record.get("register"),
        region=record.get("region"),
        difficulty_level=record.get("difficulty_level"),
        guid=guid,
        verified=bool(record.get("verified", False)),
    )

    for language_code, equivalents in (record.get("equivalents") or {}).items():
        # An empty array is "assessed, no equivalent exists" - a real state that
        # the schema cannot store yet, so nothing is written for it.
        for equivalent in equivalents:
            add_idiom_equivalent(
                session,
                idiom,
                language_code=language_code,
                expression=equivalent["expression"],
                equivalence_kind=equivalent["kind"],
                literal_gloss=equivalent.get("literalGloss"),
                usage_note=equivalent.get("usageNote"),
                register=equivalent.get("register"),
                region=equivalent.get("region"),
                verified=bool(equivalent.get("verified", False)),
            )

    return idiom


def import_idioms_from_release(session: Session, release_dir: Path) -> Tuple[int, int]:
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
