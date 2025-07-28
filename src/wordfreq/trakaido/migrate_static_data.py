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
import re
from typing import Dict, List, Any, Optional

# Configuration - Update these paths as needed
GREENLAND_SRC_PATH = '/Users/powera/repo/greenland/src'

# Add paths for imports
sys.path.append(GREENLAND_SRC_PATH)

from wordfreq.trakaido.nouns import nouns_one, nouns_two, nouns_three, nouns_four, nouns_five, common_words, common_words_two
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
        english_word: English word (may contain parenthetical info)
        lithuanian_word: Lithuanian translation
        display_category_name: Display category name from nouns.py
        difficulty_level: Difficulty level to assign (1-5)
        
    Returns:
        Lemma object or None if creation failed
    """
    # Clean the English word by removing parenthetical information and normalize
    clean_english, has_parentheses = clean_english_word(english_word)
    clean_english = clean_english.strip().lower()
    
    # Store original form in notes if parentheses were present
    notes = f"Original form: {english_word}" if has_parentheses else None
    
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
        lemma = existing_lemmas[0]
        
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
                notes=notes
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
                lithuanian_translation=lithuanian_word,
                notes=notes
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
                freq_info = f", freq_rank: {lemma.frequency_rank}" if lemma.frequency_rank else ""
                notes_info = f", notes: {lemma.notes}" if lemma.notes else ""
                print(f"    ✅ {english_word} -> {lithuanian_word} (GUID: {lemma.guid}{freq_info}{notes_info})")
                
                # Create alternatives for this lemma if they exist
                clean_english, _ = clean_english_word(english_word)
                clean_english = clean_english.strip().lower()
                alternatives_created = create_alternatives_for_lemma(session, lemma, clean_english)
                
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
        "nouns_three": (nouns_three, 4), # Treat as level 4
        "nouns_four": (nouns_four, 7), # Treat as level 7
        "nouns_five": (nouns_five, 6), # Treat as level 6
        "common_words": (common_words, 3),  # Treat as level 3
        "common_words_two": (common_words_two, 5)  # Treat as level 5
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