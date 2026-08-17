#!/usr/bin/python3

"""Shared JSONL read/write machinery for the ``/sync`` blueprints.

Every sync page does the same four things to ``data/release``: read every
``base.jsonl`` under a tree into a GUID-keyed dict, work out which file a GUID
lives in, rewrite some fields on a GUID's line, and rewrite some translations on
a GUID's line. Each blueprint used to carry its own copy of all four, which is
why ``concept_label`` updates and ``difficulty_level`` updates had subtly
different behaviour on a malformed line.

One behavioural note beyond deduplication: :func:`build_guid_file_index` scans
the tree once and answers every lookup from a dict. The per-blueprint
``_find_release_file_for_*`` helpers this replaces re-scanned every file in the
tree *per GUID*, so applying 2000 selected rows meant 2000 full-tree scans.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Sentinel: setting a field to this in an update dict removes the field from the
# release record instead of assigning it (used to clear e.g. "qid" when a lemma
# is unpaired from its concept).
REMOVE_FIELD: Any = object()

BASE_FILENAME = "base.jsonl"


def iter_release_files(release_dir: Path, filename: str = BASE_FILENAME) -> Iterator[Path]:
    """Yield every ``filename`` under ``release_dir`` in a stable order."""
    if not release_dir.exists():
        return
    yield from sorted(release_dir.rglob(filename))


def iter_release_lines(file_path: Path) -> Iterator[Tuple[int, Dict[str, Any]]]:
    """Yield ``(line_number, record)`` for each parseable line of a JSONL file.

    Blank lines are skipped and malformed lines are logged and skipped, so one
    bad hand-edit never hides the rest of a file.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as handle:
            for line_num, raw_line in enumerate(handle, 1):
                stripped = raw_line.strip()
                if not stripped:
                    continue
                try:
                    yield line_num, json.loads(stripped)
                except json.JSONDecodeError as parse_error:
                    logger.error(f"JSON parse error in {file_path}:{line_num}: {parse_error}")
    except OSError as read_error:
        logger.error(f"Error reading {file_path}: {read_error}")


def load_release_records(
    release_dir: Path,
    filename: str = BASE_FILENAME,
    *,
    subtype_key: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Load every record under ``release_dir`` keyed by GUID.

    Args:
        release_dir: Root of the release tree (e.g. ``data/release/lemmas``).
        filename: File name to read in each directory.
        subtype_key: When set, records that lack this key get it filled in from
            the containing directory's name. Phrases rely on this: the subtype
            is the directory, not a stored field.
    """
    records: Dict[str, Dict[str, Any]] = {}
    if not release_dir.exists():
        logger.warning(f"Release directory not found: {release_dir}")
        return records

    for release_file in iter_release_files(release_dir, filename):
        directory_name = release_file.parent.name
        for _, record in iter_release_lines(release_file):
            guid = record.get("guid")
            if not guid:
                continue
            if subtype_key is not None:
                record.setdefault(subtype_key, directory_name)
            records[guid] = record
    return records


def load_records_from_file(file_path: Path) -> Dict[str, Dict[str, Any]]:
    """Load one JSONL file's records keyed by GUID (empty when it is missing)."""
    if not file_path.exists():
        return {}
    return {
        str(record["guid"]): record
        for _, record in iter_release_lines(file_path)
        if record.get("guid")
    }


def build_guid_file_index(release_dir: Path, filename: str = BASE_FILENAME) -> Dict[str, Path]:
    """Map every GUID in the tree to the file that holds it, in one scan.

    Build this once per request that needs file lookups and hand it to
    :func:`file_for_guid`; do not call the two in a loop over GUIDs.
    """
    index: Dict[str, Path] = {}
    for release_file in iter_release_files(release_dir, filename):
        for _, record in iter_release_lines(release_file):
            guid = record.get("guid")
            if guid:
                index[guid] = release_file
    return index


def file_for_guid(index: Dict[str, Path], guid: str) -> Optional[Path]:
    """Return the file holding ``guid``, or None when it is not in the tree."""
    return index.get(guid)


def write_jsonl_sorted(file_path: Path, records: Iterable[Dict[str, Any]]) -> None:
    """Write records to a JSONL file sorted by GUID, creating parent dirs.

    Sorting by GUID is the release convention everywhere: new entries append at
    the end of a namespace and removed GUIDs leave gaps.
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(records, key=lambda record: str(record.get("guid") or ""))
    with open(file_path, "w", encoding="utf-8") as handle:
        for record in ordered:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _rewrite_matching_lines(
    file_path: Path,
    guids: Iterable[str],
    mutate: Any,
) -> int:
    """Rewrite the lines whose GUID is in ``guids``, applying ``mutate(record)``.

    Lines that do not match, and lines that do not parse, are copied through
    byte-for-byte: a sync that touches one word must not reformat its
    neighbours, and must never drop a line it could not read.

    Returns the number of records rewritten.
    """
    if not file_path.exists():
        logger.warning(f"Release file not found: {file_path}")
        return 0

    target_guids = set(guids)
    output_lines: List[str] = []
    rewritten = 0

    with open(file_path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            stripped = raw_line.strip()
            if not stripped:
                output_lines.append(raw_line)
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError:
                output_lines.append(raw_line)
                continue
            if record.get("guid") not in target_guids:
                output_lines.append(raw_line)
                continue
            mutate(record)
            output_lines.append(json.dumps(record, ensure_ascii=False) + "\n")
            rewritten += 1

    with open(file_path, "w", encoding="utf-8") as handle:
        handle.writelines(output_lines)
    return rewritten


def apply_field_updates(updates: Dict[Path, Dict[str, Dict[str, Any]]]) -> int:
    """Apply field updates to release JSONL files.

    ``updates`` is ``{file_path: {guid: {field_or_dotted_path: value}}}``. A
    dotted path such as ``translations.en`` addresses a nested key; a value of
    :data:`REMOVE_FIELD` deletes the field rather than setting it.

    Returns the number of records rewritten.
    """
    rewritten = 0
    for file_path, guid_updates in updates.items():

        def mutate(
            record: Dict[str, Any], guid_updates: Dict[str, Dict[str, Any]] = guid_updates
        ) -> None:
            for field_path, new_value in guid_updates[record["guid"]].items():
                _set_field_path(record, field_path, new_value)

        rewritten += _rewrite_matching_lines(file_path, guid_updates.keys(), mutate)
        logger.info(f"Updated {len(guid_updates)} record(s) in {file_path}")
    return rewritten


def _set_field_path(record: Dict[str, Any], field_path: str, new_value: Any) -> None:
    """Set (or remove) one possibly-dotted field on a release record."""
    if "." in field_path:
        parent_key, child_key = field_path.split(".", 1)
        if new_value is REMOVE_FIELD:
            parent = record.get(parent_key)
            if isinstance(parent, dict):
                parent.pop(child_key, None)
            return
        if not isinstance(record.get(parent_key), dict):
            record[parent_key] = {}
        record[parent_key][child_key] = new_value
        return
    if new_value is REMOVE_FIELD:
        record.pop(field_path, None)
        return
    record[field_path] = new_value


def apply_translation_updates(
    updates: Dict[Path, Dict[str, Dict[str, str]]],
    *,
    disambiguation_prefix: Optional[str] = None,
) -> int:
    """Apply per-language translation updates to release JSONL files.

    ``updates`` is ``{file_path: {guid: {language_code: text}}}``. An empty text
    removes that language from the record rather than storing an empty string,
    so "no translation" round-trips as a missing key the way the release format
    expects.

    Args:
        updates: The per-file, per-GUID, per-language new values.
        disambiguation_prefix: When set, keys carrying this prefix are routed to
            ``translation_disambiguations`` instead of ``translations`` (the
            lemma sync uses ``"_disambig_"`` to ship both in one dict).

    Returns the number of records rewritten.
    """
    rewritten = 0
    for file_path, guid_updates in updates.items():

        def mutate(
            record: Dict[str, Any], guid_updates: Dict[str, Dict[str, str]] = guid_updates
        ) -> None:
            translations = record.setdefault("translations", {})
            for key, new_value in guid_updates[record["guid"]].items():
                if disambiguation_prefix and key.startswith(disambiguation_prefix):
                    language_code = key[len(disambiguation_prefix) :]
                    disambiguations = record.setdefault("translation_disambiguations", {})
                    if new_value:
                        disambiguations[language_code] = new_value
                    else:
                        disambiguations.pop(language_code, None)
                    continue
                if new_value:
                    translations[key] = new_value
                else:
                    translations.pop(key, None)

        rewritten += _rewrite_matching_lines(file_path, guid_updates.keys(), mutate)
        logger.info(f"Updated translations for {len(guid_updates)} record(s) in {file_path}")
    return rewritten


def upsert_records(file_path: Path, records: Iterable[Dict[str, Any]]) -> int:
    """Merge records into a JSONL file by GUID, keeping siblings and sort order.

    Records already in the file are replaced; new ones are inserted. Everything
    is rewritten sorted by GUID. Returns the number of records merged in.
    """
    incoming = {str(record["guid"]): record for record in records}
    merged: Dict[str, Dict[str, Any]] = {}

    if file_path.exists():
        for _, existing in iter_release_lines(file_path):
            guid = existing.get("guid")
            if guid:
                merged[str(guid)] = existing

    merged.update(incoming)
    write_jsonl_sorted(file_path, merged.values())
    return len(incoming)
