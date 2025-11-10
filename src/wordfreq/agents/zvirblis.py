#!/usr/bin/env python3
"""
Žvirblis - Sentence Generation Agent

This agent autonomously generates example sentences for vocabulary words:
1. Takes a noun (lemma) as a starting point
2. Uses LLM to generate natural, contextual sentences
3. Creates sentences with the noun in different roles (subject, object)
4. Generates translations in multiple languages
5. Links sentences to vocabulary words via GUIDs
6. Calculates minimum difficulty level based on words used

"Žvirblis" means "sparrow" in Lithuanian - small but prolific, creating many examples!
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import constants
import util.prompt_loader
from clients.types import Schema, SchemaProperty
from clients.unified_client import UnifiedLLMClient
from wordfreq.storage.database import (
    create_database_session,
    Lemma,
    add_sentence,
    add_sentence_translation,
    add_sentence_word,
    calculate_minimum_level,
    find_lemma_by_guid
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ZvirblisAgent:
    """Agent for generating example sentences from vocabulary words."""

    def __init__(
        self,
        db_path: str = None,
        debug: bool = False,
        model: str = "gpt-4o-mini"
    ):
        """
        Initialize the Žvirblis agent.

        Args:
            db_path: Database path (uses default if None)
            debug: Enable debug logging
            model: LLM model to use for sentence generation
        """
        self.db_path = db_path or constants.WORDFREQ_DB_PATH
        self.debug = debug
        self.model = model
        self.llm_client = UnifiedLLMClient()

        if debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self):
        """Get database session."""
        return create_database_session(self.db_path)

    def generate_sentences_for_noun(
        self,
        lemma: Lemma,
        target_languages: List[str] = ['en', 'lt'],
        num_sentences: int = 3,
        difficulty_context: Optional[int] = None
    ) -> Dict[str, any]:
        """
        Generate example sentences featuring a specific noun.

        Args:
            lemma: Lemma object (should be a noun)
            target_languages: Languages to generate sentences in
            num_sentences: Number of sentences to generate (default: 3)
            difficulty_context: Optional difficulty level context for word selection

        Returns:
            Dictionary with generation results
        """
        if lemma.pos_type != "noun":
            logger.warning(f"Lemma {lemma.guid} is not a noun (got {lemma.pos_type})")
            return {
                'success': False,
                'error': f'Expected noun, got {lemma.pos_type}'
            }

        logger.info(f"Generating {num_sentences} sentences for noun: {lemma.lemma_text} (GUID: {lemma.guid})")

        # Get translations for the noun in target languages
        noun_translations = {}
        for lang_code in target_languages:
            translation = self._get_translation_for_language(lemma, lang_code)
            if translation:
                noun_translations[lang_code] = translation

        # Build context for LLM
        context = self._build_sentence_context(lemma, difficulty_context)

        # Generate sentences using LLM
        try:
            result = self._call_llm_for_sentences(
                lemma=lemma,
                noun_translations=noun_translations,
                target_languages=target_languages,
                num_sentences=num_sentences,
                context=context
            )

            if not result or not result.get('sentences'):
                logger.error(f"LLM failed to generate sentences for {lemma.lemma_text}")
                return {
                    'success': False,
                    'error': 'LLM generation failed'
                }

            return {
                'success': True,
                'sentences': result['sentences'],
                'lemma_guid': lemma.guid
            }

        except Exception as e:
            logger.error(f"Error generating sentences for {lemma.lemma_text}: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }

    def _get_translation_for_language(self, lemma: Lemma, language_code: str) -> Optional[str]:
        """Get translation for a lemma in a specific language."""
        # Try legacy columns first
        legacy_map = {
            'zh': lemma.chinese_translation,
            'fr': lemma.french_translation,
            'ko': lemma.korean_translation,
            'sw': lemma.swahili_translation,
            'lt': lemma.lithuanian_translation,
            'vi': lemma.vietnamese_translation
        }

        if language_code in legacy_map and legacy_map[language_code]:
            return legacy_map[language_code]

        # Try LemmaTranslation table
        for translation in lemma.translations:
            if translation.language_code == language_code:
                return translation.translation

        # For English, use the lemma text itself
        if language_code == 'en':
            return lemma.lemma_text

        return None

    def _build_sentence_context(self, lemma: Lemma, difficulty_level: Optional[int]) -> str:
        """Build context string for LLM prompt."""
        context_parts = [
            f"Word: {lemma.lemma_text}",
            f"Definition: {lemma.definition_text}",
            f"Part of Speech: {lemma.pos_type}"
        ]

        if difficulty_level:
            context_parts.append(f"Difficulty Level: {difficulty_level} (Trakaido level 1-20)")

        if lemma.disambiguation:
            context_parts.append(f"Disambiguation: {lemma.disambiguation}")

        return "\n".join(context_parts)

    def _call_llm_for_sentences(
        self,
        lemma: Lemma,
        noun_translations: Dict[str, str],
        target_languages: List[str],
        num_sentences: int,
        context: str
    ) -> Optional[Dict]:
        """
        Call LLM to generate sentences.

        Args:
            lemma: Lemma object
            noun_translations: Dictionary of language_code -> translation
            target_languages: List of language codes
            num_sentences: Number of sentences to generate
            context: Context string with word information

        Returns:
            Dictionary with generated sentences or None if failed
        """
        # Build the prompt
        langs_str = ", ".join(target_languages)
        translations_str = json.dumps(noun_translations, indent=2)

        prompt = f"""Generate {num_sentences} example sentences for language learning that feature the following noun.

{context}

Translations available:
{translations_str}

Requirements:
1. Create {num_sentences} different sentences using the noun "{lemma.lemma_text}"
2. Vary the sentence patterns:
   - Use the noun as a subject (e.g., "The book is on the table")
   - Use the noun as an object (e.g., "He read the book")
   - Include different verbs and contexts
3. Keep sentences simple and natural (appropriate for language learners)
4. Use common, everyday vocabulary for other words in the sentence
5. Provide translations for ALL languages: {langs_str}

For each sentence, also identify:
- Pattern type (SVO, SVAO, etc.)
- Tense used (present, past, future)
- ALL words used in the sentence with their:
  - Base form (lemma)
  - Role in sentence (subject, verb, object, adjective, preposition, article, etc.)
  - For nouns/adjectives: grammatical case if applicable
  - For verbs: grammatical form (e.g., "3s_present" = 3rd person singular present)

Focus on variety and natural language usage."""

        # Define response schema
        schema = Schema(
            name="SentenceGeneration",
            description="Generated sentences with grammatical analysis",
            properties={
                "sentences": SchemaProperty(
                    type="array",
                    description="List of generated sentences",
                    items={
                        "type": "object",
                        "properties": {
                            "translations": {
                                "type": "object",
                                "description": "Sentence in each language (keys are language codes)",
                                "additionalProperties": {"type": "string"}
                            },
                            "pattern": {
                                "type": "string",
                                "description": "Sentence pattern type (SVO, SVAO, etc.)"
                            },
                            "tense": {
                                "type": "string",
                                "description": "Verb tense (present, past, future)"
                            },
                            "words_used": {
                                "type": "array",
                                "description": "All words used in the sentence",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "lemma": {"type": "string", "description": "Base form of the word"},
                                        "role": {"type": "string", "description": "Role in sentence (subject, verb, object, etc.)"},
                                        "grammatical_form": {"type": "string", "description": "Form used (e.g., '3s_present', 'past_participle')"},
                                        "grammatical_case": {"type": "string", "description": "Case if applicable (nominative, accusative, etc.)"},
                                        "declined_form": {"type": "string", "description": "Actual form used in sentence"}
                                    },
                                    "required": ["lemma", "role"]
                                }
                            }
                        },
                        "required": ["translations", "pattern", "words_used"]
                    }
                )
            }
        )

        try:
            response = self.llm_client.generate_chat(
                prompt=prompt,
                model=self.model,
                json_schema=schema
            )

            if response.structured_data:
                return response.structured_data
            else:
                logger.error("No structured data received from LLM")
                return None

        except Exception as e:
            logger.error(f"Error calling LLM: {e}", exc_info=True)
            return None

    def store_sentences(
        self,
        sentences_data: List[Dict],
        source_lemma: Lemma,
        session
    ) -> Dict[str, any]:
        """
        Store generated sentences in the database.

        Args:
            sentences_data: List of sentence dictionaries from LLM
            source_lemma: The lemma these sentences were generated for
            session: Database session

        Returns:
            Dictionary with storage results
        """
        stored_count = 0
        failed_count = 0
        errors = []

        for sentence_data in sentences_data:
            try:
                # Create the sentence record
                sentence = add_sentence(
                    session=session,
                    pattern_type=sentence_data.get('pattern'),
                    tense=sentence_data.get('tense'),
                    source_filename=f"zvirblis_{source_lemma.guid}",
                    verified=False,
                    notes=f"Generated for {source_lemma.lemma_text} (GUID: {source_lemma.guid})"
                )

                # Add translations
                translations = sentence_data.get('translations', {})
                for lang_code, text in translations.items():
                    add_sentence_translation(
                        session=session,
                        sentence=sentence,
                        language_code=lang_code,
                        translation_text=text,
                        verified=False
                    )

                # Add word linkages
                words_used = sentence_data.get('words_used', [])
                for position, word_data in enumerate(words_used):
                    # Try to find the lemma by matching the base form
                    word_lemma = self._find_lemma_for_word(
                        session,
                        word_data.get('lemma'),
                        word_data.get('role')
                    )

                    add_sentence_word(
                        session=session,
                        sentence=sentence,
                        position=position,
                        word_role=word_data.get('role', 'unknown'),
                        lemma=word_lemma,
                        english_text=word_data.get('lemma'),
                        target_language_text=word_data.get('lemma'),
                        grammatical_form=word_data.get('grammatical_form'),
                        grammatical_case=word_data.get('grammatical_case'),
                        declined_form=word_data.get('declined_form')
                    )

                # Calculate minimum difficulty level
                min_level = calculate_minimum_level(session, sentence)

                session.flush()
                stored_count += 1

                logger.info(
                    f"✓ Stored sentence {sentence.id}: "
                    f"{translations.get('en', 'N/A')[:50]}... "
                    f"(level: {min_level or 'N/A'})"
                )

            except Exception as e:
                logger.error(f"Failed to store sentence: {e}", exc_info=True)
                failed_count += 1
                errors.append(str(e))
                session.rollback()

        # Commit all successful sentences
        if stored_count > 0:
            session.commit()

        return {
            'stored': stored_count,
            'failed': failed_count,
            'errors': errors
        }

    def _find_lemma_for_word(
        self,
        session,
        word_text: str,
        word_role: str
    ) -> Optional[Lemma]:
        """
        Try to find a lemma matching a word.

        Args:
            session: Database session
            word_text: Word text (lemma form)
            word_role: Role in sentence (helps with POS filtering)

        Returns:
            Lemma object if found, None otherwise
        """
        if not word_text:
            return None

        # Map roles to POS types
        role_to_pos = {
            'subject': 'noun',
            'object': 'noun',
            'verb': 'verb',
            'adjective': 'adjective',
            'adverb': 'adverb'
        }

        pos_hint = role_to_pos.get(word_role)

        # Try exact match first
        query = session.query(Lemma).filter(Lemma.lemma_text == word_text)

        if pos_hint:
            query = query.filter(Lemma.pos_type == pos_hint)

        lemma = query.first()

        if lemma:
            logger.debug(f"Found lemma for '{word_text}': {lemma.guid}")
            return lemma

        # Try case-insensitive match
        query = session.query(Lemma).filter(Lemma.lemma_text.ilike(word_text))

        if pos_hint:
            query = query.filter(Lemma.pos_type == pos_hint)

        lemma = query.first()

        if lemma:
            logger.debug(f"Found lemma (case-insensitive) for '{word_text}': {lemma.guid}")
            return lemma

        logger.debug(f"No lemma found for word '{word_text}' (role: {word_role})")
        return None

    def generate_for_difficulty_level(
        self,
        difficulty_level: int,
        limit: Optional[int] = None,
        sentences_per_noun: int = 3,
        target_languages: List[str] = ['en', 'lt'],
        dry_run: bool = False
    ) -> Dict[str, any]:
        """
        Generate sentences for all nouns at a specific difficulty level.

        Args:
            difficulty_level: Trakaido difficulty level (1-20)
            limit: Maximum number of nouns to process
            sentences_per_noun: Number of sentences to generate per noun
            target_languages: Languages to generate sentences in
            dry_run: If True, don't actually generate or store sentences

        Returns:
            Dictionary with generation statistics
        """
        logger.info(f"{'DRY RUN: ' if dry_run else ''}Generating sentences for difficulty level {difficulty_level}")

        session = self.get_session()
        try:
            # Query nouns at this difficulty level
            query = session.query(Lemma).filter(
                Lemma.pos_type == 'noun',
                Lemma.difficulty_level == difficulty_level
            ).order_by(Lemma.id)

            if limit:
                query = query.limit(limit)

            nouns = query.all()
            logger.info(f"Found {len(nouns)} nouns at level {difficulty_level}")

            if dry_run:
                return {
                    'nouns_found': len(nouns),
                    'sentences_generated': 0,
                    'sentences_stored': 0,
                    'dry_run': True
                }

            total_generated = 0
            total_stored = 0
            total_failed = 0

            for i, noun in enumerate(nouns, 1):
                logger.info(f"\n[{i}/{len(nouns)}] Processing: {noun.lemma_text} ({noun.guid})")

                # Generate sentences
                result = self.generate_sentences_for_noun(
                    lemma=noun,
                    target_languages=target_languages,
                    num_sentences=sentences_per_noun,
                    difficulty_context=difficulty_level
                )

                if result.get('success') and result.get('sentences'):
                    sentences = result['sentences']
                    total_generated += len(sentences)

                    # Store sentences
                    store_result = self.store_sentences(
                        sentences_data=sentences,
                        source_lemma=noun,
                        session=session
                    )

                    total_stored += store_result['stored']
                    total_failed += store_result['failed']

            logger.info(f"\n{'='*60}")
            logger.info(f"Generation complete!")
            logger.info(f"Nouns processed: {len(nouns)}")
            logger.info(f"Sentences generated: {total_generated}")
            logger.info(f"Sentences stored: {total_stored}")
            logger.info(f"Sentences failed: {total_failed}")
            logger.info(f"{'='*60}")

            return {
                'nouns_found': len(nouns),
                'sentences_generated': total_generated,
                'sentences_stored': total_stored,
                'sentences_failed': total_failed
            }

        except Exception as e:
            logger.error(f"Error in generation process: {e}", exc_info=True)
            return {
                'error': str(e),
                'nouns_found': 0,
                'sentences_generated': 0,
                'sentences_stored': 0
            }
        finally:
            session.close()


def main():
    """Main entry point for the sentence generation agent."""
    parser = argparse.ArgumentParser(
        description='Generate example sentences for vocabulary words'
    )
    parser.add_argument(
        '--guid',
        help='Generate sentences for a specific lemma GUID'
    )
    parser.add_argument(
        '--level',
        type=int,
        help='Generate sentences for all nouns at a specific difficulty level (1-20)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of nouns to process'
    )
    parser.add_argument(
        '--num-sentences',
        type=int,
        default=3,
        help='Number of sentences to generate per noun (default: 3)'
    )
    parser.add_argument(
        '--languages',
        nargs='+',
        default=['en', 'lt'],
        help='Target languages for generation (default: en lt)'
    )
    parser.add_argument(
        '--model',
        default='gpt-4o-mini',
        help='LLM model to use (default: gpt-4o-mini)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without actually generating sentences'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )

    args = parser.parse_args()

    # Initialize agent
    agent = ZvirblisAgent(debug=args.debug, model=args.model)

    if args.guid:
        # Generate for specific GUID
        session = agent.get_session()
        try:
            lemma = session.query(Lemma).filter(Lemma.guid == args.guid).first()

            if not lemma:
                logger.error(f"No lemma found with GUID: {args.guid}")
                return 1

            logger.info(f"Generating sentences for: {lemma.lemma_text} ({lemma.guid})")

            result = agent.generate_sentences_for_noun(
                lemma=lemma,
                target_languages=args.languages,
                num_sentences=args.num_sentences
            )

            if result.get('success') and result.get('sentences'):
                if not args.dry_run:
                    store_result = agent.store_sentences(
                        sentences_data=result['sentences'],
                        source_lemma=lemma,
                        session=session
                    )
                    logger.info(f"Stored: {store_result['stored']}, Failed: {store_result['failed']}")
                else:
                    logger.info(f"Would store {len(result['sentences'])} sentences (dry run)")
            else:
                logger.error(f"Generation failed: {result.get('error')}")
                return 1

        finally:
            session.close()

    elif args.level:
        # Generate for all nouns at difficulty level
        result = agent.generate_for_difficulty_level(
            difficulty_level=args.level,
            limit=args.limit,
            sentences_per_noun=args.num_sentences,
            target_languages=args.languages,
            dry_run=args.dry_run
        )

        if result.get('error'):
            logger.error(f"Generation failed: {result['error']}")
            return 1

    else:
        logger.error("Must specify either --guid or --level")
        parser.print_help()
        return 1

    return 0


if __name__ == '__main__':
    exit(main())
