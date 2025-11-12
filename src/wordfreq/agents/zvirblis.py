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
from wordfreq.storage.translation_helpers import get_translation, get_all_translations

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
        model: str = "gpt-5-mini"
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

        # Get a database session for translation lookups
        session = self.get_session()
        try:
            # Get translations for the noun in target languages
            noun_translations = {}
            for lang_code in target_languages:
                if lang_code == 'en':
                    # For English, use the lemma text itself
                    noun_translations[lang_code] = lemma.lemma_text
                else:
                    translation = get_translation(session, lemma, lang_code)
                    if translation:
                        noun_translations[lang_code] = translation

            # Build context for LLM
            context = self._build_sentence_context(lemma, difficulty_context)

            # Generate sentences one at a time using LLM
            generated_sentences = []
            previous_sentences = []

            for i in range(num_sentences):
                logger.info(f"Generating sentence {i+1}/{num_sentences} for {lemma.lemma_text}")

                result = self._call_llm_for_sentence(
                    lemma=lemma,
                    noun_translations=noun_translations,
                    target_languages=target_languages,
                    context=context,
                    previous_sentences=previous_sentences
                )

                if not result:
                    logger.error(f"LLM failed to generate sentence {i+1} for {lemma.lemma_text}")
                    # Continue with what we have so far
                    break

                # Result is the sentence data directly (no nesting)
                generated_sentences.append(result)

                # Add to previous sentences for context
                english_text = result.get('translations', {}).get('en', '')
                if english_text:
                    previous_sentences.append(english_text)

            if not generated_sentences:
                logger.error(f"LLM failed to generate any sentences for {lemma.lemma_text}")
                return {
                    'success': False,
                    'error': 'LLM generation failed'
                }

            return {
                'success': True,
                'sentences': generated_sentences,
                'lemma_guid': lemma.guid
            }

        except Exception as e:
            logger.error(f"Error generating sentences for {lemma.lemma_text}: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
        finally:
            session.close()

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

    def _call_llm_for_sentence(
        self,
        lemma: Lemma,
        noun_translations: Dict[str, str],
        target_languages: List[str],
        context: str,
        previous_sentences: List[str] = None
    ) -> Optional[Dict]:
        """
        Call LLM to generate a single sentence.

        Args:
            lemma: Lemma object
            noun_translations: Dictionary of language_code -> translation
            target_languages: List of language codes
            context: Context string with word information
            previous_sentences: List of previously generated sentences for variety

        Returns:
            Dictionary with generated sentence or None if failed
        """
        # Build the prompt
        langs_str = ", ".join(target_languages)
        translations_str = json.dumps(noun_translations, indent=2)

        # Include previous sentences if any
        previous_context = ""
        if previous_sentences:
            previous_context = "\n\nPreviously generated sentences (make sure this new sentence is different):\n" + "\n".join(f"- {s}" for s in previous_sentences)

        prompt = f"""Generate 1 English example sentence for language learning that features the following noun.

{context}

Translations of the noun in target languages:
{translations_str}
{previous_context}

Requirements:
1. Create 1 ENGLISH sentence using the noun "{lemma.lemma_text}"
2. Vary the sentence pattern (SVO, SOV, etc.) and use different verbs/contexts
3. Keep sentences simple and natural (appropriate for language learners)
4. Use common, everyday vocabulary for other words in the sentence
5. Translate the English sentence to ALL target languages: {langs_str}
   - Provide natural, idiomatic translations (not word-for-word)
   - Ensure grammatical correctness in each language

For the sentence, provide:
- Pattern type (SVO, SVAO, etc.) - based on English structure
- Tense used (present, past, future)
- Translations in all languages (keys are language codes like 'en', 'lt', etc.)
- For EACH target language sentence, list ALL words in order with their:
  - The actual word/phrase as it appears (e.g., "Le chocolat", "초콜릿은")
  - English translation of this word/phrase (e.g., "the chocolate", "chocolate")
  - Base/lemma form in that language (e.g., "chocolat", "초콜릿")
  - Role in sentence (subject, verb, object, adjective, preposition, article, etc.)
  - For nouns/adjectives: grammatical case (e.g., "accusative", "nominative")
  - For verbs: grammatical form (e.g., "3s_present", "1s_past")
  - English lemma for vocabulary linking (e.g., "chocolate", "melt", "sun")

Important: List words in the order they appear in that language's sentence, not English order.
Include ALL words including articles, prepositions, particles.

Focus on variety, natural language usage, and accurate translations."""

        # Build translations and words_by_language properties dynamically
        # OpenAI strict mode doesn't support dynamic maps, so we create explicit properties
        translations_properties = {}
        words_by_language_properties = {}

        for lang_code in target_languages:
            translations_properties[lang_code] = {
                "type": "string",
                "description": f"Sentence in {lang_code}"
            }

            # Define word list schema for this language
            words_by_language_properties[f"words_{lang_code}"] = {
                "type": "array",
                "description": f"All words in the {lang_code} sentence, in order",
                "items": {
                    "type": "object",
                    "properties": {
                        "word": {"type": "string", "description": "The word/phrase as it appears in sentence"},
                        "english": {"type": "string", "description": "English translation of this word"},
                        "lemma": {"type": "string", "description": "Base/lemma form in this language"},
                        "role": {"type": "string", "description": "Role in sentence"},
                        "grammatical_form": {"type": "string", "description": "Grammatical form (e.g., '3s_present')"},
                        "grammatical_case": {"type": "string", "description": "Grammatical case if applicable"},
                        "english_lemma": {"type": "string", "description": "English lemma for linking to vocabulary"}
                    },
                    "required": ["word", "english", "lemma", "role"]
                }
            }

        # Build a nested Schema for translations since it has explicit properties
        translations_schema_props = {}
        for lang_code, lang_def in translations_properties.items():
            translations_schema_props[lang_code] = SchemaProperty(
                type=lang_def["type"],
                description=lang_def.get("description", "")
            )

        translations_schema = Schema(
            name="Translations",
            description="Sentence in each language",
            properties=translations_schema_props
        )

        # Define response schema for a single sentence
        # Put all properties at the top level (no nesting) for simplicity
        top_level_properties = {
            "translations": SchemaProperty(
                type="object",
                description="Sentence in each language",
                object_schema=translations_schema
            ),
            "pattern": SchemaProperty(
                type="string",
                description="Sentence pattern type (SVO, SVAO, etc.)"
            ),
            "tense": SchemaProperty(
                type="string",
                description="Verb tense (present, past, future)"
            )
        }

        # Add per-language word lists
        for lang_code in target_languages:
            if lang_code == 'en':
                continue  # Skip English
            words_key = f"words_{lang_code}"
            top_level_properties[words_key] = SchemaProperty(
                type="array",
                description=f"All words in the {lang_code} sentence, in order",
                items=words_by_language_properties[words_key]
            )

        schema = Schema(
            name="SentenceGeneration",
            description="Generated sentence with grammatical analysis",
            properties=top_level_properties
        )

        try:
            response = self.llm_client.generate_chat(
                prompt=prompt,
                model=self.model,
                json_schema=schema,
                timeout=60  # 60 seconds for web UX - reasonable for single sentence
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
            Dictionary with storage results including sentence IDs
        """
        stored_count = 0
        failed_count = 0
        errors = []
        sentence_ids = []

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

                # Add word linkages for each language
                # Get list of languages from translations
                translations = sentence_data.get('translations', {})
                for lang_code in translations.keys():
                    if lang_code == 'en':
                        continue  # Skip English, we only store target language words

                    # Get the words list for this language
                    words_key = f'words_{lang_code}'
                    words_used = sentence_data.get(words_key, [])

                    # Flatten if LLM returned nested structure (array of arrays instead of array of objects)
                    flattened_words = []
                    for item in words_used:
                        if isinstance(item, list):
                            # If item is a list, extend with its contents
                            flattened_words.extend(item)
                        elif isinstance(item, dict):
                            # If item is already a dict, append it
                            flattened_words.append(item)
                        else:
                            logger.error(f"Unexpected item type in {words_key}: {type(item)}")

                    words_used = flattened_words

                    for position, word_data in enumerate(words_used):
                        if not isinstance(word_data, dict):
                            logger.error(f"Expected dict at position {position} in {words_key}, got {type(word_data)}: {word_data}")
                            continue
                        # Try to find the lemma by matching the English lemma
                        english_lemma = word_data.get('english_lemma')
                        word_lemma = None
                        if english_lemma:
                            word_lemma = self._find_lemma_for_word(
                                session,
                                english_lemma,
                                word_data.get('role'),
                                source_lemma=source_lemma
                            )

                        add_sentence_word(
                            session=session,
                            sentence=sentence,
                            position=position,
                            word_role=word_data.get('role', 'unknown'),
                            lemma=word_lemma,
                            english_text=word_data.get('english'),
                            target_language_text=word_data.get('lemma'),
                            grammatical_form=word_data.get('grammatical_form'),
                            grammatical_case=word_data.get('grammatical_case'),
                            declined_form=word_data.get('word'),
                            language_code=lang_code
                        )

                # Calculate minimum difficulty level (for potential future use)
                # but hard-code all new sentences to level -1 (disabled by default)
                calculate_minimum_level(session, sentence)
                sentence.minimum_level = -1
                min_level = -1

                session.flush()
                stored_count += 1
                sentence_ids.append(sentence.id)

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
            'errors': errors,
            'sentence_ids': sentence_ids
        }

    def _find_lemma_for_word(
        self,
        session,
        word_text: str,
        word_role: str,
        source_lemma: Optional[Lemma] = None
    ) -> Optional[Lemma]:
        """
        Try to find a lemma matching a word.

        Args:
            session: Database session
            word_text: Word text (lemma form)
            word_role: Role in sentence (helps with POS filtering)
            source_lemma: The lemma this sentence was generated for (helps with disambiguation)

        Returns:
            Lemma object if found, None otherwise
        """
        if not word_text:
            return None

        # FIRST: If this word matches the source lemma (ignoring disambiguation), use the source lemma
        # This handles cases like "mouse (computer)" where the word is "mouse"
        if source_lemma:
            # Strip disambiguation from source lemma text to compare
            source_text = source_lemma.lemma_text
            # Remove parenthetical disambiguation if present
            if '(' in source_text:
                source_base = source_text.split('(')[0].strip()
            else:
                source_base = source_text

            # Check if word matches the base text of source lemma
            if word_text.lower() == source_base.lower():
                logger.debug(f"Matched word '{word_text}' to source lemma: {source_lemma.guid} ({source_lemma.lemma_text})")
                return source_lemma

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


def get_argument_parser():
    """Return the argument parser for introspection.

    This function allows external tools to introspect the available
    command-line arguments without executing the main function.
    """
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
        default='gpt-5-mini',
        help='LLM model to use (default: gpt-5-mini)'
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

    return parser


def main():
    """Main entry point for the sentence generation agent."""
    parser = get_argument_parser()
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
