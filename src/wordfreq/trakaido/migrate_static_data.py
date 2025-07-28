#!/usr/bin/env python3
"""
Migration script to populate the wordfreq database with existing static trakaido data.

This script:
1. Reads the existing static word lists from nouns.py
2. Finds or creates corresponding lemmas in the wordfreq database
3. Sets Lithuanian translations on lemmas (using the new translation fields)
4. Creates language-specific derivative forms for English words
5. Assigns categories, difficulty levels, and GUIDs
6. Updates frequency ranks from the database

Usage:
    python migrate_static_data.py
"""

import sys
import os
import json
from typing import Dict, List, Any, Optional

# Configuration - Update these paths as needed
TRAKAIDO_WORDLISTS_BASE_PATH = '/Users/powera/repo/greenland/data/trakaido_wordlists'
GREENLAND_SRC_PATH = '/Users/powera/repo/greenland/src'

# Add paths for imports
sys.path.append(os.path.join(TRAKAIDO_WORDLISTS_BASE_PATH, 'lang_lt'))
sys.path.append(GREENLAND_SRC_PATH)

from nouns import nouns_one, nouns_two, nouns_three, nouns_four, nouns_five, common_words, common_words_two
from wordfreq.storage.database import (
    create_database_session, 
    get_word_token_by_text,
    add_lemma,
    add_derivative_form,
    generate_guid,
    update_lemma_translation
)
from wordfreq.storage.models.schema import WordToken, Lemma, DerivativeForm
import constants

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
        "Plants + Animals": ("noun", "animal"),  # Mixed category, defaulting to animal
        
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
        "Family + Relationships": ("noun", "human"),
        "People + Relationships": ("noun", "human"),
        "Nationalities": ("noun", "nationality"),
        
        # Places and geography
        "Countries": ("noun", "place_name"),
        "Cities": ("noun", "place_name"),
        "Geographic Features": ("noun", "natural_feature"),
        "Places + Direction": ("noun", "place_name"),
        
        # Time and temporal
        "Days of the Week": ("noun", "temporal_name"),
        "Months of the Year": ("noun", "temporal_name"),
        "Time + Life": ("noun", "time_period"),
        
        # Abstract concepts
        "Emotions": ("noun", "emotion_feeling"),
        "Abstract Concepts": ("noun", "concept_idea"),
        "Hobbies": ("noun", "concept_idea"),
        "Social + Political": ("noun", "concept_idea"),
        "Thinking + Communication": ("noun", "concept_idea"),
        
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
    
    # Convert generic "other" to POS-specific other for GUID generation
    if pos_subtype == "other":
        pos_subtype = f"{pos_type}_other"
    
    return pos_type, pos_subtype



def find_or_create_lemma(session, english_word: str, lithuanian_word: str, display_category_name: str, difficulty_level: int) -> Optional[Lemma]:
    """
    Find an existing lemma or create a new one for the given English/Lithuanian pair.
    
    Args:
        session: Database session
        english_word: English word
        lithuanian_word: Lithuanian translation
        display_category_name: Display category name from nouns.py
        difficulty_level: Difficulty level to assign (1-5)
        
    Returns:
        Lemma object or None if creation failed
    """
    # Clean the English word for lookup
    clean_english = english_word.strip().lower()
    
    # Get the appropriate POS and subtype
    pos_type, pos_subtype = get_pos_and_subtype_for_category(display_category_name)
    
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
        return existing_lemmas[0]  # Return the first match
    
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
            return existing_lemmas[0]
        
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
                lithuanian_translation=lithuanian_word
            )
            
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
                lithuanian_translation=lithuanian_word
            )
            
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

def migrate_corpus_data(session, corpus_name: str, corpus_data: Dict[str, List[Dict[str, str]]], difficulty_level: int):
    """
    Migrate data from a single corpus (e.g., nouns_one) to the database.
    
    Args:
        session: Database session
        corpus_name: Name of the corpus (e.g., "nouns_one")
        corpus_data: Dictionary of categories and word lists
        difficulty_level: Difficulty level to assign (1-5)
    """
    print(f"\nMigrating {corpus_name} (difficulty level {difficulty_level})...")
    
    total_words = 0
    successful_migrations = 0
    
    for category_display_name, word_list in corpus_data.items():
        pos_type, pos_subtype = get_pos_and_subtype_for_category(category_display_name)
        subtype_info = f" ({pos_type}/{pos_subtype})" if pos_subtype else f" ({pos_type})"
        print(f"  Processing category: {category_display_name}{subtype_info}")
        
        for word_dict in word_list:
            english_word = word_dict["english"]
            lithuanian_word = word_dict["lithuanian"]
            total_words += 1
            
            # Find or create lemma
            lemma = find_or_create_lemma(session, english_word, lithuanian_word, category_display_name, difficulty_level)
            
            if lemma:
                successful_migrations += 1
                print(f"    ✅ {english_word} -> {lithuanian_word} (GUID: {lemma.guid})")
            else:
                print(f"    ❌ Failed to create lemma for: {english_word}")
    
    print(f"  Completed {corpus_name}: {successful_migrations}/{total_words} words migrated")
    return successful_migrations, total_words

def main():
    """Main migration function."""
    print("Starting migration of static trakaido data to wordfreq database...")
    
    # Create database session
    try:
        session = create_database_session()
        print("✅ Connected to wordfreq database")
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        return
    
    # Dictionary mapping corpus names to their data and difficulty levels
    corpus_mapping = {
        "nouns_one": (nouns_one, 1),
        "nouns_two": (nouns_two, 2),
        "nouns_three": (nouns_three, 3),
        "nouns_four": (nouns_four, 4),
        "nouns_five": (nouns_five, 5),
        "common_words": (common_words, 1),  # Treat as level 1
        "common_words_two": (common_words_two, 2)  # Treat as level 2
    }
    
    total_successful = 0
    total_words = 0
    
    try:
        for corpus_name, (corpus_data, difficulty_level) in corpus_mapping.items():
            successful, words = migrate_corpus_data(session, corpus_name, corpus_data, difficulty_level)
            total_successful += successful
            total_words += words
        
        print(f"\n🎉 Migration completed!")
        print(f"Total words processed: {total_words}")
        print(f"Successfully migrated: {total_successful}")
        print(f"Failed migrations: {total_words - total_successful}")
        
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
        print(f"Lemmas with subtypes: {lemmas_with_subtypes}")
        print(f"Lemmas with GUIDs: {lemmas_with_guids}")
        print(f"Lemmas with Lithuanian translations: {lemmas_with_lithuanian}")
        print(f"Lemmas with difficulty levels: {lemmas_with_difficulty}")
        print(f"English derivative forms: {english_derivative_forms}")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    main()