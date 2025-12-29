#!/usr/bin/env python3
"""
Remove duplicate entries from old categories, keeping them only in new categories.
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

# Add src to path for imports
if str(Path(__file__).parent / "src") not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent / "src"))


def load_jsonl(file_path):
    """Load a JSONL file and return list of entries."""
    entries = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"Warning: Invalid JSON in {file_path}:{line_num}: {e}", file=sys.stderr)
    return entries


def save_jsonl(file_path, entries):
    """Save entries to a JSONL file."""
    with open(file_path, 'w', encoding='utf-8') as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')


def main():
    # Load the duplicate report
    report_path = Path('data/release_analysis_report.json')
    with open(report_path) as f:
        report = json.load(f)

    duplicates = report['duplicates']

    if not duplicates:
        print("No duplicates to remove!")
        return

    print(f"Found {len(duplicates)} duplicate concepts to remove from old categories\n")

    # Group duplicates by old file
    file_to_guids = defaultdict(set)

    for dup in duplicates:
        for old_loc in dup['old_locations']:
            file_path = old_loc['file']
            guid = old_loc['guid']
            file_to_guids[file_path].add(guid)

    # Process each file
    total_removed = 0

    for file_path, guids_to_remove in sorted(file_to_guids.items()):
        file_path = Path(file_path)

        print(f"Processing: {file_path}")
        print(f"  Removing {len(guids_to_remove)} entries: {sorted(guids_to_remove)}")

        # Load current entries
        entries = load_jsonl(file_path)
        original_count = len(entries)

        # Filter out duplicates
        filtered_entries = [
            entry for entry in entries
            if entry.get('guid') not in guids_to_remove
        ]

        removed_count = original_count - len(filtered_entries)
        total_removed += removed_count

        print(f"  Removed {removed_count} entries ({original_count} -> {len(filtered_entries)})")

        # Save updated file
        save_jsonl(file_path, filtered_entries)
        print(f"  ✓ Saved updated file\n")

    print("=" * 80)
    print(f"SUMMARY: Removed {total_removed} duplicate entries from old categories")
    print("=" * 80)

    # Show what remains in each affected file
    print("\nRemaining entries in affected files:")
    for file_path in sorted(file_to_guids.keys()):
        entries = load_jsonl(file_path)
        print(f"  {file_path}: {len(entries)} entries")


if __name__ == '__main__':
    main()
