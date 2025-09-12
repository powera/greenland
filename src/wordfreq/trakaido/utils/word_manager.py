
#!/usr/bin/env python3
"""
Core word management functionality for trakaido system.

Provides the WordManager class for adding, updating, and managing words
in the trakaido database.
"""

import logging
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# Add the src directory to the path for imports
GREENLAND_SRC_PATH = '/Users/powera/repo/greenland/src'
sys.path.append(GREENLAND_SRC_PATH)

import constants
import util.prompt_loader
from clients.types import Schema, SchemaProperty
from clients.unified_client import UnifiedLLMClient
from wordfreq.storage.database import (
    SUBTYPE_GUID_PREFIXES,
    add_word_token,
    create_database_session,
    get_subtype_values_for_pos,
)
from wordfreq.storage.models.enums import GrammaticalForm
from wordfreq.storage.models.schema import DerivativeForm, Lemma, WordToken

from .data_models import WordData, ReviewResult
from .text_rendering import display_word_data, display_current_lemma_entry, get_user_confirmation

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class WordManager:
    """Main class for managing trakaido words."""

    def __init__(self, model: str = "gpt-5-mini", db_path: str = None, debug: bool = False):
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

    def _query_word_data(self, english_word: str, lithuanian_word: str = None, model_override: str = None) -> Tuple[Optional[WordData], bool]:
        """
        Query LLM for comprehensive word data.

        Args:
            english_word: English word to analyze
            lithuanian_word: Optional Lithuanian translation to clarify meaning
            model_override: Override the default model (e.g., "gpt-5-nano")

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
            model_to_use = model_override or self.model
            response = self.client.generate_chat(
                prompt=prompt,
                model=model_to_use,
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

    def _get_user_review(self, data: WordData) -> ReviewResult:
        """
        Get user review and approval for word data.

        Args:
            data: WordData to review

        Returns:
            ReviewResult with user decisions
        """
        display_word_data(data)

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

    def _get_default_grammatical_form(self, pos_type: str) -> str:
        """Get default grammatical form for a POS type."""
        defaults = {
            'noun': 'singular',
            'verb': 'infinitive',
            'adjective': 'positive',
            'adverb': 'base_form'
        }
        return defaults.get(pos_type, 'base_form')

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

    def list_subtypes(self) -> List[Dict[str, Any]]:
        """
        List all subtypes with their POS type and word counts.

        Returns:
            List of dictionaries with subtype information
        """
        session = self.get_session()
        try:
            # Query to get counts by pos_type and pos_subtype
            from sqlalchemy import func

            query = session.query(
                Lemma.pos_type,
                Lemma.pos_subtype,
                func.count(Lemma.id).label('count')
            ).filter(
                Lemma.pos_subtype.isnot(None),
                Lemma.pos_subtype != ''
            ).group_by(
                Lemma.pos_type,
                Lemma.pos_subtype
            ).order_by(
                Lemma.pos_type,
                Lemma.pos_subtype
            )

            results = []
            for pos_type, pos_subtype, count in query.all():
                results.append({
                    'pos_type': pos_type,
                    'pos_subtype': pos_subtype,
                    'count': count
                })

            return results

        except Exception as e:
            logger.error(f"Error listing subtypes: {e}")
            return []
        finally:
            session.close()

    def move_words_by_subtype_and_level(self, from_level: int, subtype: str, to_level: int,
                                       reason: str = "", dry_run: bool = False) -> bool:
        """
        Move all words matching a specific level and subtype to a new level.

        Args:
            from_level: Current difficulty level to move from (1-20)
            subtype: POS subtype to filter by (e.g., "clothing")
            to_level: New difficulty level to move to (1-20)
            reason: Reason for the bulk change
            dry_run: If True, show what would be changed without making changes

        Returns:
            Success flag
        """
        # Validate levels
        if not (1 <= from_level <= 20):
            logger.error(f"Invalid from_level: {from_level}. Must be 1-20.")
            return False
        if not (1 <= to_level <= 20):
            logger.error(f"Invalid to_level: {to_level}. Must be 1-20.")
            return False

        session = self.get_session()
        try:
            # Find all words matching the criteria
            query = session.query(Lemma).filter(
                Lemma.difficulty_level == from_level,
                Lemma.pos_subtype == subtype,
                Lemma.guid.isnot(None)
            )

            matching_words = query.all()

            if not matching_words:
                print(f"No words found with level {from_level} and subtype '{subtype}'")
                return True

            print(f"Found {len(matching_words)} words with level {from_level} and subtype '{subtype}':")
            print("-" * 80)

            # Display the words that will be affected
            for word in matching_words:
                status = "✓" if word.verified else "?"
                print(f"{status} {word.guid:<10} L{word.difficulty_level:<2} "
                      f"{word.lemma_text:<20} → {word.lithuanian_translation or 'N/A':<20}")

            if dry_run:
                print(f"\n[DRY RUN] Would move {len(matching_words)} words from level {from_level} to level {to_level}")
                return True

            # Confirm the operation
            print(f"\nThis will move {len(matching_words)} words from level {from_level} to level {to_level}")
            if reason:
                print(f"Reason: {reason}")

            if not get_user_confirmation("Continue?"):
                print("Operation cancelled.")
                return False

            # Perform the bulk update
            updated_count = 0
            timestamp = datetime.now().strftime("%Y-%m-%d")

            for word in matching_words:
                try:
                    old_level = word.difficulty_level
                    word.difficulty_level = to_level

                    # Add to notes if reason provided
                    if reason:
                        current_notes = word.notes or ""
                        level_note = f"[{timestamp}] Bulk level change from {old_level} to {to_level}: {reason}"
                        word.notes = f"{current_notes}\n{level_note}".strip()

                    updated_count += 1

                except Exception as e:
                    logger.error(f"Error updating word {word.guid}: {e}")
                    continue

            # Commit all changes
            session.commit()

            print(f"\n✅ Successfully moved {updated_count} words from level {from_level} to level {to_level}")
            if reason:
                print(f"   Reason: {reason}")

            return True

        except Exception as e:
            session.rollback()
            logger.error(f"Error moving words: {e}")
            return False
        finally:
            session.close()

    def update_word(self, identifier: str, auto_approve: bool = False, model: str = "gpt-5-mini") -> bool:
        """
        Update an entire Lemma entry using specified model.

        Args:
            identifier: GUID or English word to update
            auto_approve: Skip user review if True
            model: LLM model to use for analysis

        Returns:
            Success flag
        """
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

            print(f"Updating word: {lemma.lemma_text} ({lemma.guid})")
            print(f"Current Lithuanian: {lemma.lithuanian_translation}")

            # Query LLM for updated word data using specified model
            print(f"Analyzing word '{lemma.lemma_text}' with {model}...")
            word_data, success = self._query_word_data(
                lemma.lemma_text,
                lemma.lithuanian_translation,
                model_override=model
            )

            if not success or not word_data:
                logger.error(f"Failed to get updated analysis for word '{lemma.lemma_text}'")
                return False

            # User review (unless auto-approve)
            if not auto_approve:
                display_current_lemma_entry(lemma)
                review = self._get_user_review(word_data)

                if not review.approved:
                    logger.info(f"Word update for '{lemma.lemma_text}' rejected by user: {review.notes}")
                    return False

                # Apply modifications
                for key, value in review.modifications.items():
                    setattr(word_data, key, value)

            # Update the lemma with new data
            old_values = {
                'lithuanian_translation': lemma.lithuanian_translation,
                'definition_text': lemma.definition_text,
                'pos_type': lemma.pos_type,
                'pos_subtype': lemma.pos_subtype,
                'chinese_translation': lemma.chinese_translation,
                'korean_translation': lemma.korean_translation,
                'french_translation': lemma.french_translation,
                'swahili_translation': lemma.swahili_translation,
                'vietnamese_translation': lemma.vietnamese_translation,
                'confidence': lemma.confidence,
                'notes': lemma.notes
            }

            # Update all fields
            lemma.lithuanian_translation = word_data.lithuanian
            lemma.definition_text = word_data.definition
            lemma.pos_type = word_data.pos_type
            lemma.pos_subtype = word_data.pos_subtype
            lemma.chinese_translation = word_data.chinese_translation
            lemma.korean_translation = word_data.korean_translation
            lemma.french_translation = word_data.french_translation
            lemma.swahili_translation = word_data.swahili_translation
            lemma.vietnamese_translation = word_data.vietnamese_translation
            lemma.confidence = word_data.confidence
            lemma.verified = not auto_approve  # Mark as verified if user reviewed

            # Add update note with LLM notes
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            current_notes = lemma.notes or ""
            update_note = f"[{timestamp}] Updated with {model}"

            # Include LLM notes if available
            if word_data.notes:
                update_note += f": {word_data.notes}"

            lemma.notes = f"{current_notes}\n{update_note}".strip()

            # Update derivative forms if needed
            # Find existing English and Lithuanian base forms
            english_form = session.query(DerivativeForm).filter(
                DerivativeForm.lemma_id == lemma.id,
                DerivativeForm.language_code == 'en',
                DerivativeForm.is_base_form == True
            ).first()

            lithuanian_form = session.query(DerivativeForm).filter(
                DerivativeForm.lemma_id == lemma.id,
                DerivativeForm.language_code == 'lt',
                DerivativeForm.is_base_form == True
            ).first()

            # Update English form if it exists and changed
            if english_form and english_form.derivative_form_text != word_data.english:
                english_token = add_word_token(session, word_data.english, 'en')
                english_form.derivative_form_text = word_data.english
                english_form.word_token_id = english_token.id
                english_form.grammatical_form = self._get_default_grammatical_form(word_data.pos_type)
                english_form.verified = not auto_approve

            # Update Lithuanian form if it exists and changed
            if lithuanian_form and lithuanian_form.derivative_form_text != word_data.lithuanian:
                lithuanian_token = add_word_token(session, word_data.lithuanian, 'lt')
                lithuanian_form.derivative_form_text = word_data.lithuanian
                lithuanian_form.word_token_id = lithuanian_token.id
                lithuanian_form.grammatical_form = self._get_default_grammatical_form(word_data.pos_type)
                lithuanian_form.verified = not auto_approve

            # Create Lithuanian form if it doesn't exist but we have translation
            elif not lithuanian_form and word_data.lithuanian:
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

            # Track alternate forms that will be added
            added_alternatives = {'english': [], 'lithuanian': []}

            # Add alternate forms (skip any with parentheses)
            if word_data.alternatives:
                # Process English alternatives
                if 'english' in word_data.alternatives and word_data.alternatives['english']:
                    for alt_form in word_data.alternatives['english']:
                        # Skip forms with parentheses
                        if '(' in alt_form or ')' in alt_form:
                            continue

                        # Check if this alternative form already exists
                        existing_alt = session.query(DerivativeForm).filter(
                            DerivativeForm.lemma_id == lemma.id,
                            DerivativeForm.language_code == 'en',
                            DerivativeForm.derivative_form_text == alt_form
                        ).first()

                        if not existing_alt:
                            # Add the alternative form
                            alt_token = add_word_token(session, alt_form, 'en')
                            alt_derivative = DerivativeForm(
                                lemma_id=lemma.id,
                                derivative_form_text=alt_form,
                                word_token_id=alt_token.id,
                                language_code='en',
                                grammatical_form=self._get_default_grammatical_form(word_data.pos_type),
                                is_base_form=False,  # Alternative forms are not base forms
                                verified=not auto_approve
                            )
                            session.add(alt_derivative)
                            added_alternatives['english'].append(alt_form)

                # Process Lithuanian alternatives
                if 'lithuanian' in word_data.alternatives and word_data.alternatives['lithuanian']:
                    for alt_form in word_data.alternatives['lithuanian']:
                        # Skip forms with parentheses
                        if '(' in alt_form or ')' in alt_form:
                            continue

                        # Check if this alternative form already exists
                        existing_alt = session.query(DerivativeForm).filter(
                            DerivativeForm.lemma_id == lemma.id,
                            DerivativeForm.language_code == 'lt',
                            DerivativeForm.derivative_form_text == alt_form
                        ).first()

                        if not existing_alt:
                            # Add the alternative form
                            alt_token = add_word_token(session, alt_form, 'lt')
                            alt_derivative = DerivativeForm(
                                lemma_id=lemma.id,
                                derivative_form_text=alt_form,
                                word_token_id=alt_token.id,
                                language_code='lt',
                                grammatical_form=self._get_default_grammatical_form(word_data.pos_type),
                                is_base_form=False,  # Alternative forms are not base forms
                                verified=not auto_approve
                            )
                            session.add(alt_derivative)
                            added_alternatives['lithuanian'].append(alt_form)

            session.commit()

            print(f"\n✅ Successfully updated word '{lemma.lemma_text}' ({lemma.guid})")

            # Show what changed
            changes = []
            for field, old_value in old_values.items():
                new_value = getattr(lemma, field)
                if old_value != new_value:
                    changes.append(f"   {field}: '{old_value}' → '{new_value}'")

            # Add information about added alternate forms
            if added_alternatives['english']:
                changes.append(f"   Added English alternatives: {', '.join(added_alternatives['english'])}")
            if added_alternatives['lithuanian']:
                changes.append(f"   Added Lithuanian alternatives: {', '.join(added_alternatives['lithuanian'])}")

            if changes:
                print("Changes made:")
                for change in changes:
                    print(change)
            else:
                print("   No changes detected (data was already up to date)")

            return True

        except Exception as e:
            session.rollback()
            logger.error(f"Error updating word '{identifier}': {e}")
            return False
        finally:
            session.close()
