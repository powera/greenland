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
from wordfreq.storage.models.schema import WordToken, Lemma, DerivativeForm
import constants

def get_english_word_from_lemma(session, lemma: Lemma) -> Optional[str]:
    """
    Get the primary English word for a lemma from its derivative forms.
    
    Args:
        session: Database session
        lemma: Lemma object
        
    Returns:
        English word string or None if not found
    """
    # Look for English derivative forms for this lemma
    english_forms = session.query(DerivativeForm)\
        .filter(DerivativeForm.lemma_id == lemma.id)\
        .filter(DerivativeForm.language_code == "en")\
        .filter(DerivativeForm.is_base_form == True)\
        .all()
    
    if english_forms:
        # Return the first base form
        return english_forms[0].derivative_form_text
    
    # If no base form found, look for any English derivative form
    any_english_forms = session.query(DerivativeForm)\
        .filter(DerivativeForm.lemma_id == lemma.id)\
        .filter(DerivativeForm.language_code == "en")\
        .all()
    
    if any_english_forms:
        # Return the first available form
        return any_english_forms[0].derivative_form_text
    
    # Fallback to lemma text if no derivative forms found
    return lemma.lemma_text

def export_trakaido_data(
    session, 
    difficulty_level: Optional[int] = None,
    pos_type: Optional[str] = None,
    limit: Optional[int] = None,
    include_without_guid: bool = False
) -> List[Dict[str, Any]]:
    """
    Export trakaido data from the database.
    
    Args:
        session: Database session
        difficulty_level: Filter by specific difficulty level (optional)
        pos_type: Filter by specific POS type (optional)
        limit: Limit number of results (optional)
        include_without_guid: Include lemmas without GUIDs (default: False)
        
    Returns:
        List of dictionaries with trakaido data
    """
    print("Querying database for trakaido data...")
    
    # Build the query
    query = session.query(Lemma)\
        .filter(Lemma.lithuanian_translation != None)\
        .filter(Lemma.lithuanian_translation != "")
    
    # Apply filters
    if not include_without_guid:
        query = query.filter(Lemma.guid != None)
    
    if difficulty_level is not None:
        query = query.filter(Lemma.difficulty_level == difficulty_level)
        print(f"Filtering by difficulty level: {difficulty_level}")
    
    if pos_type:
        query = query.filter(Lemma.pos_type == pos_type.lower())
        print(f"Filtering by POS type: {pos_type}")
    
    # Order by GUID for consistent output
    query = query.order_by(Lemma.guid.asc().nullslast())
    
    if limit:
        query = query.limit(limit)
        print(f"Limiting results to: {limit}")
    
    lemmas = query.all()
    print(f"Found {len(lemmas)} lemmas matching criteria")
    
    # Convert to JSON format
    export_data = []
    skipped_count = 0
    
    for lemma in lemmas:
        # Get the English word
        english_word = get_english_word_from_lemma(session, lemma)
        
        if not english_word:
            print(f"WARNING: No English word found for lemma ID {lemma.id} (GUID: {lemma.guid})")
            skipped_count += 1
            continue
        
        # Create the export entry with standardized key names
        entry = {
            "English": english_word,
            "Lithuanian": lemma.lithuanian_translation,
            "GUID": lemma.guid or "",
            "trakaido_level": lemma.difficulty_level or 1,
            "POS": lemma.pos_type or "noun",
            "subtype": lemma.pos_subtype or "other"
        }
        
        export_data.append(entry)
    
    if skipped_count > 0:
        print(f"WARNING: Skipped {skipped_count} lemmas without English words")
    
    # Sort the data by trakaido_level, then POS, then subtype, then English alphabetically
    print("Sorting export data...")
    export_data.sort(key=lambda x: (
        x.get("trakaido_level", 999),  # Sort by level first
        x.get("POS", "zzz"),           # Then by POS
        x.get("subtype", "zzz"),       # Then by subtype
        x.get("English", "").lower()   # Finally by English word alphabetically
    ))
    
    print(f"Successfully exported {len(export_data)} entries")
    return export_data

def write_json_file(data: List[Dict[str, Any]], output_path: str) -> None:
    """
    Write the export data to a JSON file with one line per entry.
    
    Args:
        data: List of dictionaries to export
        output_path: Path to write the JSON file
    """
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('[\n')
            for i, entry in enumerate(data):
                # Write each entry on a single line
                line = json.dumps(entry, ensure_ascii=False, separators=(', ', ': '))
                if i < len(data) - 1:
                    f.write(f'  {line},\n')
                else:
                    f.write(f'  {line}\n')
            f.write(']\n')
        
        print(f"✅ Successfully wrote {len(data)} entries to {output_path}")
        
        # Show some statistics
        pos_counts = {}
        level_counts = {}
        guid_count = 0
        
        for entry in data:
            pos = entry.get("POS", "unknown")
            level = entry.get("trakaido_level", "unknown")
            
            pos_counts[pos] = pos_counts.get(pos, 0) + 1
            level_counts[level] = level_counts.get(level, 0) + 1
            
            if entry.get("GUID"):
                guid_count += 1
        
        print(f"\nExport statistics:")
        print(f"Entries with GUIDs: {guid_count}/{len(data)}")
        print(f"POS distribution: {dict(sorted(pos_counts.items()))}")
        print(f"Level distribution: {dict(sorted(level_counts.items()))}")
        
    except Exception as e:
        print(f"❌ Failed to write JSON file: {e}")
        raise

def main():
    """Main export function."""
    parser = argparse.ArgumentParser(
        description="Export trakaido data from wordfreq database to JSON format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Export all data to default file
    python write_static_data.py
    
    # Export to specific file
    python write_static_data.py /path/to/output.json
    
    # Export only level 1 words
    python write_static_data.py --level 1
    
    # Export only nouns
    python write_static_data.py --pos noun
    
    # Export first 100 entries
    python write_static_data.py --limit 100
    
    # Include entries without GUIDs
    python write_static_data.py --include-no-guid
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
        help='Filter by difficulty level (1-7)'
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
    if args.level is not None and (args.level < 1 or args.level > 7):
        print(f"❌ Invalid difficulty level '{args.level}'. Valid levels: 1-7")
        return
    
    # Create database session
    try:
        session = create_database_session()
        print("✅ Connected to wordfreq database")
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        return
    
    try:
        # Export the data
        export_data = export_trakaido_data(
            session=session,
            difficulty_level=args.level,
            pos_type=args.pos,
            limit=args.limit,
            include_without_guid=args.include_no_guid
        )
        
        if not export_data:
            print("⚠️  No data found matching the specified criteria")
            return
        
        # Write to JSON file
        write_json_file(export_data, args.output_path)
        
        print(f"\n🎉 Export completed successfully!")
        
    except Exception as e:
        print(f"❌ Export failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()

if __name__ == "__main__":
    main()