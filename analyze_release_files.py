#!/usr/bin/env python3
"""
Analyze data/release files for duplicates and dummy definitions.
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
import re

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


def is_dummy_definition(entry):
    """
    Check if a word has a dummy definition.
    Examples:
    - "happy" as (adjective: happy)
    - Lithuanian word appearing in the definition
    """
    concept_label = entry.get('concept_label', '').strip().lower()
    concept_definition = entry.get('concept_definition', '')

    if not concept_definition or not isinstance(concept_definition, str):
        return None

    defn_lower = concept_definition.strip().lower()

    dummy_cases = []

    # Case 1: Definition is just the POS + concept_label
    # e.g., "adjective: happy" for concept_label "happy"
    if concept_label and concept_label in defn_lower:
        # Check if it's just a simple repetition
        simple_patterns = [
            f"adjective: {concept_label}",
            f"noun: {concept_label}",
            f"verb: {concept_label}",
            f"adverb: {concept_label}",
            f"{concept_label}",
        ]
        for pattern in simple_patterns:
            if defn_lower == pattern or defn_lower == pattern + '.':
                dummy_cases.append({
                    'reason': f'Definition is just POS + concept: "{concept_definition}"',
                    'definition': concept_definition
                })
                break

    # Case 2: Definition contains "Lithuanian:" or other language marker
    if re.search(r'\b(lithuanian|latvian|polish|german|french)\s*:', defn_lower):
        dummy_cases.append({
            'reason': f'Definition contains language marker: "{concept_definition}"',
            'definition': concept_definition
        })

    return dummy_cases if dummy_cases else None


def main():
    # Load category migrations
    migrations_path = Path('data/category_migrations.json')
    with open(migrations_path) as f:
        migrations = json.load(f)

    category_splits = migrations.get('category_splits', {})

    # Map old category names to new ones (handle naming differences)
    category_mapping = {
        'food_drink': ['food', 'beverage'],
        'human': ['occupation', 'family_relation'],  # human still exists
        'tool_machine': ['vehicle'],  # tool_machine still exists
        'small_movable_object': ['furniture'],  # small_movable_object still exists
    }

    # Also add quality -> size split for adjectives
    category_mapping['quality'] = ['size']  # quality still exists

    # Scan all JSONL files
    base_path = Path('data/release/lemmas')
    all_files = list(base_path.glob('**/base.jsonl'))

    print(f"Found {len(all_files)} JSONL files\n")

    # Build index of lemma -> categories
    lemma_to_categories = defaultdict(list)
    lemma_to_entries = defaultdict(list)

    for file_path in all_files:
        # Extract category from path: e.g., nouns/food_drink
        parts = file_path.relative_to(base_path).parts
        if len(parts) >= 3:
            pos = parts[0]  # nouns, verbs, adjectives, etc.
            category = parts[1]  # food_drink, human, etc.

            entries = load_jsonl(file_path)
            for entry in entries:
                concept_label = entry.get('concept_label', '').strip().lower()
                guid = entry.get('guid', '')

                lemma_to_categories[concept_label].append({
                    'pos': pos,
                    'category': category,
                    'file': str(file_path),
                    'guid': guid,
                    'concept': concept_label
                })
                lemma_to_entries[(concept_label, str(file_path))].append(entry)

    # Find duplicates based on category migrations
    print("=" * 80)
    print("DUPLICATE ANALYSIS")
    print("=" * 80)

    duplicates_found = []

    for old_category, new_categories in category_mapping.items():
        print(f"\n### Checking migration: {old_category} -> {new_categories}")

        # Find lemmas that appear in both old and new categories
        for lemma, locations in lemma_to_categories.items():
            old_locs = [loc for loc in locations if loc['category'] == old_category]
            new_locs = [loc for loc in locations if loc['category'] in new_categories]

            if old_locs and new_locs:
                print(f"\n  Duplicate: '{lemma}'")
                print(f"    In old category ({old_category}):")
                for loc in old_locs:
                    print(f"      - {loc['file']} (GUID: {loc['guid']})")
                print(f"    In new categories:")
                for loc in new_locs:
                    print(f"      - {loc['category']}: {loc['file']} (GUID: {loc['guid']})")

                duplicates_found.append({
                    'lemma': lemma,
                    'old_category': old_category,
                    'old_locations': old_locs,
                    'new_locations': new_locs
                })

    if not duplicates_found:
        print("\n✓ No duplicates found across migrated categories")
    else:
        print(f"\n! Found {len(duplicates_found)} lemmas with duplicates")

    # Find dummy definitions
    print("\n" + "=" * 80)
    print("DUMMY DEFINITION ANALYSIS")
    print("=" * 80)

    dummy_definitions = []

    for file_path in all_files:
        entries = load_jsonl(file_path)
        for entry in entries:
            dummy_cases = is_dummy_definition(entry)
            if dummy_cases:
                concept_label = entry.get('concept_label', '')
                guid = entry.get('guid', '')

                dummy_definitions.append({
                    'concept_label': concept_label,
                    'guid': guid,
                    'file': str(file_path),
                    'cases': dummy_cases,
                    'entry': entry
                })

    if dummy_definitions:
        print(f"\nFound {len(dummy_definitions)} words with dummy definitions:\n")

        for item in dummy_definitions[:50]:  # Show first 50
            print(f"  '{item['concept_label']}' (GUID: {item['guid']})")
            print(f"    File: {item['file']}")
            for case in item['cases']:
                print(f"    {case['reason']}")
            print()

        if len(dummy_definitions) > 50:
            print(f"  ... and {len(dummy_definitions) - 50} more")
    else:
        print("\n✓ No dummy definitions found")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total JSONL files analyzed: {len(all_files)}")
    print(f"Unique lemmas found: {len(lemma_to_categories)}")
    print(f"Duplicates across migrated categories: {len(duplicates_found)}")
    print(f"Words with dummy definitions: {len(dummy_definitions)}")

    # Save detailed report
    report_path = Path('data/release_analysis_report.json')
    report = {
        'duplicates': duplicates_found,
        'dummy_definitions': [
            {
                'concept_label': item['concept_label'],
                'guid': item['guid'],
                'file': item['file'],
                'cases': item['cases']
            }
            for item in dummy_definitions
        ]
    }

    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nDetailed report saved to: {report_path}")


if __name__ == '__main__':
    main()
