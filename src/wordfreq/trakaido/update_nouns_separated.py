#!/usr/bin/env python3
"""
Script to update the nouns.py file with separated structure.

This script transforms the existing word dictionaries to create:
1. Organizational files (nouns_one_structure.py, etc.) with categories mapping to GUIDs
2. Dictionary files (nouns_one_dictionary.py, etc.) with detailed word data

Configuration:
    Update the path constants below to point to your repository locations:
    - TRAKAIDO_WORDLISTS_BASE_PATH: Path to trakaido_wordlists repository
    - GREENLAND_SRC_PATH: Path to greenland/src directory

Usage:
    python update_nouns_separated.py
"""

import re
import json
from typing import Dict, List, Any, Optional

# Configuration - Update these paths as needed
TRAKAIDO_WORDLISTS_BASE_PATH = '/Users/powera/repo/greenland/data/trakaido_wordlists'
GREENLAND_SRC_PATH = '/Users/powera/repo/greenland/src'

# Add the src directory to path for wordfreq imports
import sys
import os
sys.path.append(GREENLAND_SRC_PATH)
from wordfreq.storage.database import (
    create_database_session, 
    get_lemmas_by_category_and_level,
    get_all_categories
)
from wordfreq.storage.models.schema import Lemma, DerivativeForm
import constants

def get_english_word_for_lemma(lemma: Lemma) -> str:
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

def get_lithuanian_word_for_lemma(lemma: Lemma) -> str:
    """Get the primary Lithuanian translation for a lemma."""
    # First try to get from base forms
    for form in lemma.derivative_forms:
        if form.is_base_form and form.lithuanian_translation:
            return form.lithuanian_translation
    
    # Fallback to any form with Lithuanian translation
    for form in lemma.derivative_forms:
        if form.lithuanian_translation:
            return form.lithuanian_translation
    
    # Final fallback (shouldn't happen if data is properly migrated)
    return lemma.lemma_text

def get_alternatives_for_lemma(lemma: Lemma) -> Dict[str, List[str]]:
    """Get alternative translations for a lemma."""
    # For now, return empty alternatives
    # This can be enhanced later with actual alternative data
    return {
        "english": [],
        "lithuanian": []
    }

def lemma_to_word_dict(lemma: Lemma) -> Dict[str, Any]:
    """Convert a lemma to the word dictionary format used by trakaido."""
    english_word = get_english_word_for_lemma(lemma)
    lithuanian_word = get_lithuanian_word_for_lemma(lemma)
    alternatives = get_alternatives_for_lemma(lemma)
    
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
            "frequency_rank": lemma.frequency_rank,
            "tags": tags,
            "notes": lemma.notes or ""
        }
    }

def generate_guid(prefix: str, counter: int) -> str:
    """Generate a GUID in format N01001, C01001, etc."""
    return f"{prefix}{counter:03d}"

def get_wordfreq_data(english_word: str, session) -> Dict[str, Any]:
    """
    Get word frequency data from the wordfreq database.
    
    Args:
        english_word: The English word to look up
        session: Database session
        
    Returns:
        Dictionary containing frequency data
    """
    # Remove parenthetical clarifications for lookup
    clean_word = re.sub(r'\s*\([^)]*\)', '', english_word).strip().lower()
    
    # Try to find the word token
    word_token = get_word_token_by_text(session, clean_word)
    
    if not word_token:
        return {
            "frequency_rank": None,
            "corpus_frequencies": {},
            "found_in_db": False
        }
    
    # Get frequency data from different corpora
    corpus_frequencies = {}
    for freq in word_token.frequencies:
        corpus_frequencies[freq.corpus.name] = {
            "rank": freq.rank,
            "frequency": freq.frequency
        }
    
    return {
        "frequency_rank": word_token.frequency_rank,  # Combined harmonic mean rank
        "corpus_frequencies": corpus_frequencies,
        "found_in_db": True
    }

def extract_alternatives(english_word: str, lithuanian_word: str) -> Dict[str, List[str]]:
    """
    Extract alternative translations for both English and Lithuanian words.
    This function can be expanded to include more sophisticated logic.
    """
    # Common English alternative mappings
    english_alternative_map = {
        "bicycle": ["bike"],
        "automobile": ["car"],
        "eyeglasses": ["glasses", "spectacles"],
        "telephone": ["phone"],
        "television": ["TV"],
        "refrigerator": ["fridge"],
        "motorcycle": ["motorbike"],
        "airplane": ["plane"],
        "photograph": ["photo"],
        "automobile": ["vehicle"],
        "smartphone": ["phone", "mobile"],
        "laptop": ["notebook"],
        "computer": ["PC"],
        "fire station": ["firehouse"],
        "police officer": ["policeman", "policewoman", "cop"],
        "firefighter": ["fireman"],
        "veterinarian": ["vet"],
        "monitor (computer)": ["monitor", "screen"],
        "chicken meat": ["chicken"],
    }
    
    # Lithuanian alternatives could be added here in the future
    lithuanian_alternative_map = {
        # Example: "dviratis": ["velosipedas"]
    }
    
    # Remove parenthetical clarifications for lookup
    clean_english = re.sub(r'\s*\([^)]*\)', '', english_word).strip()
    clean_lithuanian = re.sub(r'\s*\([^)]*\)', '', lithuanian_word).strip()
    
    english_alternatives = []
    if english_word in english_alternative_map:
        english_alternatives = english_alternative_map[english_word]
    elif clean_english in english_alternative_map:
        english_alternatives = english_alternative_map[clean_english]
    
    lithuanian_alternatives = []
    if lithuanian_word in lithuanian_alternative_map:
        lithuanian_alternatives = lithuanian_alternative_map[lithuanian_word]
    elif clean_lithuanian in lithuanian_alternative_map:
        lithuanian_alternatives = lithuanian_alternative_map[clean_lithuanian]
    
    return {
        "english": english_alternatives,
        "lithuanian": lithuanian_alternatives
    }

def transform_word_entry(word_dict: Dict[str, str], guid_prefix: str, guid_counter: int, session=None) -> Dict[str, Any]:
    """Transform a single word dictionary to the new structure"""
    english = word_dict["english"]
    lithuanian = word_dict["lithuanian"]
    
    # Generate alternatives
    alternatives = extract_alternatives(english, lithuanian)
    
    # Get frequency rank if session is provided
    frequency_rank = None
    found_in_db = False
    if session:
        wordfreq_data = get_wordfreq_data(english, session)
        frequency_rank = wordfreq_data.get("frequency_rank")
        found_in_db = wordfreq_data.get("found_in_db", False)
    
    # Create new structure
    new_entry = {
        "guid": generate_guid(guid_prefix, guid_counter),
        "english": english,
        "lithuanian": lithuanian,
        "alternatives": alternatives,
        "metadata": {
            "difficulty_level": None,  # Can be set later
            "frequency_rank": frequency_rank,  # From wordfreq database
            "tags": [],               # Can be populated later
            "notes": ""               # For any special notes
        },
        "_wordfreq_found": found_in_db  # Internal flag for counting, can be removed later
    }
    
    return new_entry

def transform_category_separated(category_data: List[Dict[str, str]], guid_prefix: str, start_counter: int, session=None) -> tuple[List[Dict[str, Any]], List[str], int, int]:
    """Transform all words in a category, returning both dictionary entries and GUID list.
    
    Words are sorted by frequency rank (most frequent first) before GUID assignment.
    Words without frequency data are placed at the end.
    """
    
    # First, transform all words without assigning GUIDs to get frequency data
    temp_entries = []
    wordfreq_found_count = 0
    
    for word_dict in category_data:
        # Transform without GUID assignment first
        transformed_word = transform_word_entry(word_dict, guid_prefix, 0, session)  # Use 0 as placeholder
        temp_entries.append((word_dict, transformed_word))
        
        # Count words found in wordfreq database
        if transformed_word.get("_wordfreq_found", False):
            wordfreq_found_count += 1
    
    # Sort by frequency rank (lower rank = more frequent)
    # Words without frequency data (None) should go at the end
    def sort_key(entry_tuple):
        _, transformed_word = entry_tuple
        freq_rank = transformed_word["metadata"]["frequency_rank"]
        if freq_rank is None:
            return float('inf')  # Put words without frequency data at the end
        return freq_rank
    
    sorted_entries = sorted(temp_entries, key=sort_key)
    
    # Now assign GUIDs in frequency order and create final entries
    dictionary_entries = []
    guid_list = []
    counter = start_counter
    
    for word_dict, temp_transformed_word in sorted_entries:
        # Create the final transformed word with proper GUID
        transformed_word = transform_word_entry(word_dict, guid_prefix, counter, session)
        dictionary_entries.append(transformed_word)
        
        # Create GUID entry with English word comment
        english_word = word_dict["english"]
        guid_list.append(f'"{transformed_word["guid"]}"  # {english_word}')
        
        counter += 1
    
    return dictionary_entries, guid_list, counter, wordfreq_found_count



def format_python_dict(data, indent=0):
    """Format a dictionary as proper Python code (not JSON)"""
    if data is None:
        return "None"
    elif isinstance(data, bool):
        return "True" if data else "False"
    elif isinstance(data, str):
        # Use repr to properly escape strings
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

def format_structure_dict(structure_data: Dict[str, List[str]], indent=0) -> str:
    """Format structure dictionary with proper indentation for GUID lists"""
    if not structure_data:
        return "{}"
    
    items = []
    for category, guid_list in structure_data.items():
        category_str = repr(category)
        
        if not guid_list:
            guid_str = "[]"
        else:
            indent_str = " " * (indent + 4)
            # Handle comma placement properly with comments
            formatted_items = []
            for i, guid_item in enumerate(guid_list):
                if i < len(guid_list) - 1:  # Not the last item
                    # Add comma after the GUID but before the comment
                    if "  # " in guid_item:
                        guid_part, comment_part = guid_item.split("  # ", 1)
                        formatted_items.append(f"{guid_part},  # {comment_part}")
                    else:
                        formatted_items.append(f"{guid_item},")
                else:  # Last item, no comma
                    formatted_items.append(guid_item)
            
            guid_items = f"\n{indent_str}".join(formatted_items)
            guid_str = f"[\n{indent_str}{guid_items}\n{' ' * (indent + 2)}]"
        
        items.append(f"{category_str}: {guid_str}")
    
    indent_str = " " * (indent + 2)
    items_str = f",\n{indent_str}".join(items)
    return f"{{\n{indent_str}{items_str}\n{' ' * indent}}}"

def format_dictionary_entries(entries: List[Dict[str, Any]]) -> str:
    """Format dictionary entries as individual variable assignments"""
    lines = []
    for entry in entries:
        guid = entry["guid"]
        # Remove the internal flag before formatting
        clean_entry = {k: v for k, v in entry.items() if not k.startswith('_')}
        formatted_entry = format_python_dict(clean_entry, 0)
        lines.append(f"{guid} = {formatted_entry}")
    return "\n\n".join(lines)

def sanitize_filename(name: str) -> str:
    """Convert category name to valid filename"""
    # Replace spaces and special characters with underscores
    sanitized = re.sub(r'[^\w\s-]', '', name)  # Remove special chars except spaces and hyphens
    sanitized = re.sub(r'[-\s]+', '_', sanitized)  # Replace spaces and hyphens with underscores
    return sanitized.lower()

def create_separated_files():
    """Create the separated structure and dictionary files from database"""
    
    # Create database session for wordfreq data
    print("Connecting to wordfreq database...")
    try:
        session = create_database_session()
        print("✅ Connected to wordfreq database")
    except Exception as e:
        print(f"❌ Could not connect to wordfreq database: {e}")
        return
    
    # Create subdirectories for enhanced files
    enhanced_dir = os.path.join(TRAKAIDO_WORDLISTS_BASE_PATH, 'lang_lt', 'enhanced')
    structure_dir = os.path.join(enhanced_dir, 'structure')
    dictionary_dir = os.path.join(enhanced_dir, 'dictionary')
    
    os.makedirs(structure_dir, exist_ok=True)
    os.makedirs(dictionary_dir, exist_ok=True)
    print(f"Created directories: {structure_dir}, {dictionary_dir}")
    
    # Get all categories from database
    categories = get_all_categories(session)
    if not categories:
        print("❌ No categories found in database. Run migration script first.")
        return
    
    print(f"Found {len(categories)} categories in database")
    
    # Generate files for each difficulty level (1-5)
    level_names = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}
    
    for level_num in range(1, 6):
        level_name = level_names[level_num]
        print(f"\nProcessing difficulty level {level_num} ({level_name})...")
        
        # Get all lemmas for this difficulty level, organized by category
        level_data = {}
        level_structure = {}
        all_dictionary_entries = []
        
        for category in categories:
            lemmas = get_lemmas_by_category_and_level(
                session, 
                category=category, 
                difficulty_level=level_num
            )
            
            if lemmas:
                # Convert category name to display format
                display_category = category.replace('_', ' ').title().replace(' And ', ' + ')
                
                # Convert lemmas to word dictionaries
                word_list = []
                guid_list = []
                
                for lemma in lemmas:
                    if lemma.guid:  # Only include lemmas with GUIDs
                        word_dict = lemma_to_word_dict(lemma)
                        word_list.append(word_dict)
                        all_dictionary_entries.append(word_dict)
                        
                        # Create GUID entry with English word comment
                        english_word = get_english_word_for_lemma(lemma)
                        guid_list.append(f'"{lemma.guid}"  # {english_word}')
                
                if word_list:
                    level_data[display_category] = word_list
                    level_structure[display_category] = guid_list
                    print(f"  {display_category}: {len(word_list)} words")
        
        if not level_data:
            print(f"  No data found for level {level_num}")
            continue
        
        # Generate structure file for this level
        structure_filename = f"nouns_{level_name}_structure.py"
        structure_filepath = os.path.join(structure_dir, structure_filename)
        
        structure_header = f'''"""
Structure file for difficulty level {level_num} ({level_name}) - Generated from database

This file contains the organizational structure mapping categories to GUIDs.
Each category maps to a list of GUIDs that reference entries in the corresponding dictionary file.

Generated automatically from wordfreq database - do not edit manually.
"""

'''
        
        structure_content = f"{structure_header}nouns_{level_name} = {format_structure_dict(level_structure, 0)}\n"
        
        with open(structure_filepath, 'w', encoding='utf-8') as f:
            f.write(structure_content)
        
        print(f"  ✅ Created structure file: {structure_filepath}")
        
        # Generate dictionary file for this level
        dictionary_filename = f"nouns_{level_name}_dictionary.py"
        dictionary_filepath = os.path.join(dictionary_dir, dictionary_filename)
        
        dictionary_header = f'''"""
Dictionary file for difficulty level {level_num} ({level_name}) - Generated from database

This file contains detailed word entries with the GUID as the variable name.
Each entry includes English/Lithuanian translations, alternatives, and metadata.

Generated automatically from wordfreq database - do not edit manually.
"""

'''
        
        dictionary_content = f"{dictionary_header}{format_dictionary_entries(all_dictionary_entries)}\n"
        
        with open(dictionary_filepath, 'w', encoding='utf-8') as f:
            f.write(dictionary_content)
        
        print(f"  ✅ Created dictionary file: {dictionary_filepath}")
        print(f"  📊 Total words in level {level_num}: {len(all_dictionary_entries)}")
    
    # Generate summary statistics
    total_lemmas = session.query(Lemma).filter(Lemma.category != None).count()
    total_with_guids = session.query(Lemma).filter(Lemma.guid != None).count()
    
    print(f"\n🎉 File generation completed!")
    print(f"📊 Database statistics:")
    print(f"  Total categorized lemmas: {total_lemmas}")
    print(f"  Total lemmas with GUIDs: {total_with_guids}")
    print(f"  Categories processed: {len(categories)}")
    
    session.close()

if __name__ == "__main__":
    create_separated_files()