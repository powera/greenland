#!/usr/bin/env python3
"""
Trakaido Word Management Utilities

This module provides tools for adding new words to the trakaido system and managing
difficulty levels with LLM assistance and user review.

Features:
- Add new words with GPT-4o-mini assistance for linguistic data
- Set/update difficulty levels for existing words
- Interactive user review and approval process
- GUID generation and management
- Integration with existing database schema

Usage:
    from wordfreq.trakaido.utils import WordManager
    
    manager = WordManager()
    manager.add_word("example")
    manager.set_level("N07_008", 2)
"""

import json
import logging
import sys
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from pathlib import Path

# Add the src directory to the path for imports
GREENLAND_SRC_PATH = '/Users/powera/repo/greenland/src'
sys.path.append(GREENLAND_SRC_PATH)

from wordfreq.storage.database import (
    create_database_session,
    add_word_token,
    get_subtype_values_for_pos,
    SUBTYPE_GUID_PREFIXES
)
from wordfreq.storage.models.schema import Lemma, DerivativeForm, WordToken
from wordfreq.storage.models.enums import GrammaticalForm
from wordfreq.translation.client import LinguisticClient
from clients.unified_client import UnifiedLLMClient
from clients.types import Schema, SchemaProperty
import util.prompt_loader
import constants

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class WordData:
    """Data structure for word information from LLM."""
    english: str
    lithuanian: str
    pos_type: str
    pos_subtype: str
    definition: str
    confidence: float
    alternatives: Dict[str, List[str]]
    notes: str
    # Additional translation fields
    chinese_translation: Optional[str] = None
    korean_translation: Optional[str] = None
    french_translation: Optional[str] = None
    swahili_translation: Optional[str] = None
    vietnamese_translation: Optional[str] = None

@dataclass
class ReviewResult:
    """Result of user review process."""
    approved: bool
    modifications: Dict[str, Any]
    notes: str

class WordManager:
    """Main class for managing trakaido words."""
    
    def __init__(self, model: str = "gpt-4o-mini", db_path: str = None, debug: bool = False):
        """
        Initialize the WordManager.
        
        Args:
            model: LLM model to use (default: gpt-4o-mini)
            db_path: Database path (uses default if None)
            debug: Enable debug logging
        """
        self.model = model
        self.db_path = db_path or constants.WORDFREQ_DB_PATH
        self.debug = debug
        self.client = UnifiedLLMClient(debug=debug)
        
        if debug:
            logger.setLevel(logging.DEBUG)
    
    def get_session(self):
        """Get database session."""
        return create_database_session(self.db_path)
    
    def _get_word_analysis_prompt(self, english_word: str, lithuanian_word: str = None) -> str:
        """Get the prompt for analyzing a new word."""
        context = util.prompt_loader.get_context("wordfreq", "word_analysis")
        
        if lithuanian_word:
            word_specification = f"English word '{english_word}' with Lithuanian translation '{lithuanian_word}'"
            meaning_clarification = f"Focus on the specific meaning where '{english_word}' translates to '{lithuanian_word}' in Lithuanian."
        else:
            word_specification = f"English word '{english_word}'"
            meaning_clarification = "Provide the most common, basic meaning of this word."
        
        return f"""{context}

Analyze the {word_specification} and provide:

1. Part of speech (noun, verb, adjective, adverb, etc.) - for the LEMMA form only
2. Specific subtype classification
3. Lithuanian translation (lemma/base form)
4. Definition suitable for language learners
5. Translations to other languages (Chinese, Korean, French, Swahili, Vietnamese)
6. Alternative forms in both languages (if any)
7. Confidence score (0.0-1.0)
8. Any special notes

IMPORTANT REQUIREMENTS:
- {meaning_clarification}
- Provide only the LEMMA (base) form - not conjugations, plurals, or alternative meanings
- For nouns: singular form (e.g., "cheese" not "cheeses")
- For verbs: infinitive form (e.g., "to eat" not "eating" or "ate")
- For adjectives: positive form (e.g., "big" not "bigger" or "biggest")
- Focus on the primary, most common meaning of the word
- Ensure all translations are also in their base/lemma forms

Word to analyze: {english_word}"""
    
    def _query_word_data(self, english_word: str, lithuanian_word: str = None) -> Tuple[Optional[WordData], bool]:
        """
        Query LLM for comprehensive word data.
        
        Args:
            english_word: English word to analyze
            lithuanian_word: Optional Lithuanian translation to clarify meaning
            
        Returns:
            Tuple of (WordData object, success flag)
        """
        # Get available subtypes for schema
        all_subtypes = []
        for pos in ['noun', 'verb', 'adjective', 'adverb']:
            all_subtypes.extend(get_subtype_values_for_pos(pos))
        
        schema = Schema(
            name="WordAnalysis",
            description="Comprehensive analysis of a word for language learning",
            properties={
                "english": SchemaProperty("string", "The English word being analyzed"),
                "lithuanian": SchemaProperty("string", "Lithuanian translation of the word"),
                "pos_type": SchemaProperty("string", "Part of speech", 
                    enum=["noun", "verb", "adjective", "adverb", "pronoun", "preposition", 
                          "conjunction", "interjection", "determiner", "article", "numeral"]),
                "pos_subtype": SchemaProperty("string", "Specific subtype classification", 
                    enum=all_subtypes),
                "definition": SchemaProperty("string", "Clear definition for language learners"),
                "confidence": SchemaProperty("number", "Confidence score from 0.0-1.0", 
                    minimum=0.0, maximum=1.0),
                "chinese_translation": SchemaProperty("string", "Chinese translation (base form)"),
                "korean_translation": SchemaProperty("string", "Korean translation (base form)"),
                "french_translation": SchemaProperty("string", "French translation (base form)"),
                "swahili_translation": SchemaProperty("string", "Swahili translation (base form)"),
                "vietnamese_translation": SchemaProperty("string", "Vietnamese translation (base form)"),
                "alternatives": SchemaProperty(
                    type="object",
                    description="Alternative forms in different languages",
                    properties={
                        "english": SchemaProperty(
                            type="array",
                            description="Alternative English forms",
                            items={"type": "string"}
                        ),
                        "lithuanian": SchemaProperty(
                            type="array", 
                            description="Alternative Lithuanian forms",
                            items={"type": "string"}
                        )
                    }
                ),
                "notes": SchemaProperty("string", "Additional notes about the word")
            }
        )
        
        prompt = self._get_word_analysis_prompt(english_word, lithuanian_word)
        
        try:
            response = self.client.generate_chat(
                prompt=prompt,
                model=self.model,
                json_schema=schema
            )
            
            if response.structured_data:
                data = response.structured_data
                return WordData(
                    english=data.get('english', english_word),
                    lithuanian=data.get('lithuanian', lithuanian_word or ''),
                    pos_type=data.get('pos_type', 'noun'),
                    pos_subtype=data.get('pos_subtype', ''),
                    definition=data.get('definition', ''),
                    confidence=data.get('confidence', 0.5),
                    alternatives=data.get('alternatives', {'english': [], 'lithuanian': []}),
                    notes=data.get('notes', ''),
                    chinese_translation=data.get('chinese_translation'),
                    korean_translation=data.get('korean_translation'),
                    french_translation=data.get('french_translation'),
                    swahili_translation=data.get('swahili_translation'),
                    vietnamese_translation=data.get('vietnamese_translation')
                ), True
            else:
                logger.error(f"No structured data received for word '{english_word}'")
                return None, False
                
        except Exception as e:
            logger.error(f"Error querying word data for '{english_word}': {e}")
            return None, False
    
    def _generate_guid(self, pos_subtype: str, session) -> str:
        """
        Generate a unique GUID for a word.
        
        Args:
            pos_subtype: The POS subtype for GUID prefix
            session: Database session
            
        Returns:
            Unique GUID string
        """
        # Get prefix from subtype
        prefix = SUBTYPE_GUID_PREFIXES.get(pos_subtype, 'N99')  # Default to N99 for unknown
        
        # Find the next available number for this prefix
        existing_guids = session.query(Lemma.guid).filter(
            Lemma.guid.like(f"{prefix}_%")
        ).all()
        
        existing_numbers = []
        for guid_tuple in existing_guids:
            guid = guid_tuple[0]
            if guid and '_' in guid:
                try:
                    number = int(guid.split('_')[1])
                    existing_numbers.append(number)
                except (ValueError, IndexError):
                    continue
        
        # Find next available number
        next_number = 1
        while next_number in existing_numbers:
            next_number += 1
        
        return f"{prefix}_{next_number:03d}"
    
    def _display_word_data(self, data: WordData) -> None:
        """Display word data for user review."""
        print("\n" + "="*60)
        print("WORD ANALYSIS RESULTS")
        print("="*60)
        print(f"English: {data.english}")
        print(f"Lithuanian: {data.lithuanian}")
        print(f"Part of Speech: {data.pos_type}")
        print(f"Subtype: {data.pos_subtype}")
        print(f"Definition: {data.definition}")
        print(f"Confidence: {data.confidence:.2f}")
        
        # Show additional translations
        translations = []
        if data.chinese_translation:
            translations.append(f"Chinese: {data.chinese_translation}")
        if data.korean_translation:
            translations.append(f"Korean: {data.korean_translation}")
        if data.french_translation:
            translations.append(f"French: {data.french_translation}")
        if data.swahili_translation:
            translations.append(f"Swahili: {data.swahili_translation}")
        if data.vietnamese_translation:
            translations.append(f"Vietnamese: {data.vietnamese_translation}")
        
        if translations:
            print("Other translations:")
            for trans in translations:
                print(f"  {trans}")
        
        if data.alternatives['english']:
            print(f"English Alternatives: {', '.join(data.alternatives['english'])}")
        if data.alternatives['lithuanian']:
            print(f"Lithuanian Alternatives: {', '.join(data.alternatives['lithuanian'])}")
        
        if data.notes:
            print(f"Notes: {data.notes}")
        print("="*60)
    
    def _get_user_review(self, data: WordData) -> ReviewResult:
        """
        Get user review and approval for word data.
        
        Args:
            data: WordData to review
            
        Returns:
            ReviewResult with user decisions
        """
        self._display_word_data(data)
        
        while True:
            choice = input("\nOptions:\n"
                          "1. Approve as-is\n"
                          "2. Modify before approval\n"
                          "3. Reject\n"
                          "Enter choice (1-3): ").strip()
            
            if choice == '1':
                return ReviewResult(approved=True, modifications={}, notes="")
            
            elif choice == '2':
                modifications = {}
                
                # Allow modification of key fields
                new_lithuanian = input(f"Lithuanian [{data.lithuanian}]: ").strip()
                if new_lithuanian:
                    modifications['lithuanian'] = new_lithuanian
                
                new_definition = input(f"Definition [{data.definition}]: ").strip()
                if new_definition:
                    modifications['definition'] = new_definition
                
                # Allow modification of difficulty level during review
                new_level = input("Difficulty Level (1-20, leave blank to set later): ").strip()
                if new_level and new_level.isdigit():
                    level = int(new_level)
                    if 1 <= level <= 20:
                        modifications['difficulty_level'] = level
                
                new_subtype = input(f"Subtype [{data.pos_subtype}]: ").strip()
                if new_subtype:
                    modifications['pos_subtype'] = new_subtype
                
                notes = input("Review notes: ").strip()
                
                return ReviewResult(approved=True, modifications=modifications, notes=notes)
            
            elif choice == '3':
                notes = input("Rejection reason: ").strip()
                return ReviewResult(approved=False, modifications={}, notes=notes)
            
            else:
                print("Invalid choice. Please enter 1, 2, or 3.")
    
    def add_word(self, english_word: str, lithuanian_word: str = None, 
                 difficulty_level: int = None, auto_approve: bool = False) -> bool:
        """
        Add a new word to the trakaido system.
        
        Args:
            english_word: English word to add
            lithuanian_word: Optional Lithuanian translation to clarify meaning
            difficulty_level: Optional difficulty level (1-20)
            auto_approve: Skip user review if True
            
        Returns:
            Success flag
        """
        logger.info(f"Adding word: {english_word}" + 
                   (f" → {lithuanian_word}" if lithuanian_word else ""))
        
        session = self.get_session()
        try:
            # Check if word already exists
            existing = session.query(Lemma).filter(
                Lemma.lemma_text.ilike(english_word)
            ).first()
            
            if existing:
                print(f"Word '{english_word}' already exists in database with GUID: {existing.guid}")
                return False
            
            # Query LLM for word data
            print(f"Analyzing word '{english_word}' with {self.model}...")
            word_data, success = self._query_word_data(english_word, lithuanian_word)
            
            if not success or not word_data:
                logger.error(f"Failed to get analysis for word '{english_word}'")
                return False
            
            # User review (unless auto-approve)
            if not auto_approve:
                review = self._get_user_review(word_data)
                
                if not review.approved:
                    logger.info(f"Word '{english_word}' rejected by user: {review.notes}")
                    return False
                
                # Apply modifications
                for key, value in review.modifications.items():
                    setattr(word_data, key, value)
            
            # Use provided difficulty level or default to 1 if not set
            final_difficulty_level = difficulty_level or getattr(word_data, 'difficulty_level', None) or 1
            
            # Generate GUID
            guid = self._generate_guid(word_data.pos_subtype, session)
            
            # Create lemma with all translation fields
            lemma = Lemma(
                lemma_text=word_data.english,
                definition_text=word_data.definition,
                pos_type=word_data.pos_type,
                pos_subtype=word_data.pos_subtype,
                guid=guid,
                difficulty_level=final_difficulty_level,
                lithuanian_translation=word_data.lithuanian,
                chinese_translation=word_data.chinese_translation,
                korean_translation=word_data.korean_translation,
                french_translation=word_data.french_translation,
                swahili_translation=word_data.swahili_translation,
                vietnamese_translation=word_data.vietnamese_translation,
                confidence=word_data.confidence,
                notes=word_data.notes,
                verified=not auto_approve  # Mark as verified if user reviewed
            )
            
            session.add(lemma)
            session.flush()  # Get the ID
            
            # Create English derivative form (base form)
            english_token = add_word_token(session, word_data.english, 'en')
            english_form = DerivativeForm(
                lemma_id=lemma.id,
                derivative_form_text=word_data.english,
                word_token_id=english_token.id,
                language_code='en',
                grammatical_form=self._get_default_grammatical_form(word_data.pos_type),
                is_base_form=True,
                verified=not auto_approve
            )
            session.add(english_form)
            
            # Create Lithuanian derivative form (base form)
            if word_data.lithuanian:
                lithuanian_token = add_word_token(session, word_data.lithuanian, 'lt')
                lithuanian_form = DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text=word_data.lithuanian,
                    word_token_id=lithuanian_token.id,
                    language_code='lt',
                    grammatical_form=self._get_default_grammatical_form(word_data.pos_type),
                    is_base_form=True,
                    verified=not auto_approve
                )
                session.add(lithuanian_form)
            
            # Add alternative forms
            for alt_english in word_data.alternatives.get('english', []):
                if alt_english != word_data.english:
                    alt_token = add_word_token(session, alt_english, 'en')
                    alt_form = DerivativeForm(
                        lemma_id=lemma.id,
                        derivative_form_text=alt_english,
                        word_token_id=alt_token.id,
                        language_code='en',
                        grammatical_form='alternative_form',
                        is_base_form=False,
                        verified=not auto_approve
                    )
                    session.add(alt_form)
            
            for alt_lithuanian in word_data.alternatives.get('lithuanian', []):
                if alt_lithuanian != word_data.lithuanian:
                    alt_token = add_word_token(session, alt_lithuanian, 'lt')
                    alt_form = DerivativeForm(
                        lemma_id=lemma.id,
                        derivative_form_text=alt_lithuanian,
                        word_token_id=alt_token.id,
                        language_code='lt',
                        grammatical_form='alternative_form',
                        is_base_form=False,
                        verified=not auto_approve
                    )
                    session.add(alt_form)
            
            session.commit()
            
            print(f"\n✅ Successfully added word '{english_word}' with GUID: {guid}")
            print(f"   Lithuanian: {word_data.lithuanian}")
            print(f"   Level: {final_difficulty_level}")
            print(f"   Subtype: {word_data.pos_subtype}")
            
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error adding word '{english_word}': {e}")
            return False
        finally:
            session.close()
    
    def _get_default_grammatical_form(self, pos_type: str) -> str:
        """Get default grammatical form for a POS type."""
        defaults = {
            'noun': 'singular',
            'verb': 'infinitive',
            'adjective': 'positive',
            'adverb': 'base_form'
        }
        return defaults.get(pos_type, 'base_form')
    
    def set_level(self, identifier: str, new_level: int, reason: str = "") -> bool:
        """
        Set or update the difficulty level for a word.
        
        Args:
            identifier: GUID or English word to update
            new_level: New difficulty level (1-20)
            reason: Reason for the change
            
        Returns:
            Success flag
        """
        if not (1 <= new_level <= 20):
            logger.error(f"Invalid difficulty level: {new_level}. Must be 1-20.")
            return False
        
        session = self.get_session()
        try:
            # Find lemma by GUID or English text
            if identifier.startswith(('N', 'V', 'A')):  # Looks like a GUID
                lemma = session.query(Lemma).filter(Lemma.guid == identifier).first()
            else:
                lemma = session.query(Lemma).filter(
                    Lemma.lemma_text.ilike(identifier)
                ).first()
            
            if not lemma:
                logger.error(f"Word not found: {identifier}")
                return False
            
            old_level = lemma.difficulty_level
            lemma.difficulty_level = new_level
            
            # Add to notes if reason provided
            if reason:
                current_notes = lemma.notes or ""
                timestamp = datetime.now().strftime("%Y-%m-%d")
                level_note = f"[{timestamp}] Level changed from {old_level} to {new_level}: {reason}"
                lemma.notes = f"{current_notes}\n{level_note}".strip()
            
            session.commit()
            
            print(f"✅ Updated level for '{lemma.lemma_text}' ({lemma.guid})")
            print(f"   Old level: {old_level} → New level: {new_level}")
            if reason:
                print(f"   Reason: {reason}")
            
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error setting level for '{identifier}': {e}")
            return False
        finally:
            session.close()
    
    def list_words(self, level: Optional[int] = None, subtype: Optional[str] = None, 
                   limit: int = 50) -> List[Dict[str, Any]]:
        """
        List words with optional filtering.
        
        Args:
            level: Filter by difficulty level
            subtype: Filter by POS subtype
            limit: Maximum number of results
            
        Returns:
            List of word dictionaries
        """
        session = self.get_session()
        try:
            query = session.query(Lemma).filter(Lemma.guid.isnot(None))
            
            if level:
                query = query.filter(Lemma.difficulty_level == level)
            if subtype:
                query = query.filter(Lemma.pos_subtype == subtype)
            
            query = query.order_by(Lemma.guid).limit(limit)
            lemmas = query.all()
            
            results = []
            for lemma in lemmas:
                results.append({
                    'guid': lemma.guid,
                    'english': lemma.lemma_text,
                    'lithuanian': lemma.lithuanian_translation,
                    'level': lemma.difficulty_level,
                    'subtype': lemma.pos_subtype,
                    'verified': lemma.verified
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Error listing words: {e}")
            return []
        finally:
            session.close()
    
    def export_to_json(self, output_path: Optional[str] = None) -> bool:
        """
        Export all trakaido words to JSON format (like exported_nouns.json).
        
        Args:
            output_path: Path to output JSON file (uses default if None)
            
        Returns:
            Success flag
        """
        if not output_path:
            output_path = Path(GREENLAND_SRC_PATH) / "wordfreq" / "trakaido" / "exported_nouns.json"
        
        session = self.get_session()
        try:
            # Get all lemmas with GUIDs, ordered by GUID
            lemmas = session.query(Lemma).filter(
                Lemma.guid.isnot(None)
            ).order_by(Lemma.guid).all()
            
            export_data = []
            for lemma in lemmas:
                # Convert POS type to match existing format
                pos_display = lemma.pos_type
                if lemma.pos_type in ['noun', 'verb', 'adjective', 'adverb']:
                    pos_display = lemma.pos_type
                
                entry = {
                    "English": lemma.lemma_text,
                    "Lithuanian": lemma.lithuanian_translation or "",
                    "GUID": lemma.guid,
                    "trakaido_level": lemma.difficulty_level or 1,
                    "POS": pos_display,
                    "subtype": lemma.pos_subtype or ""
                }
                export_data.append(entry)
            
            # Write to JSON file
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Exported {len(export_data)} words to {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting to JSON: {e}")
            return False
        finally:
            session.close()
    
    def export_to_lang_lt(self, output_dir: Optional[str] = None) -> bool:
        """
        Export words to lang_lt directory structure using dict_generator.
        
        Args:
            output_dir: Output directory (uses default if None)
            
        Returns:
            Success flag
        """
        try:
            # Import dict_generator functions
            from wordfreq.trakaido.dict_generator import (
                generate_structure_file,
                generate_dictionary_file
            )
            
            if not output_dir:
                output_dir = '/Users/powera/repo/greenland/data/trakaido_wordlists/lang_lt/generated'
            
            session = self.get_session()
            
            # Generate structure files for each level
            levels_generated = []
            for level in range(1, 21):  # Levels 1-20
                try:
                    filepath = generate_structure_file(session, level, output_dir)
                    if filepath:
                        levels_generated.append(level)
                        logger.info(f"Generated structure file for level {level}")
                except Exception as e:
                    logger.warning(f"Failed to generate structure file for level {level}: {e}")
            
            # Generate dictionary files for each subtype
            subtypes = session.query(Lemma.pos_subtype).filter(
                Lemma.pos_subtype.isnot(None),
                Lemma.guid.isnot(None)
            ).distinct().all()
            
            dictionaries_generated = []
            for subtype_tuple in subtypes:
                subtype = subtype_tuple[0]
                if subtype:
                    try:
                        filepath = generate_dictionary_file(session, subtype, output_dir)
                        if filepath:
                            dictionaries_generated.append(subtype)
                            logger.info(f"Generated dictionary file for {subtype}")
                    except Exception as e:
                        logger.warning(f"Failed to generate dictionary file for {subtype}: {e}")
            
            session.close()
            
            print(f"\n✅ Export to lang_lt completed:")
            print(f"   Structure files: {len(levels_generated)} levels")
            print(f"   Dictionary files: {len(dictionaries_generated)} subtypes")
            print(f"   Output directory: {output_dir}")
            
            return len(levels_generated) > 0 or len(dictionaries_generated) > 0
            
        except Exception as e:
            logger.error(f"Error exporting to lang_lt: {e}")
            return False
    
    def export_all(self, json_path: Optional[str] = None, lang_lt_dir: Optional[str] = None) -> bool:
        """
        Export to both JSON and lang_lt formats.
        
        Args:
            json_path: Path for JSON export
            lang_lt_dir: Directory for lang_lt export
            
        Returns:
            Success flag
        """
        print("Starting full export...")
        
        json_success = self.export_to_json(json_path)
        lang_lt_success = self.export_to_lang_lt(lang_lt_dir)
        
        if json_success and lang_lt_success:
            print("\n✅ Full export completed successfully!")
            return True
        elif json_success:
            print("\n⚠️  JSON export succeeded, but lang_lt export failed")
            return False
        elif lang_lt_success:
            print("\n⚠️  lang_lt export succeeded, but JSON export failed")
            return False
        else:
            print("\n❌ Both exports failed")
            return False

# CLI interface functions
def main():
    """Command-line interface for word management."""
    import argparse
    from datetime import datetime
    
    parser = argparse.ArgumentParser(description="Trakaido Word Management Tool")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Add word command
    add_parser = subparsers.add_parser('add', help='Add a new word')
    add_parser.add_argument('english_word', help='English word to add')
    add_parser.add_argument('--lithuanian', help='Lithuanian translation to clarify meaning')
    add_parser.add_argument('--level', type=int, help='Difficulty level (1-20)')
    add_parser.add_argument('--auto-approve', action='store_true', 
                           help='Skip user review')
    add_parser.add_argument('--model', default='gpt-4o-mini', 
                           help='LLM model to use')
    
    # Set level command
    level_parser = subparsers.add_parser('set-level', help='Set word difficulty level')
    level_parser.add_argument('identifier', help='GUID or English word')
    level_parser.add_argument('level', type=int, help='New difficulty level (1-20)')
    level_parser.add_argument('--reason', help='Reason for the change')
    
    # List words command
    list_parser = subparsers.add_parser('list', help='List words')
    list_parser.add_argument('--level', type=int, help='Filter by difficulty level')
    list_parser.add_argument('--subtype', help='Filter by POS subtype')
    list_parser.add_argument('--limit', type=int, default=50, help='Maximum results')
    
    # Export commands
    export_parser = subparsers.add_parser('export', help='Export words to files')
    export_subparsers = export_parser.add_subparsers(dest='export_type', help='Export formats')
    
    # Export to JSON
    json_parser = export_subparsers.add_parser('json', help='Export to JSON format')
    json_parser.add_argument('--output', help='Output JSON file path')
    
    # Export to lang_lt
    lang_lt_parser = export_subparsers.add_parser('lang-lt', help='Export to lang_lt directory structure')
    lang_lt_parser.add_argument('--output-dir', help='Output directory path')
    
    # Export all
    all_parser = export_subparsers.add_parser('all', help='Export to both JSON and lang_lt')
    all_parser.add_argument('--json-output', help='JSON output file path')
    all_parser.add_argument('--lang-lt-dir', help='lang_lt output directory path')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    manager = WordManager(model=args.model if hasattr(args, 'model') else 'gpt-4o-mini')
    
    if args.command == 'add':
        success = manager.add_word(
            english_word=args.english_word,
            lithuanian_word=args.lithuanian,
            difficulty_level=args.level,
            auto_approve=args.auto_approve
        )
        sys.exit(0 if success else 1)
    
    elif args.command == 'set-level':
        success = manager.set_level(args.identifier, args.level, 
                                   reason=getattr(args, 'reason', ''))
        sys.exit(0 if success else 1)
    
    elif args.command == 'list':
        words = manager.list_words(level=args.level, subtype=args.subtype, 
                                  limit=args.limit)
        
        if words:
            print(f"\nFound {len(words)} words:")
            print("-" * 80)
            for word in words:
                status = "✓" if word['verified'] else "?"
                print(f"{status} {word['guid']:<10} L{word['level']:<2} "
                      f"{word['english']:<20} → {word['lithuanian']:<20} "
                      f"({word['subtype']})")
        else:
            print("No words found matching criteria.")
    
    elif args.command == 'export':
        if not args.export_type:
            export_parser.print_help()
            sys.exit(1)
        
        if args.export_type == 'json':
            success = manager.export_to_json(args.output)
            sys.exit(0 if success else 1)
        
        elif args.export_type == 'lang-lt':
            success = manager.export_to_lang_lt(args.output_dir)
            sys.exit(0 if success else 1)
        
        elif args.export_type == 'all':
            success = manager.export_all(args.json_output, args.lang_lt_dir)
            sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()