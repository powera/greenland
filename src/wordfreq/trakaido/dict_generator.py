#!/usr/bin/env python3
"""
Trakaido Dictionary Generator

This script generates both structure files and dictionary files for the trakaido system
from the wordfreq database. It replaces both generate_wordlists_from_db.py and 
dictionary/generator.py with a unified approach.

Structure files: Organize words by difficulty level and subtype (e.g., nouns_one_structure.py)
Dictionary files: Individual word entries by GUID (e.g., colors_dictionary.py)

Usage:
    python dict_generator.py [--output-dir OUTPUT_DIR] [--level LEVEL] [--subtype SUBTYPE] [--type TYPE]
"""


import os
import json
import argparse
import keyword
import re
from typing import Dict, List, Any, Optional

# Configuration
GREENLAND_SRC_PATH = '/Users/powera/repo/greenland/src'
DEFAULT_OUTPUT_DIR = '/Users/powera/repo/greenland/data/trakaido_wordlists/lang_lt/generated'

import sys
sys.path.append(GREENLAND_SRC_PATH)

from wordfreq.storage.database import (
    create_database_session,
    get_lemmas_by_subtype_and_level,
)
from wordfreq.storage.models.schema import Lemma, DerivativeForm
import constants

def get_all_subtypes(session) -> List[str]:
    """Get all pos_subtypes that have lemmas with GUIDs."""
    subtypes = session.query(Lemma.pos_subtype)\
        .filter(Lemma.pos_subtype != None)\
        .filter(Lemma.guid != None)\
        .distinct()\
        .all()
    
    return [subtype[0] for subtype in subtypes if subtype[0]]

def get_lemmas_by_subtype(session, pos_subtype: str) -> List[Lemma]:
    """Get all lemmas for a specific subtype, ordered by GUID."""
    return session.query(Lemma)\
        .filter(Lemma.pos_subtype == pos_subtype)\
        .filter(Lemma.guid != None)\
        .order_by(Lemma.guid)\
        .all()

def get_english_word_for_lemma(session, lemma: Lemma) -> str:
    """Get the primary English word for a lemma."""
    # First try to get from derivative forms
    for form in lemma.derivative_forms:
        if form.word_token and form.is_base_form:
            return form.word_token.token
    
    # Fallback to any derivative form with word token
    for form in lemma.derivative_forms:
        if form.word_token:
            return form.word_token.token
    
    # Final fallback to lemma text
    return lemma.lemma_text

def get_lithuanian_word_for_lemma(session, lemma: Lemma) -> str:
    """Get the primary Lithuanian translation for a lemma."""
    # First try to get from the lemma's direct translation field
    if lemma.lithuanian_translation:
        return lemma.lithuanian_translation
    
    # Fallback to Lithuanian base forms
    for form in lemma.derivative_forms:
        if form.is_base_form and form.language_code == 'lt':
            return form.derivative_form_text
    
    # Fallback to any Lithuanian derivative form
    for form in lemma.derivative_forms:
        if form.language_code == 'lt':
            return form.derivative_form_text
    
    # Final fallback (shouldn't happen if data is properly migrated)
    return lemma.lemma_text

def get_alternatives_for_lemma(session, lemma: Lemma) -> Dict[str, List[str]]:
    """Get alternative forms for a lemma, organized by language."""
    alternatives = {'english': [], 'lithuanian': []}
    
    # Get alternative forms from DerivativeForm table
    # Alternative forms have grammatical_form starting with "alternative_"
    alt_forms = session.query(DerivativeForm)\
        .filter(DerivativeForm.lemma_id == lemma.id)\
        .filter(DerivativeForm.grammatical_form.like('alternative_%'))\
        .all()
    
    for alt_form in alt_forms:
        if alt_form.language_code == 'en' and 'english' in alternatives:
            alternatives['english'].append(alt_form.derivative_form_text)
        elif alt_form.language_code == 'lt' and 'lithuanian' in alternatives:
            alternatives['lithuanian'].append(alt_form.derivative_form_text)
        # Can extend for other languages as needed
    
    return alternatives

def get_frequency_rank_for_lemma(session, lemma: Lemma) -> Optional[int]:
    """Get the frequency rank for a lemma."""
    if lemma.frequency_rank:
        return lemma.frequency_rank
    
    # Try to get from derivative forms
    for form in lemma.derivative_forms:
        if form.word_token and form.word_token.frequency_rank:
            return form.word_token.frequency_rank
    
    return None

def lemma_to_word_dict(session, lemma: Lemma) -> Dict[str, Any]:
    """Convert a lemma to the word dictionary format used by trakaido."""
    english_word = get_english_word_for_lemma(session, lemma)
    lithuanian_word = get_lithuanian_word_for_lemma(session, lemma)
    alternatives = get_alternatives_for_lemma(session, lemma)
    frequency_rank = get_frequency_rank_for_lemma(session, lemma)
    
    # Parse tags from JSON
    tags = []
    if lemma.tags:
        try:
            tags = json.loads(lemma.tags)
        except json.JSONDecodeError:
            tags = []
    
    return {
        "guid": lemma.guid,
        "english": english_word,
        "lithuanian": lithuanian_word,
        "alternatives": alternatives,
        "metadata": {
            "difficulty_level": lemma.difficulty_level,
            "frequency_rank": frequency_rank,
            "tags": tags,
            "notes": lemma.notes or ""
        }
    }

def is_valid_python_identifier(name: str) -> bool:
    """Check if a string is a valid Python identifier (variable name)."""
    if not name:
        return False
    
    # Check if it's a valid identifier and not a Python keyword
    return name.isidentifier() and not keyword.iskeyword(name)

def validate_guid_as_variable_name(guid: str) -> bool:
    """Validate that a GUID can be used as a Python variable name."""
    if not guid:
        return False
    
    return is_valid_python_identifier(guid)

def format_python_dict(data, indent=0):
    """Format a dictionary as proper Python code."""
    if data is None:
        return "None"
    elif isinstance(data, bool):
        return "True" if data else "False"
    elif isinstance(data, str):
        return repr(data)
    elif isinstance(data, (int, float)):
        return str(data)
    elif isinstance(data, list):
        if not data:
            return "[]"
        items = []
        for item in data:
            items.append(format_python_dict(item, indent + 2))
        if len(items) == 1 and len(items[0]) < 50:
            return f"[{items[0]}]"
        else:
            indent_str = " " * (indent + 2)
            items_str = f",\n{indent_str}".join(items)
            return f"[\n{indent_str}{items_str}\n{' ' * indent}]"
    elif isinstance(data, dict):
        if not data:
            return "{}"
        items = []
        for key, value in data.items():
            key_str = repr(key)
            value_str = format_python_dict(value, indent + 2)
            items.append(f"{key_str}: {value_str}")
        
        indent_str = " " * (indent + 2)
        items_str = f",\n{indent_str}".join(items)
        return f"{{\n{indent_str}{items_str}\n{' ' * indent}}}"
    else:
        return repr(data)

def generate_structure_data(session, difficulty_level: int) -> Dict[str, List[str]]:
    """
    Generate structure data for a specific difficulty level, organized by subtype.
    Returns a dictionary mapping display names to lists of GUIDs.
    """
    level_data = {}
    
    # Get all subtypes that have words at this level
    subtypes = get_all_subtypes(session)
    
    for subtype in subtypes:
        lemmas = get_lemmas_by_subtype_and_level(
            session, 
            pos_subtype=subtype, 
            difficulty_level=difficulty_level
        )
        
        if lemmas:
            # Convert subtype name to display format
            display_subtype = subtype.replace('_', ' ').title().replace(' And ', ' + ')
            
            # Extract just the GUIDs for structure files, validating each one
            guid_list = []
            skipped_guids = 0
            
            for lemma in lemmas:
                if lemma.guid:
                    if validate_guid_as_variable_name(lemma.guid):
                        guid_list.append(lemma.guid)
                    else:
                        print(f"Warning: Skipping GUID '{lemma.guid}' in structure (not a valid Python identifier)")
                        skipped_guids += 1
            
            if guid_list:
                level_data[display_subtype] = guid_list
                if skipped_guids > 0:
                    print(f"Skipped {skipped_guids} invalid GUIDs in {display_subtype} for level {difficulty_level}")
    
    return level_data

def generate_structure_file(session, difficulty_level: int, output_dir: str) -> str:
    """
    Generate a structure file for a specific difficulty level.
    Structure files contain word objects organized by subtype, imported from dictionary files.
    """
    level_data = generate_structure_data(session, difficulty_level)
    
    if not level_data:
        print(f"No data found for difficulty level {difficulty_level}")
        return None
    
    # Generate file content
    level_names = {
        1: "one",
        2: "two", 
        3: "three",
        4: "four",
        5: "five",
        6: "six",
        7: "seven",
    }
    
    level_name = level_names.get(difficulty_level, str(difficulty_level))
    variable_name = f"words_{level_name}_structure"
    filename = f"words_{level_name}_structure.py"
    filepath = os.path.join(output_dir, "structure", filename)
    
    # Collect all subtypes that need to be imported
    subtypes_to_import = set()
    for display_subtype, guids in level_data.items():
        # Convert display name back to subtype for import
        subtype = display_subtype.lower().replace(' + ', '_and_').replace(' ', '_')
        subtypes_to_import.add(subtype)
    
    # Generate imports
    imports = []
    for subtype in sorted(subtypes_to_import):
        imports.append(f"from ..dictionary.{subtype}_dictionary import *")
    
    imports_section = '\n'.join(imports) + '\n\n' if imports else ''
    
    # Create header
    header = f'''"""
Nouns {level_name.title()} - Category Structure

This file contains the organizational structure mapping categories to word objects.
Each category contains a list of word objects imported from the dictionary files.

Structure:
- Each category has a "display_name" for pretty printing
- Each category has a "words" list containing the actual word objects
- Word objects are imported from their respective dictionary files

Format: "Category": {{
  "display_name": "Pretty Category Name",
  "words": [word_object1, word_object2, ...]
}}
"""

{imports_section}'''
    
    # Generate structured data with word objects
    structured_data = {}
    for display_subtype, guids in level_data.items():
        # Create pretty display name
        pretty_name = display_subtype.replace('_', ' ').title()
        if ' And ' in pretty_name:
            pretty_name = pretty_name.replace(' And ', ' & ')
        
        # Create word list using the actual GUID variable names
        word_list = ', '.join(guids)
        
        structured_data[display_subtype] = {
            "display_name": pretty_name,
            "words": f"[{word_list}]"  # This will be formatted as raw code
        }
    
    # Format the structure data manually to handle the raw code
    structure_lines = []
    structure_lines.append(f"{variable_name} = {{")
    
    for category, data in structured_data.items():
        structure_lines.append(f'  {repr(category)}: {{')
        structure_lines.append(f'    "display_name": {repr(data["display_name"])},')
        structure_lines.append(f'    "words": {data["words"]}')
        structure_lines.append('  },')
    
    structure_lines.append('}')
    
    content = header + '\n'.join(structure_lines) + '\n'
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    # Write file
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return filepath

def generate_dictionary_file_content(session, subtype: str) -> str:
    """Generate the complete content for a dictionary file."""
    lemmas = get_lemmas_by_subtype(session, subtype)
    
    if not lemmas:
        return f'"""\n{subtype.replace("_", " ").title()} - Dictionary Data\n\nNo entries found for this subtype.\n"""\n'
    
    # Generate header
    subtype_title = subtype.replace('_', ' ').title()
    header = f'''"""
{subtype_title} - Dictionary Data

This file contains detailed word entries for the "{subtype_title}" subtype.
Each entry is a variable assignment with the GUID as the variable name.

Entry structure:
- guid: Unique identifier (e.g., N14001)
- english: English word/phrase
- lithuanian: Lithuanian translation
- alternatives: Dictionary with separate lists for English and Lithuanian alternatives
- metadata: Extensible object with difficulty_level, frequency_rank, tags, and notes
"""

'''
    
    # Generate entries
    entries = []
    skipped_count = 0
    
    for lemma in lemmas:
        # Validate GUID as Python variable name
        if not validate_guid_as_variable_name(lemma.guid):
            print(f"Warning: Skipping lemma with invalid GUID '{lemma.guid}' (not a valid Python identifier)")
            skipped_count += 1
            continue
            
        entry_data = lemma_to_word_dict(session, lemma)
        
        # Use GUID directly as variable name since it's now validated
        variable_name = lemma.guid
        
        # Format the entry as Python code with proper escaping
        entry_code = f"""{variable_name} = {{
  'guid': {repr(entry_data['guid'])},
  'english': {repr(entry_data['english'])},
  'lithuanian': {repr(entry_data['lithuanian'])},
  'alternatives': {{
    'english': {entry_data['alternatives']['english']},
    'lithuanian': {entry_data['alternatives']['lithuanian']}
  }},
  'metadata': {{
    'difficulty_level': {entry_data['metadata']['difficulty_level']},
    'frequency_rank': {entry_data['metadata']['frequency_rank']},
    'tags': {entry_data['metadata']['tags']},
    'notes': {repr(entry_data['metadata']['notes'])}
  }}
}}"""
        entries.append(entry_code)
    
    if skipped_count > 0:
        print(f"Skipped {skipped_count} lemmas with invalid GUIDs in subtype '{subtype}'")
    
    return header + '\n\n'.join(entries) + '\n'

def generate_dictionary_file(session, subtype: str, output_dir: str) -> str:
    """Generate a dictionary file for a specific subtype."""
    content = generate_dictionary_file_content(session, subtype)
    filename = f"{subtype}_dictionary.py"
    filepath = os.path.join(output_dir, "dictionary", filename)
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return filepath

def generate_all_structure_files(session, output_dir: str) -> List[str]:
    """Generate structure files for all difficulty levels (1-5)."""
    generated_files = []
    
    for level in range(1, 8):
        filepath = generate_structure_file(session, level, output_dir)
        if filepath:
            generated_files.append(filepath)
            print(f"Generated structure file: {filepath}")
    
    return generated_files

def generate_all_dictionary_files(session, output_dir: str) -> List[str]:
    """Generate dictionary files for all subtypes that have lemmas."""
    subtypes = get_all_subtypes(session)
    generated_files = []
    
    for subtype in subtypes:
        filepath = generate_dictionary_file(session, subtype, output_dir)
        if filepath:
            generated_files.append(filepath)
            print(f"Generated dictionary file: {filepath}")
    
    return generated_files

def generate_all_files(session, output_dir: str) -> List[str]:
    """Generate all structure and dictionary files."""
    generated_files = []
    
    # Generate structure files (organized by difficulty level)
    structure_files = generate_all_structure_files(session, output_dir)
    generated_files.extend(structure_files)
    
    # Generate dictionary files (organized by subtype)
    dictionary_files = generate_all_dictionary_files(session, output_dir)
    generated_files.extend(dictionary_files)
    
    return generated_files

def main():
    """Main function for command-line usage."""
    parser = argparse.ArgumentParser(description='Generate trakaido structure and dictionary files from wordfreq database')
    parser.add_argument('--output-dir', '-o', default=DEFAULT_OUTPUT_DIR, 
                       help='Output directory for generated files')
    parser.add_argument('--level', '-l', type=int, choices=range(1, 6),
                       help='Generate structure file for specific difficulty level only (1-5)')
    parser.add_argument('--subtype', '-s', 
                       help='Generate dictionary file for specific subtype only')
    parser.add_argument('--type', '-t', choices=['structure', 'dictionary', 'both'], default='both',
                       help='Type of files to generate (default: both)')
    parser.add_argument('--db-path', help='Path to database file (optional)')
    
    args = parser.parse_args()
    
    # Create database session
    try:
        session = create_database_session(args.db_path) if args.db_path else create_database_session()
        print("✅ Connected to wordfreq database")
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        return
    
    try:
        generated_files = []
        
        if args.level and args.type in ['structure', 'both']:
            # Generate specific level structure file
            filepath = generate_structure_file(session, args.level, args.output_dir)
            if filepath:
                generated_files.append(filepath)
                print(f"Generated: {filepath}")
            else:
                print(f"No data found for level {args.level}")
        
        if args.subtype and args.type in ['dictionary', 'both']:
            # Generate specific subtype dictionary file
            filepath = generate_dictionary_file(session, args.subtype, args.output_dir)
            if filepath:
                generated_files.append(filepath)
                print(f"Generated: {filepath}")
            else:
                print(f"No data found for subtype {args.subtype}")
        
        if not args.level and not args.subtype:
            # Generate all files based on type
            if args.type == 'structure':
                generated_files = generate_all_structure_files(session, args.output_dir)
            elif args.type == 'dictionary':
                generated_files = generate_all_dictionary_files(session, args.output_dir)
            else:  # both
                generated_files = generate_all_files(session, args.output_dir)
        
        print(f"\n🎉 Generated {len(generated_files)} files in {args.output_dir}")
        
        if generated_files:
            print("\nGenerated files:")
            for filepath in generated_files:
                print(f"  - {filepath}")
    
    except Exception as e:
        print(f"❌ Generation failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()

if __name__ == "__main__":
    main()