#!/usr/bin/env python3
"""Pre-commit check: GUID integrity across the data/release JSONL tree.

Usage: python scripts/check_duplicate_guids.py [DATA_DIR]

Two things are checked, both of which break the release contract that a GUID
names exactly one thing, forever:

1. **Duplicates.** A GUID may appear at most once per file, and all of its files
   must live in one directory.  A category directory holds several files that
   describe the same words from different angles -- ``base.jsonl``, the grouped
   translation files (``secondary.jsonl``, ``ancient.jsonl``), the per-language
   files (``en.jsonl``, ``lt.jsonl``, ...) and ``audio.jsonl`` -- so one GUID
   legitimately appears once in each.  The same GUID in *two* directories means
   two different words were given the same number.

2. **Reuse of a retired GUID.** ``tombstones/guid_tombstones.jsonl`` records
   GUIDs that have been permanently retired.  None of them may name a live
   record anywhere in the tree.  ``storage.utils.guid`` enforces this when
   allocating, so a hit here means a file was hand-edited or an import carried
   in a stale number.

Exits 0 if clean, 1 otherwise.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterator, List, Set, Tuple

# Retired GUIDs, not live records: scanned separately and never counted as
# content. See storage.models.guid_tombstone.
TOMBSTONE_RELATIVE_PATH = Path("tombstones") / "guid_tombstones.jsonl"

Location = Tuple[Path, int]


def _iter_guids(jsonl_path: Path) -> Iterator[Tuple[str, int]]:
    """Yield (guid, line number) for every record in a file carrying a GUID.

    Records without a ``guid`` are skipped rather than treated as errors: the
    relation files are keyed by ``concept``, not by GUID.
    """
    with open(jsonl_path, encoding="utf-8") as handle:
        for line_num, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"WARNING: bad JSON in {jsonl_path}:{line_num}: {exc}", file=sys.stderr)
                continue
            if isinstance(entry, dict) and entry.get("guid") is not None:
                yield str(entry["guid"]), line_num


def _collect(data_dir: Path) -> Tuple[Dict[str, List[Location]], Set[str]]:
    """Map every live GUID to where it appears, and collect retired GUIDs."""
    live: Dict[str, List[Location]] = defaultdict(list)
    tombstoned: Set[str] = set()
    tombstone_file = data_dir / TOMBSTONE_RELATIVE_PATH

    for jsonl_path in sorted(data_dir.rglob("*.jsonl")):
        for guid, line_num in _iter_guids(jsonl_path):
            if jsonl_path == tombstone_file:
                tombstoned.add(guid)
            else:
                live[guid].append((jsonl_path, line_num))

    return live, tombstoned


def _report(title: str, offenders: Dict[str, List[Location]]) -> None:
    print(f"FAIL: {len(offenders)} {title}:\n", file=sys.stderr)
    for guid in sorted(offenders):
        print(f"  {guid}:", file=sys.stderr)
        for path, line_num in offenders[guid]:
            print(f"    {path}:{line_num}", file=sys.stderr)
    print("", file=sys.stderr)


def main() -> int:
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/release")

    if not data_dir.is_dir():
        print(f"ERROR: directory not found: {data_dir}", file=sys.stderr)
        return 1

    live, tombstoned = _collect(data_dir)

    duplicates: Dict[str, List[Location]] = {}
    for guid, locations in live.items():
        directories = {path.parent for path, _ in locations}
        files = [path for path, _ in locations]
        if len(directories) > 1 or len(files) != len(set(files)):
            duplicates[guid] = locations

    reused = {guid: live[guid] for guid in sorted(set(live) & tombstoned)}

    failed = False
    if duplicates:
        _report("duplicate GUID(s) found", duplicates)
        failed = True
    if reused:
        _report("retired GUID(s) back in use", reused)
        print(
            "These GUIDs are recorded in "
            f"{TOMBSTONE_RELATIVE_PATH} and must never name a record again.",
            file=sys.stderr,
        )
        failed = True

    if failed:
        return 1

    print(f"OK: {len(live)} unique GUIDs, {len(tombstoned)} tombstoned, no conflicts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
