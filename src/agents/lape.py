#!/usr/bin/env python3
"""
Lape - Grammar Facts Generator Agent

This agent generates language-specific grammatical facts for lemmas using LLM queries.
It supports various types of grammar facts that can be specified via command line parameters.

Currently supported fact types:
- measure_words (Chinese): Generate appropriate measure words/classifiers for nouns

Future expansions (commented examples):
- grammatical_gender (French, Spanish, German, etc.): Determine noun gender (masculine, feminine, neuter)
- number_type (English, etc.): Identify plurale tantum (scissors, pants) or singulare tantum (furniture, information)
- declension_class (Lithuanian, Latin, etc.): Determine which declension pattern a noun follows
- verb_aspect (Russian, Polish, etc.): Identify perfective vs imperfective verb pairs
- honorific_level (Japanese, Korean): Determine appropriate honorific/politeness level
- tone_pattern (Vietnamese, Thai): Identify tone patterns for words
- definiteness (Arabic, Hebrew): Whether nouns are definite or indefinite by default
- animacy (Russian, Czech): Whether nouns are animate or inanimate (affects grammar)

"Lape" means "fox" in Lithuanian - clever and precise in analyzing grammar!
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
from wordfreq.storage.database import create_database_session
from wordfreq.storage.models.schema import Lemma
from wordfreq.storage.crud.grammar_fact import (
    add_grammar_fact,
    get_grammar_fact_value,
    get_grammar_facts
)
from wordfreq.storage.crud.operation_log import log_operation
from wordfreq.storage.translation_helpers import get_translation
from wordfreq.translation.client import LinguisticClient
from clients.unified_client import UnifiedLLMClient
from clients.types import Schema, SchemaProperty

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class LapeAgent:
    """Agent for generating grammar facts for lemmas."""

    # Language-specific gender systems configuration
    GENDER_SYSTEMS = {
        "fr": {
            "name": "French",
            "genders": ["masculine", "feminine"],
            "description": "2-way system (masculine/feminine)"
        },
        "lt": {
            "name": "Lithuanian",
            "genders": ["masculine", "feminine"],
            "description": "2-way system (masculine/feminine)"
        },
        "es": {
            "name": "Spanish",
            "genders": ["masculine", "feminine"],
            "description": "2-way system (masculine/feminine)"
        },
        "de": {
            "name": "German",
            "genders": ["masculine", "feminine", "neuter"],
            "description": "3-way system (masculine/feminine/neuter)"
        },
        "pt": {
            "name": "Portuguese",
            "genders": ["masculine", "feminine"],
            "description": "2-way system (masculine/feminine)"
        },
        "ru": {
            "name": "Russian",
            "genders": ["masculine", "feminine", "neuter"],
            "description": "3-way system (masculine/feminine/neuter)"
        },
        "it": {
            "name": "Italian",
            "genders": ["masculine", "feminine"],
            "description": "2-way system (masculine/feminine)"
        },
    }

    # Supported fact types and their required parameters
    SUPPORTED_FACT_TYPES = {
        "measure_words": {
            "languages": ["zh"],  # Chinese only for now
            "required_pos": ["noun"],
            "description": "Generate Chinese measure words/classifiers for nouns"
        },
        "grammatical_gender": {
            "languages": list(GENDER_SYSTEMS.keys()),
            "required_pos": ["noun"],
            "description": "Determine grammatical gender (masculine, feminine, neuter)"
        },
        # 'number_type': {
        #     'languages': ['en', 'lt', 'fr', 'es'],
        #     'required_pos': ['noun'],
        #     'description': 'Identify plurale tantum or singulare tantum nouns'
        # },
        # 'declension_class': {
        #     'languages': ['lt', 'la', 'ru', 'de'],
        #     'required_pos': ['noun', 'adjective'],
        #     'description': 'Determine declension class/pattern'
        # },
    }

    def __init__(self, db_path: str = None, debug: bool = False, model: str = None):
        """
        Initialize the Lape agent.

        Args:
            db_path: Database path (uses default if None)
            debug: Enable debug logging
            model: LLM model to use (default: gpt-5-mini)
        """
        self.db_path = db_path or constants.WORDFREQ_DB_PATH
        self.debug = debug
        self.model = model or "gpt-5-mini"
        self.linguistic_client = None  # Lazy initialization
        self.llm_client = None  # For direct LLM calls

        if debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self):
        """Get database session."""
        return create_database_session(self.db_path)

    def get_linguistic_client(self):
        """Get or create linguistic client for LLM queries."""
        if self.linguistic_client is None:
            self.linguistic_client = LinguisticClient(
                model=self.model,
                db_path=self.db_path,
                debug=self.debug
            )
        return self.linguistic_client

    def get_llm_client(self):
        """Get or create LLM client for direct queries."""
        if self.llm_client is None:
            self.llm_client = UnifiedLLMClient(debug=self.debug)
            self.llm_client.warm_model(self.model)
        return self.llm_client

    def generate_measure_words(
        self,
        lemma: Lemma,
        chinese_translation: str,
        session=None
    ) -> Tuple[Optional[str], Optional[str], float]:
        """
        Generate Chinese measure word(s) for a noun using LLM.

        Args:
            lemma: The Lemma object
            chinese_translation: The Chinese translation of the word
            session: Database session (optional)

        Returns:
            Tuple of (measure_word, explanation, confidence)
        """
        if lemma.pos_type != "noun":
            logger.warning(f"Lemma '{lemma.lemma_text}' is not a noun, skipping measure word generation")
            return None, None, 0.0

        # Load prompts
        try:
            context = util.prompt_loader.get_context("wordfreq", "measure_words")
            prompt_template = util.prompt_loader.get_prompt("wordfreq", "measure_words")
        except Exception as e:
            logger.error(f"Failed to load measure_words prompts: {e}")
            return None, None, 0.0

        # Format prompt
        prompt_text = prompt_template.format(
            english_word=lemma.lemma_text,
            chinese_translation=chinese_translation,
            pos_type=lemma.pos_type,
            definition=lemma.definition_text or "N/A"
        )

        # Define JSON schema for response
        schema = Schema(
            name="MeasureWordGeneration",
            description="Generate Chinese measure words/classifiers for nouns",
            properties={
                "primary_measure_word": SchemaProperty("string", "The primary/most common measure word"),
                "alternative_measure_words": SchemaProperty(
                    "array",
                    "List of alternative measure words that can also be used",
                    items={"type": "string"}
                ),
                "explanation": SchemaProperty("string", "Brief explanation of why this measure word is appropriate"),
                "confidence": SchemaProperty("number", "Confidence score 0.0-1.0", minimum=0.0, maximum=1.0)
            }
        )

        # Query LLM
        try:
            client = self.get_llm_client()
            response = client.generate_chat(
                prompt=prompt_text,
                model=self.model,
                json_schema=schema,
                context=context
            )

            # Extract structured data
            if response.structured_data:
                result = response.structured_data
            else:
                logger.error(f"No structured data received for '{lemma.lemma_text}'")
                return None, None, 0.0

            measure_word = result.get("primary_measure_word", None)
            alternatives = result.get("alternative_measure_words", [])
            explanation = result.get("explanation", "")
            confidence = float(result.get("confidence", 0.5))

            # Combine primary and alternatives
            if alternatives:
                all_measure_words = f"{measure_word} (alt: {', '.join(alternatives)})"
            else:
                all_measure_words = measure_word

            logger.info(
                f"Generated measure word for '{lemma.lemma_text}': {all_measure_words} "
                f"(confidence: {confidence:.2f})"
            )

            return measure_word, explanation, confidence

        except Exception as e:
            logger.error(f"Failed to generate measure word for '{lemma.lemma_text}': {e}")
            return None, None, 0.0

    def generate_grammatical_gender(
        self,
        lemma: Lemma,
        target_translation: str,
        language_code: str,
        session=None
    ) -> Tuple[Optional[str], Optional[str], float]:
        """
        Generate grammatical gender for a noun using LLM.

        Args:
            lemma: The Lemma object
            target_translation: The translation in the target language
            language_code: Target language code (e.g., 'fr', 'lt', 'de')
            session: Database session (optional)

        Returns:
            Tuple of (gender, explanation, confidence)
        """
        if lemma.pos_type != "noun":
            logger.warning(f"Lemma '{lemma.lemma_text}' is not a noun, skipping gender generation")
            return None, None, 0.0

        if language_code not in self.GENDER_SYSTEMS:
            logger.error(f"Language '{language_code}' does not have a configured gender system")
            return None, None, 0.0

        gender_config = self.GENDER_SYSTEMS[language_code]
        language_name = gender_config["name"]
        valid_genders = ", ".join(gender_config["genders"])
        gender_system = gender_config["description"]

        # Load prompts
        try:
            context = util.prompt_loader.get_context("wordfreq", "grammatical_gender")
            prompt_template = util.prompt_loader.get_prompt("wordfreq", "grammatical_gender")
        except Exception as e:
            logger.error(f"Failed to load grammatical_gender prompts: {e}")
            return None, None, 0.0

        # Format prompt
        prompt_text = prompt_template.format(
            english_word=lemma.lemma_text,
            target_translation=target_translation,
            pos_type=lemma.pos_type,
            definition=lemma.definition_text or "N/A",
            language_name=language_name,
            language_code=language_code,
            gender_system=gender_system,
            valid_genders=valid_genders
        )

        # Define JSON schema for response
        schema = Schema(
            name="GrammaticalGenderGeneration",
            description=f"Determine grammatical gender for {language_name} nouns",
            properties={
                "gender": SchemaProperty(
                    "string",
                    f"The grammatical gender: {valid_genders}",
                    enum=gender_config["genders"]
                ),
                "explanation": SchemaProperty(
                    "string",
                    "Brief explanation of why this gender is correct"
                ),
                "confidence": SchemaProperty(
                    "number",
                    "Confidence score 0.0-1.0",
                    minimum=0.0,
                    maximum=1.0
                )
            }
        )

        # Query LLM
        try:
            client = self.get_llm_client()
            response = client.generate_chat(
                prompt=prompt_text,
                model=self.model,
                json_schema=schema,
                context=context
            )

            # Extract structured data
            if response.structured_data:
                result = response.structured_data
            else:
                logger.error(f"No structured data received for '{lemma.lemma_text}'")
                return None, None, 0.0

            gender = result.get("gender", None)
            explanation = result.get("explanation", "")
            confidence = float(result.get("confidence", 0.5))

            logger.info(
                f"Generated gender for '{lemma.lemma_text}' ({target_translation}): "
                f"{gender} (confidence: {confidence:.2f})"
            )

            return gender, explanation, confidence

        except Exception as e:
            logger.error(f"Failed to generate gender for '{lemma.lemma_text}': {e}")
            return None, None, 0.0

    def generate_grammar_facts(
        self,
        fact_type: str,
        language_code: str,
        limit: Optional[int] = None,
        skip_existing: bool = True,
        min_confidence: float = 0.7,
        dry_run: bool = False
    ) -> Dict[str, any]:
        """
        Generate grammar facts for lemmas.

        Args:
            fact_type: Type of grammar fact to generate (e.g., 'measure_words')
            language_code: Language code (e.g., 'zh', 'fr')
            limit: Maximum number of lemmas to process
            skip_existing: Skip lemmas that already have this fact
            min_confidence: Minimum confidence to save the fact
            dry_run: If True, don't save to database

        Returns:
            Dictionary with generation results
        """
        # Validate fact type
        if fact_type not in self.SUPPORTED_FACT_TYPES:
            raise ValueError(
                f"Unsupported fact type: {fact_type}. "
                f"Supported types: {', '.join(self.SUPPORTED_FACT_TYPES.keys())}"
            )

        fact_config = self.SUPPORTED_FACT_TYPES[fact_type]

        # Validate language
        if language_code not in fact_config["languages"]:
            raise ValueError(
                f"Fact type '{fact_type}' does not support language '{language_code}'. "
                f"Supported languages: {', '.join(fact_config['languages'])}"
            )

        logger.info(f"Generating {fact_type} for language {language_code}...")
        if dry_run:
            logger.info("DRY RUN MODE - No changes will be saved")

        session = self.get_session()
        try:
            # Get lemmas that need this fact
            query = session.query(Lemma).filter(
                Lemma.pos_type.in_(fact_config["required_pos"])
            ).order_by(Lemma.id)

            if limit:
                query = query.limit(limit * 2)  # Get extra in case we skip some

            lemmas = query.all()
            logger.info(f"Found {len(lemmas)} candidate lemmas")

            # Process lemmas
            processed_count = 0
            skipped_count = 0
            success_count = 0
            failed_count = 0
            results = []

            for lemma in lemmas:
                if limit and processed_count >= limit:
                    break

                # Check if fact already exists
                if skip_existing:
                    existing_fact = get_grammar_fact_value(
                        session, lemma.id, language_code, fact_type
                    )
                    if existing_fact is not None:
                        skipped_count += 1
                        continue

                # Get translation for target language
                translation = get_translation(session, lemma, language_code)
                if not translation:
                    logger.debug(f"No {language_code} translation for '{lemma.lemma_text}', skipping")
                    skipped_count += 1
                    continue

                processed_count += 1
                logger.info(f"Processing {processed_count}/{limit or '∞'}: {lemma.lemma_text}")

                # Generate fact based on type
                if fact_type == "measure_words":
                    fact_value, notes, confidence = self.generate_measure_words(
                        lemma, translation, session
                    )
                elif fact_type == "grammatical_gender":
                    fact_value, notes, confidence = self.generate_grammatical_gender(
                        lemma, translation, language_code, session
                    )
                else:
                    # Placeholder for future fact types
                    logger.error(f"Fact type {fact_type} not yet implemented")
                    failed_count += 1
                    continue

                if fact_value and confidence >= min_confidence:
                    # Save to database (unless dry run)
                    if not dry_run:
                        add_grammar_fact(
                            session,
                            lemma_id=lemma.id,
                            language_code=language_code,
                            fact_type=fact_type,
                            fact_value=fact_value,
                            notes=notes,
                            verified=False
                        )
                        session.commit()

                        # Log operation
                        log_operation(
                            session,
                            operation_type="grammar_fact_generated",
                            entity_type="grammar_fact",
                            entity_id=lemma.id,
                            details={
                                "fact_type": fact_type,
                                "language_code": language_code,
                                "fact_value": fact_value,
                                "confidence": confidence,
                                "agent": "lape",
                                "model": self.model
                            }
                        )
                        session.commit()

                    success_count += 1
                    results.append({
                        "lemma_id": lemma.id,
                        "lemma_text": lemma.lemma_text,
                        "translation": translation,
                        "fact_value": fact_value,
                        "notes": notes,
                        "confidence": confidence
                    })
                    logger.info(f"  ✓ Generated: {fact_value} (confidence: {confidence:.2f})")
                else:
                    failed_count += 1
                    logger.warning(
                        f"  ✗ Failed or low confidence: {fact_value} (confidence: {confidence:.2f})"
                    )

            logger.info(
                f"Complete! Processed: {processed_count}, Success: {success_count}, "
                f"Failed: {failed_count}, Skipped: {skipped_count}"
            )

            return {
                "fact_type": fact_type,
                "language_code": language_code,
                "processed": processed_count,
                "success": success_count,
                "failed": failed_count,
                "skipped": skipped_count,
                "results": results,
                "dry_run": dry_run
            }

        except Exception as e:
            logger.error(f"Error generating grammar facts: {e}")
            if session:
                session.rollback()
            raise
        finally:
            if session:
                session.close()


def main():
    """Command-line interface for the Lape agent."""
    parser = argparse.ArgumentParser(
        description="Lape - Grammar Facts Generator Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate Chinese measure words for nouns
  python lape.py --fact-type measure_words --language zh --limit 10

  # Generate French grammatical gender for nouns
  python lape.py --fact-type grammatical_gender --language fr --limit 10

  # Generate Lithuanian grammatical gender for nouns
  python lape.py --fact-type grammatical_gender --language lt --limit 10

  # Dry run to see what would be generated
  python lape.py --fact-type grammatical_gender --language fr --limit 5 --dry-run

  # Generate for all lemmas without existing facts
  python lape.py --fact-type grammatical_gender --language fr

  # Use a different model
  python lape.py --fact-type grammatical_gender --language de --model gpt-5 --limit 10

Supported fact types:
  - measure_words: Chinese measure words/classifiers for nouns (languages: zh)
  - grammatical_gender: Noun gender (languages: fr, lt, es, de, pt, ru, it)

Future fact types (see code comments):
  - number_type: Plurale tantum or singulare tantum identification
  - declension_class: Declension pattern classification
  - verb_aspect: Perfective vs imperfective verbs
  - honorific_level: Politeness/honorific level
  - And more...
        """
    )

    parser.add_argument(
        "--fact-type",
        required=True,
        choices=LapeAgent.SUPPORTED_FACT_TYPES.keys(),
        help="Type of grammar fact to generate"
    )
    parser.add_argument(
        "--language",
        required=True,
        help="Language code (e.g., zh, fr, es)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of lemmas to process"
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip lemmas that already have this fact (default: True)"
    )
    parser.add_argument(
        "--no-skip-existing",
        dest="skip_existing",
        action="store_false",
        help="Process all lemmas, even if they have existing facts"
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.7,
        help="Minimum confidence score to save fact (default: 0.7)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without saving to database"
    )
    parser.add_argument(
        "--model",
        default="gpt-5-mini",
        help="LLM model to use (default: gpt-5-mini)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    parser.add_argument(
        "--db-path",
        help="Database path (default: from constants)"
    )

    args = parser.parse_args()

    # Create agent
    agent = LapeAgent(
        db_path=args.db_path,
        debug=args.debug,
        model=args.model
    )

    # Generate facts
    try:
        results = agent.generate_grammar_facts(
            fact_type=args.fact_type,
            language_code=args.language,
            limit=args.limit,
            skip_existing=args.skip_existing,
            min_confidence=args.min_confidence,
            dry_run=args.dry_run
        )

        # Print summary
        print("\n" + "=" * 60)
        print("GRAMMAR FACTS GENERATION SUMMARY")
        print("=" * 60)
        print(f"Fact Type: {results['fact_type']}")
        print(f"Language: {results['language_code']}")
        print(f"Processed: {results['processed']}")
        print(f"Success: {results['success']}")
        print(f"Failed: {results['failed']}")
        print(f"Skipped: {results['skipped']}")
        if results["dry_run"]:
            print("\n⚠️  DRY RUN - No changes saved to database")
        print("=" * 60)

        # Print some examples
        if results["results"]:
            print("\nSample results:")
            for i, result in enumerate(results["results"][:5], 1):
                print(f"{i}. {result['lemma_text']} ({result['translation']})")
                print(f"   → {result['fact_value']}")
                print(f"   Confidence: {result['confidence']:.2f}")
                if result["notes"]:
                    print(f"   Notes: {result['notes']}")

    except Exception as e:
        logger.error(f"Failed to generate grammar facts: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
