#!/usr/bin/env python3
"""
Migration script to populate the wordfreq database with trakaido data from JSON export.

This script:
1. Reads trakaido data from nouns.json (exported from SQLite database)
2. Finds or creates corresponding lemmas in the wordfreq database
3. Sets Lithuanian translations on lemmas (using the new translation fields)
4. Creates language-specific derivative forms for English words
5. Assigns or updates GUIDs and difficulty levels
6. Updates frequency ranks from the database

Expected JSON format:
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
GREENLAND_SRC_PATH = '/Users/powera/repo/greenland/src'
DEFAULT_JSON_PATH = '/Users/powera/repo/greenland/src/wordfreq/trakaido/nouns.json'

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
    Clean English word by removing parenthetical information and indicate if parentheses were present.
    
    Examples:
        "orange (fruit)" -> ("orange", True)
        "cousin (m)" -> ("cousin", True)
        "head (body)" -> ("head", True)
        "Lithuanian (f)" -> ("lithuanian", True)
        "simple" -> ("simple", False)
    
    Args:
        english_word: The English word potentially containing parenthetical info
        
    Returns:
        tuple: (cleaned_word, has_parentheses) where has_parentheses indicates if parentheses were found
    """
    # Check if parenthetical information exists
    has_parentheses = bool(re.search(r'\s*\([^)]+\)', english_word))
    
    # Remove parenthetical information
    cleaned = re.sub(r'\s*\([^)]+\)', '', english_word).strip()
    
    return cleaned, has_parentheses


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
    required_fields = ["English", "Lithuanian", "GUID", "trakaido_level"]
    optional_fields = ["POS", "subtype"]  # These fields are optional but recommended
    
    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValueError(f"Entry {i} is not a dictionary: {entry}")
        
        missing_fields = [field for field in required_fields if field not in entry]
        if missing_fields:
            raise KeyError(f"Entry {i} missing required fields: {missing_fields}")
        
        # Validate POS type if provided
        if "POS" in entry:
            pos_type = entry["POS"].lower()
            valid_pos_types = {
                "noun", "verb", "adjective", "adverb", "pronoun", 
                "preposition", "conjunction", "interjection", "determiner",
                "article", "numeral", "auxiliary", "modal"
            }
            if pos_type not in valid_pos_types:
                print(f"WARNING: Entry {i} has invalid POS type '{entry['POS']}', will use default")
    
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
    # Clean the English word by removing parenthetical information and normalize
    clean_english, has_parentheses = clean_english_word(english_word)
    clean_english = clean_english.strip().lower()
    
    # Store original form in notes if parentheses were present
    notes = f"Original form: {english_word}" if has_parentheses else None
    
    # Use provided POS or default to noun
    if not pos_type:
        pos_type = "noun"
    else:
        pos_type = pos_type.lower()
    
    if not pos_subtype:
        pos_subtype = "other"
    
    # First, try to find existing lemma by checking English derivative forms and Lithuanian translation
    existing_lemmas = session.query(Lemma)\
        .join(DerivativeForm)\
        .join(WordToken)\
        .filter(WordToken.token == clean_english)\
        .filter(WordToken.language_code == "en")\
        .filter(DerivativeForm.language_code == "en")\
        .filter(Lemma.lithuanian_translation == lithuanian_word)\
        .all()
    
    if existing_lemmas:
        lemma = existing_lemmas[0]
        
        # Update difficulty level if requested and different
        if update_difficulty and lemma.difficulty_level != difficulty_level:
            old_difficulty = lemma.difficulty_level
            lemma.difficulty_level = difficulty_level
            session.commit()
            print(f"    Updated difficulty level for '{english_word}' from {old_difficulty} to {difficulty_level}")
        
        # Update notes if parenthetical info exists and lemma doesn't already have notes
        if notes and not lemma.notes:
            lemma.notes = notes
            session.commit()
        
        return lemma  # Return the first match
    
    # Try to find by English word token only
    word_token = get_word_token_by_text(session, clean_english, "en")
    if word_token:
        # Check if there's already a lemma for this word token with matching Lithuanian translation
        existing_lemmas = session.query(Lemma)\
            .join(DerivativeForm)\
            .filter(DerivativeForm.word_token_id == word_token.id)\
            .filter(DerivativeForm.language_code == "en")\
            .filter(Lemma.lithuanian_translation == lithuanian_word)\
            .all()
        
        if existing_lemmas:
            lemma = existing_lemmas[0]
            
            # Update difficulty level if requested and different
            if update_difficulty and lemma.difficulty_level != difficulty_level:
                old_difficulty = lemma.difficulty_level
                lemma.difficulty_level = difficulty_level
                session.commit()
                print(f"    Updated difficulty level for '{english_word}' from {old_difficulty} to {difficulty_level}")
            
            # Update notes if parenthetical info exists and lemma doesn't already have notes
            if notes and not lemma.notes:
                lemma.notes = notes
                session.commit()
            
            return lemma
        
        # Check if there's a lemma for this word token without Lithuanian translation
        existing_lemmas_no_lt = session.query(Lemma)\
            .join(DerivativeForm)\
            .filter(DerivativeForm.word_token_id == word_token.id)\
            .filter(DerivativeForm.language_code == "en")\
            .filter(Lemma.lithuanian_translation.is_(None))\
            .all()
        
        if existing_lemmas_no_lt:
            # Update the existing lemma with Lithuanian translation
            lemma = existing_lemmas_no_lt[0]
            update_lemma_translation(session, lemma.id, "lithuanian", lithuanian_word)
            
            # Update difficulty level if requested and different
            if update_difficulty and lemma.difficulty_level != difficulty_level:
                old_difficulty = lemma.difficulty_level
                lemma.difficulty_level = difficulty_level
                session.commit()
                print(f"    Updated difficulty level for '{english_word}' from {old_difficulty} to {difficulty_level}")
            
            # Update notes if parenthetical info exists and lemma doesn't already have notes
            if notes and not lemma.notes:
                lemma.notes = notes
                session.commit()
            
            return lemma
        
        # If we found the word token but no matching lemma, create a new lemma
        try:
            lemma = add_lemma(
                session=session,
                lemma_text=clean_english,
                definition_text=f"Lithuanian: {lithuanian_word}",
                pos_type=pos_type,
                pos_subtype=pos_subtype,
                difficulty_level=difficulty_level,
                frequency_rank=word_token.frequency_rank,  # Use word token's frequency rank
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
                word_token=word_token,
                is_base_form=True
            )
            
            return lemma
            
        except Exception as e:
            print(f"Error creating lemma for {english_word}: {e}")
            return None
    
    else:
        # Word token doesn't exist, this might be a compound word or phrase
        # Create a basic lemma without word token association
        try:
            lemma = add_lemma(
                session=session,
                lemma_text=clean_english,
                definition_text=f"Lithuanian: {lithuanian_word}",
                pos_type=pos_type,
                pos_subtype=pos_subtype,
                difficulty_level=difficulty_level,
                lithuanian_translation=lithuanian_word,
                notes=notes,
                auto_generate_guid=not existing_guid  # Don't auto-generate if we have an existing GUID
            )
            
            # Set the existing GUID if provided
            if existing_guid:
                lemma.guid = existing_guid
                session.commit()
            
            # Add English derivative form without word token (for phrases/compound words)
            add_derivative_form(
                session=session,
                lemma=lemma,
                derivative_form_text=clean_english,
                language_code="en",
                grammatical_form="singular" if pos_type == "noun" else "base_form",
                word_token=None,  # No word token for multi-word expressions
                is_base_form=True
            )
            
            print(f"Created lemma without word token for: {english_word}")
            return lemma
            
        except Exception as e:
            print(f"Error creating basic lemma for {english_word}: {e}")
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


def migrate_json_data(session, trakaido_data: List[Dict[str, Any]], update_difficulty: bool = True):
    """
    Migrate data from JSON export to the database.
    
    Args:
        session: Database session
        trakaido_data: List of dictionaries with English, Lithuanian, GUID, trakaido level, POS, and subtype data
        update_difficulty: Whether to update difficulty level on existing lemmas (default: True)
    """
    print(f"\nMigrating {len(trakaido_data)} entries from JSON data...")
    
    total_words = len(trakaido_data)
    successful_migrations = 0
    
    for i, entry in enumerate(trakaido_data):
        english_word = entry["English"]
        lithuanian_word = entry["Lithuanian"]
        existing_guid = entry.get("GUID")
        difficulty_level = entry.get("trakaido_level", 1)
        pos_type = entry.get("POS")
        pos_subtype = entry.get("subtype")
        
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
            freq_info = f", freq_rank: {lemma.frequency_rank}" if lemma.frequency_rank else ""
            notes_info = f", notes: {lemma.notes}" if lemma.notes else ""
            pos_info = f", POS: {lemma.pos_type}/{lemma.pos_subtype}" if lemma.pos_subtype else f", POS: {lemma.pos_type}"
            print(f"    ✅ {english_word} -> {lithuanian_word} (GUID: {lemma.guid}{pos_info}{freq_info}{notes_info})")
            
            # Create alternatives for this lemma if they exist
            clean_english, _ = clean_english_word(english_word)
            clean_english = clean_english.strip().lower()
            alternatives_created = create_alternatives_for_lemma(session, lemma, clean_english)
            
        else:
            print(f"    ❌ Failed to create lemma for: {english_word}")
        
        # Progress indicator for large datasets
        if (i + 1) % 100 == 0:
            print(f"  Progress: {i + 1}/{total_words} entries processed...")
    
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