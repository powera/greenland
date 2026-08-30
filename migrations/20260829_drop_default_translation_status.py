#!/usr/bin/env python3
"""Drop uninformative ``translation_status`` entries from the release tree.

The status field was designed for the ancient languages, where *how* a concept
is rendered is itself the evidence ``words.term_age`` reads. For a living
target language the contrast does not exist - an established Spanish or Chinese
word being ``conventional`` is the unremarkable default - so those entries say
nothing and put a metadata block on records that need none.

``storage.translation_helpers.translation_status_is_informative`` is the single
definition of "worth keeping", and the release exporters now apply it. This
migration brings the already-written files into line with what a fresh export
would produce, so re-exporting the database does not churn the tree.

Release-only by design: the database keeps whatever status its rows hold. A
stored ``conventional`` on Spanish is still a judgement somebody recorded and
the Barsukas UI still shows it; it simply stops being written out.

Rerunnable - a second run finds nothing left to drop and reports zero.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from storage.translation_helpers import translation_status_is_informative

DEFAULT_RELEASE_ROOT = ROOT / "data" / "release"

#: Metadata keys this migration is allowed to remove. Anything else a language
#: entry carries (``ipa_pronunciation``, ``sort_key``, ``notes``, ``verified``
#: on names) is preserved untouched.
STATUS_KEYS = frozenset({"translation_status", "translation_status_note"})


@dataclass(frozen=True)
class MigrationResult:
    """Counts reported by one migration run."""

    records_updated: int
    files_updated: int
    language_entries_dropped: int


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read JSON objects from a JSONL file."""
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as input_file:
        for line_number, raw_line in enumerate(input_file, start=1):
            stripped_line = raw_line.strip()
            if not stripped_line:
                continue
            decoded = json.loads(stripped_line)
            if not isinstance(decoded, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            records.append(decoded)
    return records


def _write_jsonl_atomic(path: Path, records: Sequence[dict[str, Any]]) -> None:
    """Atomically replace a JSONL file with ``records``."""
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary_file:
        temporary_path = Path(temporary_file.name)
        try:
            for record in records:
                temporary_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise
    os.replace(temporary_path, path)


def clean_metadata(
    translation_metadata: Dict[str, Any],
) -> tuple[Dict[str, Any], int]:
    """Strip default statuses from one record's ``translation_metadata``.

    Returns the cleaned mapping (which may be empty) and the number of language
    entries a status was dropped from. A language entry that carries other
    extras keeps them and loses only the status keys; one that carried nothing
    else disappears entirely.
    """
    cleaned: Dict[str, Any] = {}
    entries_dropped = 0

    for language_code, entry in translation_metadata.items():
        if not isinstance(entry, dict):
            cleaned[language_code] = entry
            continue
        if translation_status_is_informative(
            language_code,
            entry.get("translation_status"),
            entry.get("translation_status_note"),
        ):
            cleaned[language_code] = entry
            continue
        remainder = {key: value for key, value in entry.items() if key not in STATUS_KEYS}
        if len(remainder) != len(entry):
            entries_dropped += 1
        if remainder:
            cleaned[language_code] = remainder

    return cleaned, entries_dropped


def clean_record(record: Dict[str, Any]) -> tuple[Dict[str, Any], int]:
    """Return ``record`` with default statuses stripped, and the entries dropped."""
    translation_metadata = record.get("translation_metadata")
    if not isinstance(translation_metadata, dict) or not translation_metadata:
        return record, 0

    cleaned, entries_dropped = clean_metadata(translation_metadata)
    if not entries_dropped:
        return record, 0

    rewritten = dict(record)
    if cleaned:
        rewritten["translation_metadata"] = cleaned
    else:
        # Absent rather than empty: an empty object would be a key the exporter
        # never writes, and the round-trip test asserts the two agree.
        del rewritten["translation_metadata"]
    return rewritten, entries_dropped


def migrate_release(
    release_root: Path = DEFAULT_RELEASE_ROOT,
    dry_run: bool = False,
) -> MigrationResult:
    """Rewrite every JSONL file under ``release_root`` that holds a default status."""
    if not release_root.is_dir():
        raise FileNotFoundError(f"{release_root} is not a directory")

    records_updated = 0
    files_updated = 0
    language_entries_dropped = 0

    for path in sorted(release_root.rglob("*.jsonl")):
        records = _read_jsonl(path)
        rewritten_records: list[dict[str, Any]] = []
        file_records_updated = 0

        for record in records:
            rewritten, entries_dropped = clean_record(record)
            rewritten_records.append(rewritten)
            if entries_dropped:
                file_records_updated += 1
                language_entries_dropped += entries_dropped

        if not file_records_updated:
            continue

        records_updated += file_records_updated
        files_updated += 1
        if not dry_run:
            _write_jsonl_atomic(path, rewritten_records)

    return MigrationResult(
        records_updated=records_updated,
        files_updated=files_updated,
        language_entries_dropped=language_entries_dropped,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Parse command-line arguments and run the migration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release-root",
        type=Path,
        default=DEFAULT_RELEASE_ROOT,
        help="Release root to clean (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the changes without writing the release tree",
    )
    args = parser.parse_args(argv)

    result = migrate_release(release_root=args.release_root, dry_run=args.dry_run)
    action = "Would drop" if args.dry_run else "Dropped"
    print(
        f"{action} {result.language_entries_dropped} default statuses "
        f"from {result.records_updated} records in {result.files_updated} files"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
