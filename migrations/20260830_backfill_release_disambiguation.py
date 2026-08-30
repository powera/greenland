#!/usr/bin/env python3
"""Move release senses into the ``disambiguation`` map.

A lemma's English sense used to live only inside the ``concept_label``
parenthetical (``"fine (quality)"``), and every other language's in a separate
``translation_disambiguations`` key. Both now belong in one ``{language: sense}``
map in the base record, English included.

This migration reads the parenthetical, writes it as the ``en`` entry, and folds
any ``translation_disambiguations`` in beside it. ``concept_label`` keeps its
parenthetical: it is display text from here on, and nothing parses it.

The tree is rewritten in place rather than regenerated from a database, so no
import/export cycle is involved and nothing but the sense keys can move.
Rerunning is a no-op: a record whose map already holds a matching ``en`` entry
is left alone, and one whose entry disagrees with its label is reported rather
than overwritten.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

DEFAULT_RELEASE_ROOT = ROOT / "data" / "release"

# The sense in a trailing "(...)" qualifier, e.g. "quality" in "fine (quality)".
# This migration is the last thing that reads a label this way; storage.release
# dropped its parser with the field it fed.
CONCEPT_LABEL_RE = re.compile(r"^(.+?)\s+\(([^)]+)\)$")

# The new key replaces this one and is written in its place, matching the order
# lemma_to_release_record emits, so a migrated tree and a regenerated one
# produce identical lines.
LEGACY_KEY = "translation_disambiguations"


@dataclass
class MigrationResult:
    """Counts and conflicts reported by one migration run."""

    files_scanned: int = 0
    records_scanned: int = 0
    records_updated: int = 0
    records_already_set: int = 0
    legacy_keys_folded: int = 0
    conflicts: List[str] = field(default_factory=list)


def label_disambiguation(concept_label: str) -> Optional[str]:
    """The sense in a concept label's trailing parenthetical, or None."""
    match = CONCEPT_LABEL_RE.match(concept_label.strip())
    return match.group(2).strip() if match else None


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Read JSON objects from a JSONL file."""
    records: List[Dict[str, Any]] = []
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


def _write_jsonl_atomic(path: Path, records: Sequence[Dict[str, Any]]) -> None:
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


def _rebuilt(record: Dict[str, Any], disambiguations: Dict[str, str]) -> Dict[str, Any]:
    """Return ``record`` carrying ``disambiguations``, in canonical key order."""
    rebuilt: Dict[str, Any] = {}
    for key, value in record.items():
        if key == LEGACY_KEY:
            rebuilt["disambiguation"] = disambiguations
            continue
        if key == "disambiguation":
            rebuilt["disambiguation"] = disambiguations
            continue
        rebuilt[key] = value
    if "disambiguation" not in rebuilt:
        rebuilt["disambiguation"] = disambiguations
    return rebuilt


def migrate_file(path: Path, result: MigrationResult, dry_run: bool = False) -> None:
    """Migrate one base.jsonl, recording what changed on ``result``."""
    records = _read_jsonl(path)
    result.files_scanned += 1
    result.records_scanned += len(records)

    rewritten: List[Dict[str, Any]] = []
    changed = False
    for record in records:
        existing = record.get("disambiguation")
        existing_map: Dict[str, str] = dict(existing) if isinstance(existing, dict) else {}
        legacy = record.get(LEGACY_KEY)
        legacy_map: Dict[str, str] = dict(legacy) if isinstance(legacy, dict) else {}
        from_label = label_disambiguation(str(record.get("concept_label") or ""))

        merged: Dict[str, str] = {**legacy_map, **existing_map}
        if from_label:
            if merged.get("en") and merged["en"] != from_label:
                result.conflicts.append(
                    f"{path}: {record.get('guid')} has an en sense "
                    f"{merged['en']!r} but a label reading {from_label!r}"
                )
            else:
                merged.setdefault("en", from_label)

        if merged.get("en") and existing_map.get("en") == merged["en"] and not legacy_map:
            result.records_already_set += 1
            rewritten.append(record)
            continue

        if merged == existing_map and LEGACY_KEY not in record:
            rewritten.append(record)
            continue

        rewritten.append(_rebuilt(record, merged))
        result.records_updated += 1
        if legacy_map:
            result.legacy_keys_folded += 1
        changed = True

    if changed and not dry_run:
        _write_jsonl_atomic(path, rewritten)


def run_migration(
    release_root: Path = DEFAULT_RELEASE_ROOT,
    dry_run: bool = False,
) -> MigrationResult:
    """Migrate every lemma base record under ``release_root``."""
    lemmas_root = release_root / "lemmas"
    if not lemmas_root.exists():
        raise FileNotFoundError(f"{lemmas_root} does not exist; release tree is incomplete")

    result = MigrationResult()
    for base_path in sorted(lemmas_root.rglob("base.jsonl")):
        migrate_file(base_path, result, dry_run=dry_run)
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Parse command-line arguments and run the migration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release-root",
        type=Path,
        default=DEFAULT_RELEASE_ROOT,
        help="Release root containing lemmas/ (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the changes without rewriting the release tree",
    )
    args = parser.parse_args(argv)

    result = run_migration(release_root=args.release_root, dry_run=args.dry_run)

    action = "Would migrate" if args.dry_run else "Migrated"
    print(f"Scanned {result.records_scanned} records in {result.files_scanned} files")
    print(f"{action} {result.records_updated} records")
    print(f"  folded a {LEGACY_KEY} key: {result.legacy_keys_folded}")
    print(f"  already carried the map: {result.records_already_set}")
    for conflict in result.conflicts:
        print(f"CONFLICT: {conflict}")
    return 1 if result.conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
