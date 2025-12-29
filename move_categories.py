#!/usr/bin/env python3
"""
Move entries between categories.
"""

import json
import sys
from pathlib import Path

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


def move_entries(source_file, dest_file, concept_labels, new_pos_subtype):
    """
    Move entries with specified concept labels from source to destination.
    Updates pos_subtype to match the new category.
    """
    source_path = Path(source_file)
    dest_path = Path(dest_file)

    # Load both files
    source_entries = load_jsonl(source_path)
    dest_entries = load_jsonl(dest_path) if dest_path.exists() else []

    # Find entries to move
    to_move = []
    to_keep = []

    for entry in source_entries:
        concept = entry.get('concept_label', '').strip()
        if concept in concept_labels:
            # Update pos_subtype to match new category
            entry['pos_subtype'] = new_pos_subtype
            to_move.append(entry)
        else:
            to_keep.append(entry)

    if not to_move:
        print(f"  No entries found to move from {source_file}")
        return 0

    # Add to destination
    dest_entries.extend(to_move)

    # Sort destination by GUID for consistency
    dest_entries.sort(key=lambda x: x.get('guid', ''))

    # Save both files
    save_jsonl(source_path, to_keep)
    save_jsonl(dest_path, dest_entries)

    print(f"  Moved {len(to_move)} entries: {', '.join(sorted(concept_labels))}")
    print(f"  {source_file}: {len(source_entries)} → {len(to_keep)} entries")
    print(f"  {dest_file}: {len(dest_entries) - len(to_move)} → {len(dest_entries)} entries")

    return len(to_move)


def main():
    print("=" * 80)
    print("MOVING ENTRIES BETWEEN CATEGORIES")
    print("=" * 80)

    total_moved = 0

    # Move vehicles from tool_machine to vehicle
    print("\n### Moving vehicles from tool_machine to vehicle")
    vehicles = [
        'airplane',
        'bicycle',
        'boat',
        'ship',
        'taxi',
        'truck',
        'motorcycle'
    ]

    moved = move_entries(
        'data/release/lemmas/nouns/tool_machine/base.jsonl',
        'data/release/lemmas/nouns/vehicle/base.jsonl',
        vehicles,
        'vehicle'
    )
    total_moved += moved

    # Move all remaining food_drink to food
    print("\n### Moving all food_drink entries to food")

    # Get all concept labels from food_drink
    food_drink_path = Path('data/release/lemmas/nouns/food_drink/base.jsonl')
    food_drink_entries = load_jsonl(food_drink_path)
    all_food = [entry.get('concept_label', '').strip() for entry in food_drink_entries]

    if all_food:
        moved = move_entries(
            'data/release/lemmas/nouns/food_drink/base.jsonl',
            'data/release/lemmas/nouns/food/base.jsonl',
            all_food,
            'food'
        )
        total_moved += moved

    print("\n" + "=" * 80)
    print(f"SUMMARY: Moved {total_moved} total entries")
    print("=" * 80)


if __name__ == '__main__':
    main()
