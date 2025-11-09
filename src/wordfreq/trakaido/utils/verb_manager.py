#!/usr/bin/env python3
"""
Verb management functionality for trakaido system.

Provides the VerbManager class for adding, updating, and managing verbs
in the trakaido database with conjugation/derivative forms.
"""

import logging
import sys
import os
from typing import Any, Dict, List, Optional, Tuple

# Add the src directory to the path for imports
GREENLAND_SRC_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
sys.path.append(GREENLAND_SRC_PATH)

import constants
import util.prompt_loader
from clients.types import Schema, SchemaProperty
from clients.unified_client import UnifiedLLMClient
from wordfreq.storage.database import (
    add_word_token,
    create_database_session,
)
from wordfreq.storage.models.schema import DerivativeForm, Lemma
from wordfreq.translation.client import LinguisticClient

from .data_models import WordData, ReviewResult
from .text_rendering import display_word_data

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class VerbManager:
    """Main class for managing trakaido verbs."""

    # GUID prefix for verbs
    VERB_GUID_PREFIX = "V01"

    def __init__(self, model: str = "gpt-5-mini", db_path: str = None, debug: bool = False):
        """
        Initialize the VerbManager.

        Args:
            model: LLM model to use (default: gpt-5-mini)
            db_path: Database path (uses default if None)
            debug: Enable debug logging
        """
        self.model = model
        self.db_path = db_path or constants.WORDFREQ_DB_PATH
        self.debug = debug
        self.client = UnifiedLLMClient(debug=debug)
        self.linguistic_client = LinguisticClient(model=model, debug=debug)

        if debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self):
        """Get database session."""
        return create_database_session(self.db_path)

    def _get_verb_analysis_prompt(self, english_verb: str, target_translation: str = None,
                                   language: str = 'lt') -> str:
        """Get the prompt for analyzing a new verb."""
        language_names = {
            'lt': 'Lithuanian',
            'zh': 'Chinese',
            'ko': 'Korean',
            'fr': 'French'
        }
        language_name = language_names.get(language, 'Lithuanian')

        context = util.prompt_loader.get_context("wordfreq", "word_analysis")
        prompt_template = util.prompt_loader.get_prompt("wordfreq", "word_analysis")

        if target_translation:
            word_specification = f"English verb '{english_verb}' with {language_name} translation '{target_translation}'"
            meaning_clarification = f"Focus on the specific meaning where '{english_verb}' translates to '{target_translation}' in {language_name}."
        else:
            word_specification = f"English verb '{english_verb}'"
            meaning_clarification = "Provide the most common, basic meaning of this verb."

        prompt = prompt_template.format(
            word_specification=word_specification,
            meaning_clarification=meaning_clarification,
            english_word=english_verb
        )

        return f"{context}\n\n{prompt}"

    def _query_verb_data(self, english_verb: str, target_translation: str = None,
                        language: str = 'lt', model_override: str = None) -> Tuple[Optional[WordData], bool]:
        """
        Query LLM for comprehensive verb data.

        Args:
            english_verb: English verb to analyze (should be infinitive form)
            target_translation: Optional translation in target language to clarify meaning
            language: Target language code (lt, zh, ko, fr)
            model_override: Override the default model

        Returns:
            Tuple of (WordData object, success flag)
        """
        language_field_names = {
            'lt': 'lithuanian',
            'zh': 'chinese',
            'ko': 'korean',
            'fr': 'french'
        }

        schema = Schema(
            name="VerbAnalysis",
            description="Comprehensive analysis of a verb for language learning",
            properties={
                "english": SchemaProperty("string", "The English verb being analyzed (infinitive form)"),
                "lithuanian": SchemaProperty("string", "Lithuanian translation of the verb (infinitive form)"),
                "pos_type": SchemaProperty("string", "Part of speech (should be 'verb')",
                    enum=["verb"]),
                "pos_subtype": SchemaProperty("string", "Verb subtype classification",
                    enum=["action", "state", "motion", "communication", "mental", "modal", "auxiliary", "other"]),
                "definition": SchemaProperty("string", "Clear definition for language learners"),
                "confidence": SchemaProperty("number", "Confidence score from 0.0-1.0",
                    minimum=0.0, maximum=1.0),
                "chinese_translation": SchemaProperty("string", "Chinese translation (infinitive/base form)"),
                "korean_translation": SchemaProperty("string", "Korean translation (infinitive/base form)"),
                "french_translation": SchemaProperty("string", "French translation (infinitive form)"),
                "swahili_translation": SchemaProperty("string", "Swahili translation (infinitive/base form)"),
                "vietnamese_translation": SchemaProperty("string", "Vietnamese translation (infinitive/base form)"),
                "alternatives": SchemaProperty(
                    type="object",
                    description="Alternative forms in different languages",
                    properties={
                        "english": SchemaProperty(
                            type="array",
                            description="Alternative English forms (synonyms)",
                            items={"type": "string"}
                        ),
                        "lithuanian": SchemaProperty(
                            type="array",
                            description="Alternative Lithuanian forms (synonyms)",
                            items={"type": "string"}
                        )
                    }
                ),
                "notes": SchemaProperty("string", "Additional notes about the verb (e.g., transitivity, irregular conjugations)")
            }
        )

        prompt = self._get_verb_analysis_prompt(english_verb, target_translation, language)

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
                    english=data.get('english', english_verb),
                    lithuanian=data.get('lithuanian', target_translation or ''),
                    pos_type='verb',  # Always verb
                    pos_subtype=data.get('pos_subtype', 'action'),
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
                logger.error(f"No structured data received for verb '{english_verb}'")
                return None, False

        except Exception as e:
            logger.error(f"Error querying verb data for '{english_verb}': {e}")
            return None, False

    def _generate_guid(self, session) -> str:
        """
        Generate a unique GUID for a verb.

        Args:
            session: Database session

        Returns:
            Unique GUID string in format V01_###
        """
        # Find the next available number for verb prefix
        existing_guids = session.query(Lemma.guid).filter(
            Lemma.guid.like(f"{self.VERB_GUID_PREFIX}_%")
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

        return f"{self.VERB_GUID_PREFIX}_{next_number:03d}"

    def _get_user_review(self, data: WordData) -> ReviewResult:
        """
        Get user review and approval for verb data.

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
                new_translation = input(f"Target translation [{data.lithuanian}]: ").strip()
                if new_translation:
                    modifications['lithuanian'] = new_translation

                new_definition = input(f"Definition [{data.definition}]: ").strip()
                if new_definition:
                    modifications['definition'] = new_definition

                new_level = input("Difficulty Level (1-20, leave blank to set later): ").strip()
                if new_level and new_level.isdigit():
                    level = int(new_level)
                    if 1 <= level <= 20:
                        modifications['difficulty_level'] = level

                new_subtype = input(f"Verb subtype [{data.pos_subtype}]: ").strip()
                if new_subtype:
                    modifications['pos_subtype'] = new_subtype

                notes = input("Review notes: ").strip()

                return ReviewResult(approved=True, modifications=modifications, notes=notes)

            elif choice == '3':
                notes = input("Rejection reason: ").strip()
                return ReviewResult(approved=False, modifications={}, notes=notes)

            else:
                print("Invalid choice. Please enter 1, 2, or 3.")

    def _generate_conjugation_forms(self, lemma_id: int, language: str = 'lt') -> bool:
        """
        Generate conjugation forms for a verb using the LinguisticClient.

        Args:
            lemma_id: ID of the lemma to generate forms for
            language: Language code (lt, zh, ko, fr)

        Returns:
            Success flag
        """
        if language == 'zh':
            # Chinese verbs don't conjugate - skip this step
            logger.info("Skipping conjugation generation for Chinese (verbs don't conjugate)")
            return True

        if language == 'lt':
            # Use existing Lithuanian verb conjugation generator
            from wordfreq.translation.generate_lithuanian_verb_forms import process_lemma_conjugations
            return process_lemma_conjugations(self.linguistic_client, lemma_id, self.db_path)
        elif language == 'fr':
            # Use French verb conjugation generator
            from wordfreq.translation.generate_french_verb_forms import process_lemma_conjugations as process_french
            return process_french(self.linguistic_client, lemma_id, self.db_path)
        elif language == 'ko':
            # Korean verbs conjugate - would need a generator similar to Lithuanian/French
            logger.warning(f"Korean verb conjugation not yet implemented for lemma {lemma_id}")
            return True
        else:
            logger.warning(f"Unknown language '{language}' for conjugation generation")
            return True

    def add_verb(self, english_verb: str, target_translation: str = None,
                 difficulty_level: int = None, auto_approve: bool = False,
                 language: str = 'lt', generate_forms: bool = True) -> bool:
        """
        Add a new verb to the trakaido system.

        Args:
            english_verb: English verb to add (should be infinitive: "to eat", "eat", etc.)
            target_translation: Optional translation in target language to clarify meaning
            difficulty_level: Optional difficulty level (1-20)
            auto_approve: Skip user review if True
            language: Target language code (lt, zh, ko, fr)
            generate_forms: Whether to generate conjugation forms (default: True)

        Returns:
            Success flag
        """
        # Normalize English verb to infinitive form (remove "to " if present)
        if english_verb.startswith("to "):
            english_verb = english_verb[3:]

        logger.info(f"Adding verb: {english_verb}" +
                   (f" → {target_translation}" if target_translation else ""))

        session = self.get_session()
        try:
            # Check if verb already exists
            existing = session.query(Lemma).filter(
                Lemma.lemma_text.ilike(english_verb),
                Lemma.pos_type == 'verb'
            ).first()

            if existing:
                print(f"Verb '{english_verb}' already exists in database with GUID: {existing.guid}")
                return False

            # Query LLM for verb data
            print(f"Analyzing verb '{english_verb}' with {self.model}...")
            verb_data, success = self._query_verb_data(english_verb, target_translation, language)

            if not success or not verb_data:
                logger.error(f"Failed to get analysis for verb '{english_verb}'")
                return False

            # User review (unless auto-approve)
            if not auto_approve:
                review = self._get_user_review(verb_data)

                if not review.approved:
                    logger.info(f"Verb '{english_verb}' rejected by user: {review.notes}")
                    return False

                # Apply modifications
                for key, value in review.modifications.items():
                    setattr(verb_data, key, value)

            # Use provided difficulty level or default to 1 if not set
            final_difficulty_level = difficulty_level or getattr(verb_data, 'difficulty_level', None) or 1

            # Generate GUID
            guid = self._generate_guid(session)

            # Create lemma with all translation fields
            lemma = Lemma(
                lemma_text=verb_data.english,
                definition_text=verb_data.definition,
                pos_type='verb',
                pos_subtype=verb_data.pos_subtype,
                guid=guid,
                difficulty_level=final_difficulty_level,
                lithuanian_translation=verb_data.lithuanian,
                chinese_translation=verb_data.chinese_translation,
                korean_translation=verb_data.korean_translation,
                french_translation=verb_data.french_translation,
                swahili_translation=verb_data.swahili_translation,
                vietnamese_translation=verb_data.vietnamese_translation,
                confidence=verb_data.confidence,
                notes=verb_data.notes,
                verified=not auto_approve  # Mark as verified if user reviewed
            )

            session.add(lemma)
            session.flush()  # Get the ID

            # Create English derivative form (infinitive/base form)
            english_token = add_word_token(session, verb_data.english, 'en')
            english_form = DerivativeForm(
                lemma_id=lemma.id,
                derivative_form_text=verb_data.english,
                word_token_id=english_token.id,
                language_code='en',
                grammatical_form='infinitive',
                is_base_form=True,
                verified=not auto_approve
            )
            session.add(english_form)

            # Create target language derivative form (infinitive/base form)
            if verb_data.lithuanian:
                target_token = add_word_token(session, verb_data.lithuanian, language)
                target_form = DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text=verb_data.lithuanian,
                    word_token_id=target_token.id,
                    language_code=language,
                    grammatical_form='infinitive',
                    is_base_form=True,
                    verified=not auto_approve
                )
                session.add(target_form)

            # Add alternative forms (synonyms)
            for alt_english in verb_data.alternatives.get('english', []):
                if alt_english != verb_data.english:
                    alt_token = add_word_token(session, alt_english, 'en')
                    alt_form = DerivativeForm(
                        lemma_id=lemma.id,
                        derivative_form_text=alt_english,
                        word_token_id=alt_token.id,
                        language_code='en',
                        grammatical_form='synonym',
                        is_base_form=False,
                        verified=not auto_approve
                    )
                    session.add(alt_form)

            for alt_target in verb_data.alternatives.get('lithuanian', []):
                if alt_target != verb_data.lithuanian:
                    alt_token = add_word_token(session, alt_target, language)
                    alt_form = DerivativeForm(
                        lemma_id=lemma.id,
                        derivative_form_text=alt_target,
                        word_token_id=alt_token.id,
                        language_code=language,
                        grammatical_form='synonym',
                        is_base_form=False,
                        verified=not auto_approve
                    )
                    session.add(alt_form)

            session.commit()

            logger.info(f"✅ Successfully added verb '{english_verb}' with GUID {guid}")

            # Generate conjugation forms if requested
            if generate_forms:
                logger.info(f"Generating conjugation forms for {language}...")
                forms_success = self._generate_conjugation_forms(lemma.id, language)
                if forms_success:
                    logger.info(f"✅ Successfully generated conjugation forms")
                else:
                    logger.warning(f"⚠️  Failed to generate conjugation forms (verb added but forms missing)")

            return True

        except Exception as e:
            session.rollback()
            logger.error(f"Error adding verb '{english_verb}': {e}")
            return False
        finally:
            session.close()

    def list_verbs(self, language: str = 'lt', level: int = None, subtype: str = None,
                   limit: int = 50) -> List[Dict[str, Any]]:
        """
        List verbs in the database.

        Args:
            language: Filter by language (default: lt)
            level: Filter by difficulty level
            subtype: Filter by verb subtype
            limit: Maximum number of results

        Returns:
            List of verb dictionaries
        """
        session = self.get_session()
        try:
            language_field_map = {
                'lt': 'lithuanian_translation',
                'zh': 'chinese_translation',
                'ko': 'korean_translation',
                'fr': 'french_translation'
            }

            query = session.query(Lemma).filter(Lemma.pos_type == 'verb')

            # Filter by language (must have translation)
            if language in language_field_map:
                field = getattr(Lemma, language_field_map[language])
                query = query.filter(field.isnot(None), field != '')

            if level:
                query = query.filter(Lemma.difficulty_level == level)

            if subtype:
                query = query.filter(Lemma.pos_subtype == subtype)

            query = query.order_by(Lemma.guid).limit(limit)

            verbs = query.all()

            results = []
            for verb in verbs:
                translation = getattr(verb, language_field_map.get(language, 'lithuanian_translation'), '')
                results.append({
                    'guid': verb.guid,
                    'english': verb.lemma_text,
                    'translation': translation,
                    'language': language,
                    'level': verb.difficulty_level,
                    'subtype': verb.pos_subtype,
                    'verified': verb.verified
                })

            return results

        finally:
            session.close()
