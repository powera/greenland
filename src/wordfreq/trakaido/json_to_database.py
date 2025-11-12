#!/usr/bin/env python3
"""
Migration script to populate the wordfreq database with trakaido data from JSON export.

This script:
1. Reads trakaido data from nouns.json (exported from SQLite database)
2. Finds or creates corresponding lemmas in the wordfreq database
3. Sets Lithuanian translations on lemmas (using the new translation fields)
4. Creates language-specific derivative forms for English words
5. Assigns or updates GUIDs (auto-generates if not provided) and difficulty levels
6. Updates frequency ranks from the database

Required fields: English, Lithuanian, trakaido_level, POS, subtype
Optional fields: GUID (will be auto-generated if not provided)

Expected JSON format:
[
    {
        "English": "word",
        "Lithuanian": "žodis", 
        "trakaido_level": 1,
        "POS": "noun",
        "subtype": "food_drink",
        "GUID": "some-guid-string"  // Optional - will be auto-generated if not provided
    },
    ...
]

Usage:
    python json_to_database.py [path_to_nouns.json] [--no-update-difficulty]
    
    Options:
        path_to_nouns.json: Path to JSON file (optional, defaults to nouns.json in same directory)
        --no-update-difficulty: Don't update difficulty levels on existing lemmas (default: update them)
"""

import sys
import os
import json
import re
import argparse
from typing import Dict, List, Any, Optional

# Configuration - Update these paths as needed
GREENLAND_SRC_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
DEFAULT_JSON_PATH = os.path.join(os.path.dirname(__file__), 'nouns.json')

# Add paths for imports
sys.path.append(GREENLAND_SRC_PATH)
from wordfreq.storage.database import (
    create_database_session, 
    get_word_token_by_text,
    add_lemma,
    add_derivative_form,
    generate_guid,
    update_lemma_translation,
    add_alternative_form
)
from wordfreq.storage.models.schema import WordToken, Lemma, DerivativeForm
import constants

english_alternative_map = {
    "bicycle": ["bike"],
    "car": ["automobile"],
    "eyeglasses": ["glasses", "spectacles"],
    "telephone": ["phone"],
    "television": ["TV"],
    "refrigerator": ["fridge"],
    "motorcycle": ["motorbike"],
    "airplane": ["plane"],
    "photograph": ["photo"],
    "smartphone": ["phone", "mobile"],
    "laptop": ["notebook"],
    "computer": ["PC"],
    "fire station": ["firehouse"],
    "police officer": ["policeman", "policewoman", "cop"],
    "firefighter": ["fireman"],
    "veterinarian": ["vet"],
    "monitor (computer)": ["screen"],
    "chicken meat": ["chicken"],
}

def clean_english_word(english_word: str) -> tuple[str, bool]:
    """
    Normalize English word while preserving parenthetical disambiguation.

    This function does NOT strip parentheticals - those are needed for disambiguation!
    It only normalizes whitespace.

    Examples:
        "orange (fruit)" -> ("orange (fruit)", True)
        "cousin (male)" -> ("cousin (male)", True)
        "  mouse  " -> ("mouse", False)
        "simple" -> ("simple", False)

    Args:
        english_word: The English word potentially containing parenthetical info

    Returns:
        tuple: (normalized_word, has_parentheses) where has_parentheses indicates if parentheses were found
    """
    # Check if parenthetical information exists
    has_parentheses = bool(re.search(r'\s*\([^)]+\)', english_word))

    # Just normalize whitespace, DO NOT strip parentheticals
    normalized = ' '.join(english_word.split())

    return normalized, has_parentheses


def load_trakaido_json(json_path: str) -> List[Dict[str, Any]]:
    """
    Load trakaido data from JSON file.
    
    Args:
        json_path: Path to the JSON file containing trakaido data
        
    Returns:
        List of dictionaries with English, Lithuanian, GUID, and trakaido level data
        
    Raises:
        FileNotFoundError: If the JSON file doesn't exist
        json.JSONDecodeError: If the JSON file is malformed
        KeyError: If required fields are missing from the JSON data
    """
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"JSON file not found: {json_path}")
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f"Invalid JSON in {json_path}: {e}")
    
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON to contain a list, got {type(data)}")
    
    # Validate that each entry has the required fields
    required_fields = ["English", "Lithuanian", "trakaido_level", "POS", "subtype"]
    optional_fields = ["GUID"]  # GUID is optional - will be auto-generated if not provided
    
    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValueError(f"Entry {i} is not a dictionary: {entry}")
        
        missing_fields = [field for field in required_fields if field not in entry]
        if missing_fields:
            raise KeyError(f"Entry {i} missing required fields: {missing_fields}")
        
        # Validate POS type (now required)
        pos_type = entry["POS"].lower()
        valid_pos_types = {
            "noun", "verb", "adjective", "adverb", "pronoun", 
            "preposition", "conjunction", "interjection", "determiner",
            "article", "numeral", "auxiliary", "modal"
        }
        if pos_type not in valid_pos_types:
            raise ValueError(f"Entry {i} has invalid POS type '{entry['POS']}'. Valid types: {', '.join(sorted(valid_pos_types))}")
    
    print(f"✅ Loaded {len(data)} entries from {json_path}")
    return data


def get_pos_and_subtype_for_category(display_category_name: str) -> tuple[str, Optional[str]]:
    """
    Determine the part of speech and subtype for a given display category.
    
    Args:
        display_category_name: The display name from nouns.py (e.g., "Food + Drink")
    
    Returns:
        tuple: (pos_type, pos_subtype) where pos_subtype can be None
    """
    # Direct mapping from display names to (pos_type, pos_subtype)
    category_mapping = {
        # Food and consumables
        "Food + Drink": ("noun", "food_drink"),
        "Additional Foods": ("noun", "food_drink"),
        
        # Living things
        "Animals": ("noun", "animal"),
        "Plants": ("noun", "plant"),
        
        # Physical objects
        "Clothing": ("noun", "clothing_accessory"),
        "Small Physical Objects": ("noun", "small_movable_object"),
        "Buildings": ("noun", "building_structure"),
        "Transportation": ("noun", "tool_machine"),
        "Materials": ("noun", "material_substance"),
        "Technology": ("noun", "tool_machine"),
        
        # Body and health
        "Body Parts": ("noun", "body_part"),
        
        # People and relationships
        "Occupations": ("noun", "human"),
        "Family & Relationships": ("noun", "human"),
        "People & Relationships": ("noun", "human"),
        "Nationalities": ("noun", "nationality"),
        
        # Places and geography
        "Countries": ("noun", "place_name"),
        "Cities": ("noun", "place_name"),
        "Geographic Features": ("noun", "natural_feature"),
        "Places & Direction": ("noun", "place_name"),
        
        # Time and temporal
        "Days of the Week": ("noun", "temporal_name"),
        "Months of the Year": ("noun", "temporal_name"),
        "Time & Life": ("noun", "time_period"),
        
        # Abstract concepts
        "Emotions": ("noun", "emotion_feeling"),
        "Abstract Concepts": ("noun", "concept_idea"),
        "Hobbies": ("noun", "concept_idea"),
        "Social & Political": ("noun", "concept_idea"),
        "Thinking & Communication": ("noun", "concept_idea"),
        
        # Measurements and quantities
        "Units of Measurement": ("noun", "unit_of_measurement"),
        "Numbers": ("adjective", "definite_quantity"),
        
        # Descriptive qualities
        "Colors": ("adjective", "color"),
        "Shapes": ("adjective", "shape"),
        "Qualitative Adjectives": ("adjective", "quality"),
        "Descriptive Words": ("adjective", "quality"),
        "Personality": ("adjective", "quality"),
        
        # Weather and nature
        "Weather": ("noun", "natural_feature"),
        
        # Grammar categories
        "Grammar - Connectors": ("conjunction", "other"),
        "Grammar - Adverbs of Time and Place": ("adverb", "location"),
        "Grammar - Adverbs of Manner": ("adverb", "style"),
        "Question Words": ("pronoun", "other"),
        
        # Proper nouns
        "Common Proper Nouns": ("noun", "personal_name"),
    }
    
    pos_type, pos_subtype = category_mapping.get(display_category_name, ("noun", "other"))
    
    # Log if category mapping was not found
    if display_category_name not in category_mapping:
        print(f"WARNING: No category mapping found for '{display_category_name}', using default (noun, other)")
    
    # Convert generic "other" to POS-specific other for GUID generation
    if pos_subtype == "other":
        pos_subtype = f"{pos_type}_other"
    
    return pos_type, pos_subtype



def find_or_create_lemma(session, english_word: str, lithuanian_word: str, difficulty_level: int, existing_guid: Optional[str] = None, pos_type: Optional[str] = None, pos_subtype: Optional[str] = None, update_difficulty: bool = True) -> Optional[Lemma]:
    """
    Find an existing lemma or create a new one for the given English/Lithuanian pair.
    
    Args:
        session: Database session
        english_word: English word (may contain parenthetical info)
        lithuanian_word: Lithuanian translation
        difficulty_level: Difficulty level to assign (1-5)
        existing_guid: GUID from the original trakaido database (optional)
        pos_type: Part of speech (noun, verb, adjective, etc.) (optional)
        pos_subtype: POS subtype (food_drink, physical_action, etc.) (optional)
        update_difficulty: Whether to update difficulty level on existing lemmas (default: True)
        
    Returns:
        Lemma object or None if creation failed
    """
    # Normalize the English word (preserves parentheticals for disambiguation)
    # DO NOT lowercase - proper nouns like "Christmas" and "North America" need capitalization
    clean_english, has_parentheses = clean_english_word(english_word)
    
    # Use provided POS or default to noun
    if not pos_type:
        pos_type = "noun"
    else:
        pos_type = pos_type.lower()
    
    if not pos_subtype:
        pos_subtype = "other"
    
    # Step 1: Look for existing lemma with matching Lithuanian translation and lemma text
    # This finds lemmas regardless of whether they have word tokens or derivative forms
    existing_lemma = session.query(Lemma)\
        .filter(Lemma.lemma_text == clean_english)\
        .filter(Lemma.lithuanian_translation == lithuanian_word)\
        .first()
    
    if existing_lemma:
        # Update difficulty level if requested and different
        if update_difficulty and existing_lemma.difficulty_level != difficulty_level:
            old_difficulty = existing_lemma.difficulty_level
            existing_lemma.difficulty_level = difficulty_level
            session.commit()
            print(f"    Updated difficulty level for '{english_word}' from {old_difficulty} to {difficulty_level}")
        
        # Update notes if parenthetical info exists and lemma doesn't already have notes
        if notes and not existing_lemma.notes:
            existing_lemma.notes = notes
            session.commit()
        
        return existing_lemma
    
    # Step 2: Check if we have a word token for frequency data
    word_token = get_word_token_by_text(session, clean_english, "en")
    
    # Step 3: Create new lemma
    try:
        lemma = add_lemma(
            session=session,
            lemma_text=clean_english,
            definition_text=f"Lithuanian: {lithuanian_word}",
            pos_type=pos_type,
            pos_subtype=pos_subtype,
            difficulty_level=difficulty_level,
            frequency_rank=word_token.frequency_rank if word_token else None,
            lithuanian_translation=lithuanian_word,
            notes=notes,
            auto_generate_guid=not existing_guid  # Don't auto-generate if we have an existing GUID
        )
        
        # Set the existing GUID if provided
        if existing_guid:
            lemma.guid = existing_guid
            session.commit()
        
        # Add English derivative form
        add_derivative_form(
            session=session,
            lemma=lemma,
            derivative_form_text=clean_english,
            language_code="en",
            grammatical_form="singular" if pos_type == "noun" else "base_form",
            word_token=word_token,  # Will be None if no word token exists
            is_base_form=True
        )
        
        if word_token:
            print(f"Created lemma with word token for: {english_word}")
        else:
            print(f"Created lemma without word token for: {english_word}")
        
        return lemma
        
    except Exception as e:
        print(f"Error creating lemma for {english_word}: {e}")
        return None

def create_alternatives_for_lemma(session, lemma: Lemma, english_word: str) -> int:
    """
    Create alternative forms for a lemma based on the english_alternative_map.
    
    Args:
        session: Database session
        lemma: The lemma to create alternatives for
        english_word: The original English word (cleaned)
        
    Returns:
        int: Number of alternatives created
    """
    alternatives_created = 0
    
    # Check if this word has alternatives defined
    if english_word in english_alternative_map:
        alternatives = english_alternative_map[english_word]
        
        for alternative in alternatives:
            # Determine the grammatical form based on the alternative
            if alternative in ["TV", "PC"]:
                grammatical_form = "abbreviation"
                explanation = f"Abbreviation for {english_word}"
            elif alternative == "spectacles":
                grammatical_form = "archaic"
                explanation = f"Archaic term for {english_word}"
            else:
                grammatical_form = "informal"
                explanation = f"Informal term for {english_word}"
            
            try:
                # Try to find the word token for the alternative
                alternative_word_token = get_word_token_by_text(session, alternative, "en")
                
                # Create the alternative form
                add_alternative_form(
                    session=session,
                    lemma=lemma,
                    alternative_text=alternative,
                    language_code="en",
                    alternative_type=grammatical_form,
                    explanation=explanation,
                    word_token=alternative_word_token
                )
                
                alternatives_created += 1
                freq_info = f", freq_rank: {alternative_word_token.frequency_rank}" if alternative_word_token and alternative_word_token.frequency_rank else ""
                print(f"      ➕ Added alternative: {alternative} ({grammatical_form}{freq_info})")
                
            except Exception as e:
                print(f"      ❌ Failed to create alternative '{alternative}' for {english_word}: {e}")
    
    return alternatives_created


def migrate_json_data(session, trakaido_data: List[Dict[str, Any]], update_difficulty: bool = True, verbose: bool = True):
    """
    Migrate data from JSON export to the database.

    Args:
        session: Database session
        trakaido_data: List of dictionaries with English, Lithuanian, trakaido level, POS, and subtype data (GUID is optional)
        update_difficulty: Whether to update difficulty level on existing lemmas (default: True)
        verbose: Whether to print detailed progress messages (default: True)

    Returns:
        tuple: (successful_migrations, total_words) counts
    """
    if verbose:
        print(f"\nMigrating {len(trakaido_data)} entries from JSON data...")

    total_words = len(trakaido_data)
    successful_migrations = 0

    for i, entry in enumerate(trakaido_data):
        english_word = entry["English"]
        lithuanian_word = entry["Lithuanian"]
        existing_guid = entry.get("GUID")  # Optional - will be auto-generated if None
        difficulty_level = entry["trakaido_level"]  # Now required
        pos_type = entry["POS"]  # Now required
        pos_subtype = entry["subtype"]  # Now required

        # Find or create lemma
        lemma = find_or_create_lemma(
            session=session,
            english_word=english_word,
            lithuanian_word=lithuanian_word,
            difficulty_level=difficulty_level,
            existing_guid=existing_guid,
            pos_type=pos_type,
            pos_subtype=pos_subtype,
            update_difficulty=update_difficulty
        )

        if lemma:
            successful_migrations += 1
            if verbose:
                freq_info = f", freq_rank: {lemma.frequency_rank}" if lemma.frequency_rank else ""
                notes_info = f", notes: {lemma.notes}" if lemma.notes else ""
                pos_info = f", POS: {lemma.pos_type}/{lemma.pos_subtype}" if lemma.pos_subtype else f", POS: {lemma.pos_type}"
                print(f"    ✅ {english_word} -> {lithuanian_word} (GUID: {lemma.guid}{pos_info}{freq_info}{notes_info})")

            # Create alternatives for this lemma if they exist
            clean_english, _ = clean_english_word(english_word)
            alternatives_created = create_alternatives_for_lemma(session, lemma, clean_english)

        else:
            if verbose:
                print(f"    ❌ Failed to create lemma for: {english_word}")

        # Progress indicator for large datasets
        if verbose and (i + 1) % 100 == 0:
            print(f"  Progress: {i + 1}/{total_words} entries processed...")

    if verbose:
        print(f"  Completed migration: {successful_migrations}/{total_words} words migrated")
    return successful_migrations, total_words

def main():
    """Main migration function."""
    parser = argparse.ArgumentParser(
        description="Migrate trakaido data from JSON export to wordfreq database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python json_to_database.py                                    # Use default JSON file, update difficulty levels
  python json_to_database.py /path/to/nouns.json               # Use custom JSON file, update difficulty levels
  python json_to_database.py --no-update-difficulty            # Don't update existing difficulty levels
  python json_to_database.py /path/to/nouns.json --no-update-difficulty  # Custom file, no difficulty updates
        """
    )
    
    parser.add_argument(
        'json_path',
        nargs='?',
        default=DEFAULT_JSON_PATH,
        help=f'Path to JSON file containing trakaido data (default: {DEFAULT_JSON_PATH})'
    )
    
    parser.add_argument(
        '--no-update-difficulty',
        action='store_true',
        help='Do not update difficulty levels on existing lemmas (default: update difficulty levels)'
    )
    
    args = parser.parse_args()
    
    print("Starting migration of trakaido data from JSON export to wordfreq database...")
    print(f"Using JSON file: {args.json_path}")
    print(f"Update difficulty levels: {'No' if args.no_update_difficulty else 'Yes'}")
    
    # Load trakaido data from JSON
    try:
        trakaido_data = load_trakaido_json(args.json_path)
    except Exception as e:
        print(f"❌ Failed to load JSON data: {e}")
        return
    
    # Create database session
    try:
        session = create_database_session()
        print("✅ Connected to wordfreq database")
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        return
    
    try:
        # Migrate the JSON data
        update_difficulty = not args.no_update_difficulty
        successful, total = migrate_json_data(session, trakaido_data, update_difficulty)
        
        print(f"\n🎉 Migration completed!")
        print(f"Total words processed: {total}")
        print(f"Successfully migrated: {successful}")
        print(f"Failed migrations: {total - successful}")
        
        # Commit all changes to the database
        session.commit()
        print("✅ Changes committed to database")
        
        # Show some statistics
        print(f"\nDatabase statistics after migration:")
        lemmas_with_subtypes = session.query(Lemma).filter(Lemma.pos_subtype != None).count()
        lemmas_with_guids = session.query(Lemma).filter(Lemma.guid != None).count()
        lemmas_with_lithuanian = session.query(Lemma).filter(Lemma.lithuanian_translation != None).count()
        lemmas_with_difficulty = session.query(Lemma).filter(Lemma.difficulty_level != None).count()
        english_derivative_forms = session.query(DerivativeForm).filter(DerivativeForm.language_code == "en").count()
        alternative_forms = session.query(DerivativeForm).filter(
            DerivativeForm.language_code == "en",
            DerivativeForm.grammatical_form.like("alternative_%")
        ).count()
        print(f"Lemmas with subtypes: {lemmas_with_subtypes}")
        print(f"Lemmas with GUIDs: {lemmas_with_guids}")
        print(f"Lemmas with Lithuanian translations: {lemmas_with_lithuanian}")
        print(f"Lemmas with difficulty levels: {lemmas_with_difficulty}")
        print(f"English derivative forms: {english_derivative_forms}")
        print(f"Alternative forms created: {alternative_forms}")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    main()