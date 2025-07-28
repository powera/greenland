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

# Import the existing data
import sys
import os
sys.path.append(os.path.join(TRAKAIDO_WORDLISTS_BASE_PATH, 'lang_lt'))
from .nouns import nouns_one, nouns_two, nouns_three, nouns_four, nouns_five, common_words, common_words_two

# Add the src directory to path for wordfreq imports
sys.path.append(GREENLAND_SRC_PATH)
from wordfreq.storage.database import create_database_session, get_word_token_by_text
from wordfreq.storage.models.schema import WordToken, WordFrequency
import constants

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
    """Create the separated structure and dictionary files"""
    
    # Create database session for wordfreq data
    print("Connecting to wordfreq database...")
    try:
        session = create_database_session()
        print("✅ Connected to wordfreq database")
    except Exception as e:
        print(f"⚠️  Warning: Could not connect to wordfreq database: {e}")
        print("Proceeding without wordfreq data...")
        session = None
    
    # Create subdirectories for enhanced files
    enhanced_dir = os.path.join(TRAKAIDO_WORDLISTS_BASE_PATH, 'lang_lt', 'enhanced')
    structure_dir = os.path.join(enhanced_dir, 'structure')
    dictionary_dir = os.path.join(enhanced_dir, 'dictionary')
    
    os.makedirs(structure_dir, exist_ok=True)
    os.makedirs(dictionary_dir, exist_ok=True)
    print(f"Created directories: {structure_dir}, {dictionary_dir}")
    
    # Dictionary to store all corpus data
    corpus_data = {
        "nouns_one": nouns_one,
        "nouns_two": nouns_two,
        "nouns_three": nouns_three,
        "nouns_four": nouns_four,
        "nouns_five": nouns_five,
        "common_words": common_words,
        "common_words_two": common_words_two
    }
    
    total_wordfreq_found = 0
    total_words = 0
    category_counter = 1  # Global counter for dictionary files
    
    # First pass: collect all categories and assign GUID prefixes
    all_categories = []
    for corpus_name, corpus_dict in corpus_data.items():
        for category in corpus_dict.keys():
            all_categories.append((corpus_name, category))
    
    for corpus_name, corpus_dict in corpus_data.items():
        print(f"Transforming {corpus_name}...")
        
        # Determine prefix based on corpus type
        if corpus_name.startswith('common_words'):
            base_prefix = 'C'
        else:
            base_prefix = 'N'
        
        # Transform each category separately with its own GUID sequence
        structure_data = {}
        
        for category, words in corpus_dict.items():
            # Create GUID prefix for this category (e.g., N01, N02, C01, etc.)
            guid_prefix = f"{base_prefix}{category_counter:02d}"
            
            # Transform this category (words will be sorted by frequency)
            print(f"  Processing category '{category}' with {len(words)} words...")
            dict_entries, guid_list, _, wordfreq_found = transform_category_separated(words, guid_prefix, 1, session)
            total_wordfreq_found += wordfreq_found
            total_words += len(words)
            print(f"    Found frequency data for {wordfreq_found}/{len(words)} words")
            
            # Store structure data
            structure_data[category] = guid_list
            
            # Create dictionary file for this category
            category_filename = sanitize_filename(category)
            
            dictionary_content = f'''"""
{category} - Dictionary Data

This file contains detailed word entries for the "{category}" category.
Each entry is a variable assignment with the GUID as the variable name.

Entry structure:
- guid: Unique identifier (e.g., {guid_prefix}001)
- english: English word/phrase
- lithuanian: Lithuanian translation
- alternatives: Dictionary with separate lists for English and Lithuanian alternatives
- metadata: Extensible object with difficulty_level, frequency_rank, tags, and notes
"""

{format_dictionary_entries(dict_entries)}
'''
            
            dictionary_path = os.path.join(dictionary_dir, f'{category_filename}_dictionary.py')
            with open(dictionary_path, 'w', encoding='utf-8') as f:
                f.write(dictionary_content)
            print(f"Created dictionary file: {dictionary_path}")
            
            category_counter += 1
        
        # Create structure file for this corpus
        structure_content = f'''"""
{corpus_name.replace('_', ' ').title()} - Category Structure

This file contains the organizational structure mapping categories to word GUIDs.
Each GUID corresponds to a detailed entry in the companion dictionary files.

Format: "Category": [
  "GUID",  # English word
  ...
]
"""

{corpus_name}_structure = {format_structure_dict(structure_data)}
'''
        
        structure_path = os.path.join(structure_dir, f'{corpus_name}_structure.py')
        with open(structure_path, 'w', encoding='utf-8') as f:
            f.write(structure_content)
        print(f"Created structure file: {structure_path}")
    
    print(f"\n✅ Processing complete!")
    print(f"Total words processed: {total_words}")
    print(f"Total dictionary files created: {category_counter - 1}")
    if session:
        print(f"Words found in wordfreq database: {total_wordfreq_found} ({total_wordfreq_found/total_words*100:.1f}%)")
    else:
        print("No wordfreq data included (database connection failed)")
    
    # Close database session
    if session:
        session.close()
        print("Database session closed")
    
    print(f"\nFiles created in:")
    print(f"Structure files: {structure_dir}")
    print(f"Dictionary files: {dictionary_dir}")

if __name__ == "__main__":
    create_separated_files()