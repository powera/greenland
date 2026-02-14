#!/usr/bin/env python3
"""Pre-commit check: ensure no duplicate GUIDs exist in data/release JSONL files.

Usage: python scripts/check_duplicate_guids.py [DATA_DIR]

Scans all .jsonl files under DATA_DIR (default: data/release) for duplicate
GUID values.  Exits 0 if clean, 1 if duplicates found.
"""

import json
import sys
from pathlib import Path


def main() -> int:
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/release")

    if not data_dir.is_dir():
        print(f"ERROR: directory not found: {data_dir}", file=sys.stderr)
        return 1

    # A GUID may appear in both base.jsonl and secondary.jsonl within the same
    # directory (one entry each).  That is expected, not a duplicate.
    # We flag a GUID as duplicate only when it appears in files that are NOT a
    # base/secondary pair in the same directory, or more than once in any file.

    # guid -> list of (file, line_number)
    seen: dict[str, list[tuple[str, int]]] = {}

    # Files whose stem is "base" or "secondary" form companion pairs.
    COMPANION_STEMS = {"base", "secondary"}

    for jsonl_path in sorted(data_dir.rglob("*.jsonl")):
        with open(jsonl_path, encoding="utf-8") as fh:
            for line_num, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError as exc:
                    print(
                        f"WARNING: bad JSON in {jsonl_path}:{line_num}: {exc}",
                        file=sys.stderr,
                    )
                    continue
                guid = entry.get("guid")
                if guid is None:
                    continue
                location = (str(jsonl_path), line_num)
                seen.setdefault(guid, []).append(location)

    def _is_companion_pair(locs: list[tuple[str, int]]) -> bool:
        """Return True if locs are exactly a base/secondary pair in one dir."""
        if len(locs) != 2:
            return False
        paths = [Path(loc[0]) for loc in locs]
        if paths[0].parent != paths[1].parent:
            return False
        stems = {p.stem for p in paths}
        return stems == COMPANION_STEMS

    duplicates = {
        guid: locs
        for guid, locs in seen.items()
        if len(locs) > 1 and not _is_companion_pair(locs)
    }

    if not duplicates:
        print(f"OK: {len(seen)} unique GUIDs, no duplicates.")
        return 0

    print(f"FAIL: {len(duplicates)} duplicate GUID(s) found:\n", file=sys.stderr)
    for guid in sorted(duplicates):
        print(f"  {guid}:", file=sys.stderr)
        for filepath, line_num in duplicates[guid]:
            print(f"    {filepath}:{line_num}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
