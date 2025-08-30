#!/usr/bin/env python3
"""
Export script to write trakaido data from the wordfreq database to JSON format.

This script:
1. Queries the wordfreq database for lemmas with Lithuanian translations
2. Extracts English words from derivative forms
3. Exports data in the format expected by migrate_static_data.py
4. Optionally filters by difficulty level, POS type, or other criteria

Expected output JSON format:
[
    {
        "English": "word",
        "Lithuanian": "žodis", 
        "GUID": "some-guid-string",
        "trakaido_level": 1,
        "POS": "noun",
        "subtype": "food_drink"
    },
    ...
]

Usage:
    python write_static_data.py [output_path.json] [--level LEVEL] [--pos POS] [--limit LIMIT]
"""

import sys
import os
import json
import argparse
from typing import Dict, List, Any, Optional

# Configuration - Update these paths as needed
GREENLAND_SRC_PATH = '/Users/powera/repo/greenland/src'
DEFAULT_OUTPUT_PATH = '/Users/powera/repo/greenland/src/wordfreq/trakaido/exported_nouns.json'

# Add paths for imports
sys.path.append(GREENLAND_SRC_PATH)
from wordfreq.storage.database import create_database_session
from wordfreq.trakaido.export_utils import TrakaideExporter
import constants

def main():
    """Main export function."""
    parser = argparse.ArgumentParser(
        description="Export trakaido data from wordfreq database to JSON format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Export all data to default file
    python database_to_json.py
    
    # Export to specific file
    python database_to_json.py /path/to/output.json
    
    # Export only level 1 words
    python database_to_json.py --level 1
    
    # Export only nouns
    python database_to_json.py --pos noun
    
    # Export first 100 entries
    python database_to_json.py --limit 100
    
    # Include entries without GUIDs
    python database_to_json.py --include-no-guid
        """
    )
    
    parser.add_argument(
        'output_path',
        nargs='?',
        default=DEFAULT_OUTPUT_PATH,
        help=f'Output JSON file path (default: {DEFAULT_OUTPUT_PATH})'
    )
    
    parser.add_argument(
        '--level',
        type=int,
        help='Filter by difficulty level (1-20)'
    )
    
    parser.add_argument(
        '--pos',
        type=str,
        help='Filter by part of speech (noun, verb, adjective, etc.)'
    )
    
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of results'
    )
    
    parser.add_argument(
        '--include-no-guid',
        action='store_true',
        help='Include lemmas without GUIDs (default: only include lemmas with GUIDs)'
    )
    
    parser.add_argument(
        '--include-unverified',
        action='store_true',
        help='Include unverified entries (default: only verified entries)'
    )
    
    args = parser.parse_args()
    
    print("Starting export of trakaido data from wordfreq database...")
    print(f"Output file: {args.output_path}")
    
    # Validate POS type if provided
    if args.pos:
        valid_pos_types = {
            "noun", "verb", "adjective", "adverb", "pronoun", 
            "preposition", "conjunction", "interjection", "determiner",
            "article", "numeral", "auxiliary", "modal"
        }
        if args.pos.lower() not in valid_pos_types:
            print(f"❌ Invalid POS type '{args.pos}'. Valid types: {', '.join(sorted(valid_pos_types))}")
            return
    
    # Validate difficulty level if provided
    if args.level is not None and (args.level < 1 or args.level > 20):
        print(f"❌ Invalid difficulty level '{args.level}'. Valid levels: 1-20")
        return
    
    # Create exporter and export the data
    try:
        exporter = TrakaideExporter()
        
        success, stats = exporter.export_to_json(
            output_path=args.output_path,
            difficulty_level=args.level,
            pos_type=args.pos,
            limit=args.limit,
            include_without_guid=args.include_no_guid,
            include_unverified=args.include_unverified,
            pretty_print=True
        )
        
        if success:
            print(f"\n🎉 Export completed successfully!")
            if stats:
                print(f"Exported {stats.total_entries} entries")
                print(f"Entries with GUIDs: {stats.entries_with_guids}")
        else:
            print("⚠️  No data found matching the specified criteria")
        
    except Exception as e:
        print(f"❌ Export failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()