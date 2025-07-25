#!/usr/bin/env python3
"""
Script to update the nouns.py file with enhanced structure.

This script transforms the existing word dictionaries to include:
- GUID (unique identifier like N1245)
- Alternative translations (e.g., "bike" for "bicycle")
- Word frequency data from the wordfreq database
- Extensible structure for future enhancements

Configuration:
    Update the path constants below to point to your repository locations:
    - TRAKAIDO_WORDLISTS_BASE_PATH: Path to trakaido_wordlists repository
    - GREENLAND_SRC_PATH: Path to greenland/src directory

Usage:
    python update_nouns_structure.py
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
from nouns import nouns_one, nouns_two, nouns_three, nouns_four, nouns_five, common_words, common_words_two

# Add the src directory to path for wordfreq imports
sys.path.append(GREENLAND_SRC_PATH)
from wordfreq.storage.database import create_database_session, get_word_token_by_text
from wordfreq.storage.models.schema import WordToken, WordFrequency
import constants

def generate_guid(counter: int) -> str:
    """Generate a GUID in format N1245"""
    return f"N{counter:04d}"

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

def transform_word_entry(word_dict: Dict[str, str], guid_counter: int, session=None) -> Dict[str, Any]:
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
        "guid": generate_guid(guid_counter),
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

def transform_category(category_data: List[Dict[str, str]], start_counter: int, session=None) -> tuple[List[Dict[str, Any]], int, int]:
    """Transform all words in a category"""
    transformed_words = []
    counter = start_counter
    wordfreq_found_count = 0
    
    for word_dict in category_data:
        transformed_word = transform_word_entry(word_dict, counter, session)
        transformed_words.append(transformed_word)
        
        # Count words found in wordfreq database
        if transformed_word.get("_wordfreq_found", False):
            wordfreq_found_count += 1
            
        counter += 1
    
    return transformed_words, counter, wordfreq_found_count

def transform_dictionary(word_dict: Dict[str, List[Dict[str, str]]], start_counter: int, session=None) -> tuple[Dict[str, List[Dict[str, Any]]], int, int]:
    """Transform an entire dictionary (like nouns_one)"""
    transformed_dict = {}
    counter = start_counter
    total_wordfreq_found = 0
    
    for category, words in word_dict.items():
        transformed_words, counter, wordfreq_found = transform_category(words, counter, session)
        transformed_dict[category] = transformed_words
        total_wordfreq_found += wordfreq_found
    
    return transformed_dict, counter, total_wordfreq_found

def clean_entries_for_output(word_dict: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
    """Remove internal flags from entries before writing to file"""
    cleaned_dict = {}
    for category, words in word_dict.items():
        cleaned_words = []
        for word in words:
            cleaned_word = {k: v for k, v in word.items() if not k.startswith('_')}
            cleaned_words.append(cleaned_word)
        cleaned_dict[category] = cleaned_words
    return cleaned_dict

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

def create_updated_file():
    """Create the updated nouns.py file with enhanced structure"""
    
    # Create database session for wordfreq data
    print("Connecting to wordfreq database...")
    try:
        session = create_database_session()
        print("✅ Connected to wordfreq database")
    except Exception as e:
        print(f"⚠️  Warning: Could not connect to wordfreq database: {e}")
        print("Proceeding without wordfreq data...")
        session = None
    
    # Transform all dictionaries
    counter = 1
    total_wordfreq_found = 0
    
    print("Transforming nouns_one...")
    new_nouns_one, counter, wordfreq_found = transform_dictionary(nouns_one, counter, session)
    total_wordfreq_found += wordfreq_found
    
    print("Transforming nouns_two...")
    new_nouns_two, counter, wordfreq_found = transform_dictionary(nouns_two, counter, session)
    total_wordfreq_found += wordfreq_found
    
    print("Transforming nouns_three...")
    new_nouns_three, counter, wordfreq_found = transform_dictionary(nouns_three, counter, session)
    total_wordfreq_found += wordfreq_found
    
    print("Transforming nouns_four...")
    new_nouns_four, counter, wordfreq_found = transform_dictionary(nouns_four, counter, session)
    total_wordfreq_found += wordfreq_found
    
    print("Transforming nouns_five...")
    new_nouns_five, counter, wordfreq_found = transform_dictionary(nouns_five, counter, session)
    total_wordfreq_found += wordfreq_found
    
    print("Transforming common_words...")
    new_common_words, counter, wordfreq_found = transform_dictionary(common_words, counter, session)
    total_wordfreq_found += wordfreq_found
    
    print("Transforming common_words_two...")
    new_common_words_two, counter, wordfreq_found = transform_dictionary(common_words_two, counter, session)
    total_wordfreq_found += wordfreq_found
    
    total_words = counter - 1
    print(f"Total words processed: {total_words}")
    if session:
        print(f"Words found in wordfreq database: {total_wordfreq_found} ({total_wordfreq_found/total_words*100:.1f}%)")
    else:
        print("No wordfreq data included (database connection failed)")
    
    # Close database session
    if session:
        session.close()
        print("Database session closed")
    
    # Generate the new file content
    file_content = '''"""
Enhanced Lithuanian-English word lists with detailed structure.

Each word entry now includes:
- guid: Unique identifier (e.g., N0001)
- english: English word/phrase
- lithuanian: Lithuanian translation
- alternatives: Dictionary with separate lists for English and Lithuanian alternatives
  - english: List of alternative English words/phrases
  - lithuanian: List of alternative Lithuanian words/phrases
- metadata: Extensible object for future enhancements
  - difficulty_level: Can be set to indicate word difficulty
  - frequency_rank: Frequency rank from wordfreq database (combined harmonic mean rank across corpora)
  - tags: List of tags for categorization
  - notes: Any special notes about the word
"""

'''
    
    # Clean and add each dictionary to the file
    file_content += f"nouns_one = {format_python_dict(clean_entries_for_output(new_nouns_one))}\n\n"
    file_content += f"nouns_two = {format_python_dict(clean_entries_for_output(new_nouns_two))}\n\n"
    file_content += f"nouns_three = {format_python_dict(clean_entries_for_output(new_nouns_three))}\n\n"
    file_content += f"nouns_four = {format_python_dict(clean_entries_for_output(new_nouns_four))}\n\n"
    file_content += f"nouns_five = {format_python_dict(clean_entries_for_output(new_nouns_five))}\n\n"
    file_content += f"common_words = {format_python_dict(clean_entries_for_output(new_common_words))}\n\n"
    file_content += f"common_words_two = {format_python_dict(clean_entries_for_output(new_common_words_two))}\n"
    
    # Write to new file
    output_path = os.path.join(TRAKAIDO_WORDLISTS_BASE_PATH, 'lang_lt', 'nouns_enhanced.py')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(file_content)
    
    print(f"Enhanced file created: {output_path}")
    
    # Create a backup of the original
    backup_path = os.path.join(TRAKAIDO_WORDLISTS_BASE_PATH, 'lang_lt', 'nouns_original_backup.py')
    original_path = os.path.join(TRAKAIDO_WORDLISTS_BASE_PATH, 'lang_lt', 'nouns.py')
    
    with open(original_path, 'r', encoding='utf-8') as f:
        original_content = f.read()
    
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(original_content)
    
    print(f"Original file backed up to: {backup_path}")
    
    return output_path, total_words, total_wordfreq_found

def print_sample_output():
    """Print a sample of the transformed structure"""
    print("\n" + "="*60)
    print("SAMPLE OUTPUT STRUCTURE")
    print("="*60)
    
    # Create a sample database session for demonstration
    try:
        session = create_database_session()
        print("✅ Connected to wordfreq database for sample")
    except Exception as e:
        print(f"⚠️  Warning: Could not connect to wordfreq database for sample: {e}")
        session = None
    
    # Transform just one word as an example
    sample_word = {"english": "bicycle", "lithuanian": "dviratis"}
    transformed = transform_word_entry(sample_word, 1, session)
    
    print("Original structure:")
    print(format_python_dict(sample_word))
    
    print("\nNew enhanced structure:")
    # Clean the sample for display (remove internal flags)
    cleaned_sample = {k: v for k, v in transformed.items() if not k.startswith('_')}
    print(format_python_dict(cleaned_sample))
    
    # Close sample session
    if session:
        session.close()
    
    print("\n" + "="*60)

def main():
    """Main function"""
    print("Lithuanian Nouns Structure Enhancement Script")
    print("=" * 50)
    
    # Show sample output first
    print_sample_output()
    
    # Ask for confirmation
    response = input("\nDo you want to proceed with transforming all words? (y/n): ")
    if response.lower() != 'y':
        print("Operation cancelled.")
        return
    
    # Create the enhanced file
    try:
        output_path, total_words, wordfreq_found = create_updated_file()
        
        print(f"\n✅ SUCCESS!")
        print(f"Enhanced file created with {total_words} words")
        print(f"Location: {output_path}")
        print(f"Original file backed up")
        if wordfreq_found > 0:
            print(f"Wordfreq data included for {wordfreq_found} words ({wordfreq_found/total_words*100:.1f}%)")
        
        print(f"\nTo use the new structure, you can:")
        print(f"1. Review the enhanced file: {output_path}")
        print(f"2. Replace the original file when ready")
        print(f"3. Update any code that uses the word dictionaries")
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return

if __name__ == "__main__":
    main()
