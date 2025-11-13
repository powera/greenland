#!/usr/bin/env python3
"""
Bebras Agent - Core logic for sentence-word link management.

This module handles the extraction of vocabulary words from sentences,
word-to-lemma matching, and database linking.
"""

import json
import logging
from typing import Dict, List, Optional, Tuple

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
    calculate_minimum_level
)

logger = logging.getLogger(__name__)


class BebrasAgent:
    """Agent for managing sentence-word links."""

    def __init__(
        self,
        db_path: str = None,
        debug: bool = False,
        model: str = "gpt-5-mini"
    ):
        """
        Initialize the Bebras agent.

        Args:
            db_path: Database path (uses default if None)
            debug: Enable debug logging
            model: LLM model to use for word extraction
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

    def analyze_sentence(
        self,
        sentence_text: str,
        source_language: str = "en",
        context: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Analyze a sentence to extract vocabulary words and their metadata.

        Args:
            sentence_text: The sentence to analyze (e.g., "I eat a banana")
            source_language: Source language code (default: "en")
            context: Optional context about the sentence

        Returns:
            Dictionary with analysis results including extracted words
        """
        logger.info(f"Analyzing sentence: {sentence_text}")

        # Build the prompt for LLM
        prompt = self._build_analysis_prompt(sentence_text, source_language, context)

        # Define response schema
        schema = self._build_analysis_schema()

        try:
            response = self.llm_client.generate_chat(
                prompt=prompt,
                model=self.model,
                json_schema=schema,
                timeout=60
            )

            if response.structured_data:
                result = response.structured_data
                logger.info(f"Extracted {len(result.get('words', []))} words from sentence")
                return {
                    'success': True,
                    'sentence_text': sentence_text,
                    'analysis': result
                }
            else:
                logger.error("No structured data received from LLM")
                return {
                    'success': False,
                    'error': 'LLM did not return structured data'
                }

        except Exception as e:
            logger.error(f"Error analyzing sentence: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }

    def _build_analysis_prompt(
        self,
        sentence_text: str,
        source_language: str,
        context: Optional[str]
    ) -> str:
        """Build the LLM prompt for sentence analysis."""
        # Load prompt templates
        prompt_context = util.prompt_loader.get_context("wordfreq", "sentence_analysis")
        prompt_template = util.prompt_loader.get_prompt("wordfreq", "sentence_analysis")

        # Format the prompt with parameters
        context_info = f"\n\nContext: {context}" if context else ""
        formatted_prompt = prompt_template.format(
            sentence_text=sentence_text,
            source_language=source_language,
            context_info=context_info
        )

        # Combine context (system instructions) and user prompt
        combined_prompt = f"{prompt_context}\n\n{formatted_prompt}"
        return combined_prompt

    def _build_analysis_schema(self) -> Schema:
        """Build the response schema for sentence analysis."""
        properties = {
            "pattern": SchemaProperty(
                type="string",
                description="Sentence pattern (e.g., SVO, SVAO)"
            ),
            "tense": SchemaProperty(
                type="string",
                description="Main verb tense (present, past, future)"
            ),
            "words": SchemaProperty(
                type="array",
                description="List of content words in the sentence",
                items={
                    "type": "object",
                    "properties": {
                        "word": {
                            "type": "string",
                            "description": "Word as it appears in sentence"
                        },
                        "lemma": {
                            "type": "string",
                            "description": "Base form/lemma of the word"
                        },
                        "pos": {
                            "type": "string",
                            "description": "Part of speech (noun, verb, adjective, adverb)"
                        },
                        "role": {
                            "type": "string",
                            "description": "Role in sentence (subject, verb, object, etc.)"
                        },
                        "disambiguation": {
                            "type": "string",
                            "description": "Context or disambiguation hint"
                        },
                        "grammatical_form": {
                            "type": "string",
                            "description": "Grammatical form (e.g., plural, past_tense)"
                        }
                    },
                    "required": ["word", "lemma", "pos", "role"]
                }
            )
        }

        return Schema(
            name="SentenceAnalysis",
            description="Analysis of sentence with extracted vocabulary words",
            properties=properties
        )

    def link_sentence_to_words(
        self,
        sentence: 'Sentence',
        analysis: Dict,
        source_language: str = "en",
        target_languages: Optional[List[str]] = None,
        session=None
    ) -> Dict[str, any]:
        """
        Link a sentence to its vocabulary words in the database.

        Args:
            sentence: Sentence object to link words to
            analysis: Analysis result from analyze_sentence()
            source_language: Source language code
            target_languages: Optional list of target languages for translation
            session: Database session (creates one if None)

        Returns:
            Dictionary with linking results
        """
        close_session = False
        if session is None:
            session = self.get_session()
            close_session = True

        try:
            from .disambiguation import find_best_lemma_match

            words = analysis.get('words', [])
            linked_count = 0
            unlinked_count = 0
            disambiguation_needed = []

            for position, word_data in enumerate(words):
                lemma_text = word_data.get('lemma')
                pos = word_data.get('pos')
                disambiguation_hint = word_data.get('disambiguation', '')

                # Try to find matching lemma
                lemma = find_best_lemma_match(
                    session=session,
                    lemma_text=lemma_text,
                    pos=pos,
                    disambiguation_hint=disambiguation_hint
                )

                if lemma:
                    linked_count += 1
                    logger.info(f"Linked '{lemma_text}' to lemma {lemma.guid} ({lemma.lemma_text})")
                else:
                    unlinked_count += 1
                    logger.warning(f"No lemma found for '{lemma_text}' (POS: {pos})")
                    disambiguation_needed.append({
                        'word': lemma_text,
                        'pos': pos,
                        'hint': disambiguation_hint
                    })

                # Create SentenceWord record
                add_sentence_word(
                    session=session,
                    sentence=sentence,
                    position=position,
                    word_role=word_data.get('role', 'unknown'),
                    lemma=lemma,
                    english_text=lemma_text,
                    target_language_text=lemma_text,  # Will be updated with translations
                    grammatical_form=word_data.get('grammatical_form'),
                    language_code=source_language
                )

            session.commit()

            return {
                'success': True,
                'linked_count': linked_count,
                'unlinked_count': unlinked_count,
                'disambiguation_needed': disambiguation_needed
            }

        except Exception as e:
            logger.error(f"Error linking sentence to words: {e}", exc_info=True)
            session.rollback()
            return {
                'success': False,
                'error': str(e)
            }
        finally:
            if close_session:
                session.close()

    def process_sentence(
        self,
        sentence_text: str,
        source_language: str = "en",
        target_languages: Optional[List[str]] = None,
        context: Optional[str] = None,
        verified: bool = False
    ) -> Dict[str, any]:
        """
        Complete pipeline: analyze sentence, create database records, and link words.

        Args:
            sentence_text: The sentence to process
            source_language: Source language code (default: "en")
            target_languages: List of target language codes for translations
            context: Optional context about the sentence
            verified: Whether the sentence is verified

        Returns:
            Dictionary with processing results including sentence_id
        """
        logger.info(f"Processing sentence: {sentence_text}")

        # Step 1: Analyze the sentence
        analysis_result = self.analyze_sentence(
            sentence_text=sentence_text,
            source_language=source_language,
            context=context
        )

        if not analysis_result.get('success'):
            return analysis_result

        analysis = analysis_result['analysis']

        # Step 2: Create sentence record
        session = self.get_session()
        try:
            sentence = add_sentence(
                session=session,
                pattern_type=analysis.get('pattern'),
                tense=analysis.get('tense'),
                source_filename="bebras_import",
                verified=verified,
                notes=context
            )

            # Step 3: Add source language translation
            add_sentence_translation(
                session=session,
                sentence=sentence,
                language_code=source_language,
                translation_text=sentence_text,
                verified=verified
            )

            # Step 4: Add target language translations if requested
            if target_languages:
                from .translation import ensure_translations
                ensure_translations(
                    session=session,
                    sentence=sentence,
                    source_text=sentence_text,
                    source_language=source_language,
                    target_languages=target_languages,
                    model=self.model
                )

            session.flush()

            # Step 5: Link sentence to words
            link_result = self.link_sentence_to_words(
                sentence=sentence,
                analysis=analysis,
                source_language=source_language,
                target_languages=target_languages,
                session=session
            )

            # Step 6: Calculate minimum difficulty level
            calculate_minimum_level(session, sentence)

            session.commit()

            return {
                'success': True,
                'sentence_id': sentence.id,
                'sentence_text': sentence_text,
                'linked_words': link_result.get('linked_count', 0),
                'unlinked_words': link_result.get('unlinked_count', 0),
                'disambiguation_needed': link_result.get('disambiguation_needed', []),
                'minimum_level': sentence.minimum_level
            }

        except Exception as e:
            logger.error(f"Error processing sentence: {e}", exc_info=True)
            session.rollback()
            return {
                'success': False,
                'error': str(e)
            }
        finally:
            session.close()

    def process_sentence_batch(
        self,
        sentences: List[str],
        source_language: str = "en",
        target_languages: Optional[List[str]] = None,
        verified: bool = False
    ) -> Dict[str, any]:
        """
        Process multiple sentences in batch.

        Args:
            sentences: List of sentences to process
            source_language: Source language code
            target_languages: Target language codes for translations
            verified: Whether sentences are verified

        Returns:
            Dictionary with batch processing results
        """
        logger.info(f"Processing batch of {len(sentences)} sentences")

        results = []
        success_count = 0
        failure_count = 0

        for i, sentence_text in enumerate(sentences, 1):
            logger.info(f"[{i}/{len(sentences)}] Processing: {sentence_text}")

            result = self.process_sentence(
                sentence_text=sentence_text,
                source_language=source_language,
                target_languages=target_languages,
                verified=verified
            )

            results.append(result)

            if result.get('success'):
                success_count += 1
            else:
                failure_count += 1

        logger.info(f"Batch complete: {success_count} succeeded, {failure_count} failed")

        return {
            'total': len(sentences),
            'success_count': success_count,
            'failure_count': failure_count,
            'results': results
        }
