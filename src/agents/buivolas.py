#!/usr/bin/env python3
"""
Buivolas - Simple Pattern Sentence Generation Agent

This agent generates simple pattern-based sentences for language learning,
translating them into multiple languages and storing them in the database
with proper word linkages.

"Buivolas" means "water buffalo" in Lithuanian - muscular and traveling in herds,
like the large batches of sentences this agent generates!

Usage:
  # Generate sentences for specific patterns
  python buivolas.py --patterns where_is_noun my_noun_is_color --languages lt zh --limit 5

  # Generate sentences for all patterns
  python buivolas.py --all-patterns --languages lt zh fr --limit 10

  # Dry run (don't save to database)
  python buivolas.py --patterns where_is_noun --languages lt --limit 3 --dry-run
"""

import argparse
import logging
import random
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import constants
import util.prompt_loader
from clients.unified_client import UnifiedLLMClient
from clients.types import Schema, SchemaProperty
from wordfreq.patterns.simple_patterns import SIMPLE_PATTERNS
from wordfreq.storage.database import create_database_session
from wordfreq.storage.models.schema import (
    Lemma,
    LemmaTranslation,
    Sentence,
    SentenceTranslation,
    SentenceWord,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Language name mappings for prompts
LANGUAGE_NAMES = {
    "en": "English",
    "lt": "Lithuanian",
    "zh": "Chinese",
    "fr": "French",
    "ko": "Korean",
    "de": "German",
    "es": "Spanish",
    "pt": "Portuguese",
}

# Language column mapping for direct translation columns
LANGUAGE_COLUMN_MAP = {
    "zh": "chinese_translation",
    "ko": "korean_translation",
    "fr": "french_translation",
    "lt": "lithuanian_translation",
}


class BuivolasAgent:
    """Agent for generating pattern-based simple sentences."""

    def __init__(
        self,
        db_path: str = None,
        model: str = "gpt-4o-mini",
        debug: bool = False,
        dry_run: bool = False,
    ):
        """
        Initialize the Buivolas agent.

        Args:
            db_path: Database path (uses default if None)
            model: LLM model to use for translations
            debug: Enable debug logging
            dry_run: Don't save to database
        """
        self.db_path = db_path or constants.WORDFREQ_DB_PATH
        self.model = model
        self.debug = debug
        self.dry_run = dry_run

        if debug:
            logger.setLevel(logging.DEBUG)

        # Initialize LLM client
        self.llm = UnifiedLLMClient(debug=debug)

    def get_session(self):
        """Get database session."""
        return create_database_session(self.db_path)

    def get_lemmas_for_slot(
        self, session, slot: Dict, limit: int = None
    ) -> List[Tuple[Lemma, str]]:
        """
        Get lemmas matching a slot specification.

        Args:
            session: Database session
            slot: Slot specification dict
            limit: Max number to return

        Returns:
            List of (lemma, guid) tuples
        """
        query = session.query(Lemma).filter(
            Lemma.guid.isnot(None),
            Lemma.pos_type == slot["pos_type"],
        )

        # Filter by subtype if specified
        if slot.get("pos_subtype"):
            query = query.filter(Lemma.pos_subtype == slot["pos_subtype"])

        # Filter by difficulty range
        if slot.get("min_level"):
            query = query.filter(Lemma.difficulty_level >= slot["min_level"])
        if slot.get("max_level"):
            query = query.filter(Lemma.difficulty_level <= slot["max_level"])

        lemmas = query.all()

        # Return limited random sample
        if limit and len(lemmas) > limit:
            lemmas = random.sample(lemmas, limit)

        return [(lemma, lemma.guid) for lemma in lemmas]

    def get_translation(self, session, lemma: Lemma, language_code: str) -> Optional[str]:
        """
        Get translation for a lemma in a specific language.

        Args:
            session: Database session
            lemma: Lemma object
            language_code: Language code (e.g., "lt", "zh")

        Returns:
            Translation text or None if not available
        """
        # English is the lemma text itself
        if language_code == "en":
            return lemma.lemma_text

        # Check column-based translations
        if language_code in LANGUAGE_COLUMN_MAP:
            column_name = LANGUAGE_COLUMN_MAP[language_code]
            return getattr(lemma, column_name, None)

        # Check table-based translations (es, de, pt)
        translation = (
            session.query(LemmaTranslation)
            .filter_by(lemma_id=lemma.id, language_code=language_code)
            .first()
        )
        return translation.translation if translation else None

    def fill_pattern_slots(
        self, session, pattern: Dict, limit_per_slot: int = 10
    ) -> List[Dict]:
        """
        Generate multiple combinations by filling pattern slots with lemmas.

        Args:
            session: Database session
            pattern: Pattern definition
            limit_per_slot: Max lemmas to get per slot

        Returns:
            List of filled pattern dictionaries
        """
        # Get lemmas for each slot
        slot_lemmas = {}
        for slot in pattern["slots"]:
            lemmas = self.get_lemmas_for_slot(session, slot, limit=limit_per_slot)
            if not lemmas:
                logger.warning(
                    f"No lemmas found for slot {slot['name']} (pos_type={slot['pos_type']})"
                )
                return []
            slot_lemmas[slot["name"]] = lemmas

        # Generate combinations
        # For now, just create one sentence per unique lemma in the first slot
        # This avoids combinatorial explosion
        combinations = []
        primary_slot = pattern["slots"][0]["name"]

        for lemma, guid in slot_lemmas[primary_slot]:
            combination = {"pattern_id": pattern["pattern_id"], "lemmas": {}}

            # Add the primary slot lemma
            combination["lemmas"][primary_slot] = (lemma, guid)

            # For other slots, pick random lemmas
            for slot in pattern["slots"][1:]:
                slot_name = slot["name"]
                if slot_lemmas[slot_name]:
                    combination["lemmas"][slot_name] = random.choice(slot_lemmas[slot_name])

            combinations.append(combination)

        return combinations

    def translate_pattern_sentence(
        self,
        pattern: Dict,
        filled_slots: Dict[str, Tuple[Lemma, str]],
        target_languages: List[str],
    ) -> Dict:
        """
        Translate a pattern-filled sentence to multiple languages using LLM.

        Args:
            pattern: Pattern definition
            filled_slots: Dict mapping slot names to (Lemma, guid) tuples
            target_languages: List of language codes to translate to

        Returns:
            Dictionary with translations and metadata
        """
        # Build English template with actual words
        session = self.get_session()
        try:
            en_words = {}
            for slot_name, (lemma, guid) in filled_slots.items():
                en_words[slot_name] = lemma.lemma_text

            # Replace placeholders in template
            en_sentence = pattern["en_template"]
            for slot_name, word in en_words.items():
                en_sentence = en_sentence.replace(f"[{slot_name}]", word)

            logger.info(f"Translating: {en_sentence}")

            # Build word context for LLM (helps with accuracy)
            word_translations = {}
            for slot_name, (lemma, guid) in filled_slots.items():
                word_translations[slot_name] = {}
                for lang in target_languages:
                    if lang != "en":
                        trans = self.get_translation(session, lemma, lang)
                        if trans:
                            word_translations[slot_name][lang] = trans

            # Format prompt
            prompt = f"""You are translating a simple language learning sentence into multiple languages.

English sentence: {en_sentence}

Word translations for reference:
"""
            for slot_name, translations in word_translations.items():
                prompt += f"\n{en_words[slot_name]}:"
                for lang, trans in translations.items():
                    prompt += f" {LANGUAGE_NAMES[lang]}={trans},"

            prompt += f"""

Please translate this sentence naturally into the following languages: {", ".join([LANGUAGE_NAMES[lang] for lang in target_languages if lang != "en"])}.

Keep the translations simple and natural for language learners. Use the provided word translations where appropriate, but adjust grammar (cases, verb forms, articles, etc.) as needed for natural, grammatically correct sentences.
"""

            # Build response schema
            properties = {}
            for lang_code in target_languages:
                if lang_code != "en":
                    properties[lang_code] = SchemaProperty(
                        type="string",
                        description=f"Natural translation in {LANGUAGE_NAMES[lang_code]}",
                    )

            schema = Schema(
                name="Translations",
                description="Sentence translations in multiple languages",
                strict=True,
                properties=properties,
                required=list(properties.keys()),
            )

            # Call LLM
            response = self.llm.generate(
                prompt=prompt, model=self.model, response_schema=schema
            )

            if not response.success:
                logger.error(f"Translation failed: {response.error}")
                return {"success": False, "error": response.error}

            # Parse translations
            translations = {"en": en_sentence}
            if response.structured_output:
                translations.update(response.structured_output)

            return {
                "success": True,
                "translations": translations,
                "lemmas": filled_slots,
                "pattern_id": pattern["pattern_id"],
            }

        finally:
            session.close()

    def save_sentence(self, session, result: Dict) -> Optional[Sentence]:
        """
        Save a generated sentence to the database.

        Args:
            session: Database session
            result: Translation result dictionary

        Returns:
            Sentence object or None if save failed
        """
        if self.dry_run:
            logger.info("[DRY RUN] Would save sentence:")
            for lang, text in result["translations"].items():
                logger.info(f"  {lang}: {text}")
            return None

        try:
            # Create Sentence record
            sentence = Sentence(
                pattern_type=result.get("pattern_type"),
                source_filename=f"pattern:{result['pattern_id']}",
                verified=False,
            )
            session.add(sentence)
            session.flush()  # Get sentence ID

            # Add translations
            for lang_code, translation_text in result["translations"].items():
                translation = SentenceTranslation(
                    sentence_id=sentence.id,
                    language_code=lang_code,
                    translation_text=translation_text,
                    verified=False,
                )
                session.add(translation)

            # Add word links
            position = 0
            for slot_name, (lemma, guid) in result["lemmas"].items():
                for lang_code in result["translations"].keys():
                    word_text = self.get_translation(session, lemma, lang_code)
                    if word_text:
                        sentence_word = SentenceWord(
                            sentence_id=sentence.id,
                            lemma_id=lemma.id,
                            language_code=lang_code,
                            position=position,
                            word_role=slot_name,
                            english_text=lemma.lemma_text,
                            target_language_text=word_text,
                        )
                        session.add(sentence_word)
                position += 1

            session.commit()
            logger.info(f"Saved sentence {sentence.id}: {result['translations']['en']}")
            return sentence

        except Exception as e:
            logger.error(f"Failed to save sentence: {e}")
            session.rollback()
            return None

    def generate_for_pattern(
        self, pattern: Dict, languages: List[str], limit: int = 10
    ) -> Dict:
        """
        Generate sentences for a specific pattern.

        Args:
            pattern: Pattern definition
            languages: Target languages
            limit: Maximum number of sentences to generate

        Returns:
            Dictionary with generation results
        """
        logger.info(f"Generating sentences for pattern: {pattern['pattern_id']}")

        session = self.get_session()
        try:
            # Fill pattern slots with lemmas
            combinations = self.fill_pattern_slots(session, pattern, limit_per_slot=limit)

            if not combinations:
                return {
                    "pattern_id": pattern["pattern_id"],
                    "success": False,
                    "error": "No valid lemma combinations found",
                }

            logger.info(f"Generated {len(combinations)} combinations")

            # Translate each combination
            results = {
                "pattern_id": pattern["pattern_id"],
                "total": len(combinations),
                "success_count": 0,
                "error_count": 0,
                "sentences": [],
            }

            for i, combo in enumerate(combinations[:limit], 1):
                logger.info(
                    f"[{i}/{min(len(combinations), limit)}] Translating combination..."
                )

                translation_result = self.translate_pattern_sentence(
                    pattern, combo["lemmas"], languages
                )

                if translation_result["success"]:
                    # Add pattern type to result
                    translation_result["pattern_type"] = pattern.get("pattern_type")

                    # Save to database
                    sentence = self.save_sentence(session, translation_result)

                    if sentence or self.dry_run:
                        results["success_count"] += 1
                        results["sentences"].append(translation_result)
                    else:
                        results["error_count"] += 1
                else:
                    results["error_count"] += 1
                    logger.error(f"Translation failed: {translation_result.get('error')}")

            return results

        finally:
            session.close()

    def generate_all_patterns(self, languages: List[str], limit_per_pattern: int = 10) -> Dict:
        """
        Generate sentences for all defined patterns.

        Args:
            languages: Target languages
            limit_per_pattern: Max sentences per pattern

        Returns:
            Dictionary with overall results
        """
        logger.info(f"Generating sentences for {len(SIMPLE_PATTERNS)} patterns")

        overall_results = {
            "patterns_processed": 0,
            "total_sentences": 0,
            "total_success": 0,
            "total_errors": 0,
            "pattern_results": [],
        }

        for pattern in SIMPLE_PATTERNS:
            result = self.generate_for_pattern(pattern, languages, limit=limit_per_pattern)
            overall_results["patterns_processed"] += 1
            overall_results["total_sentences"] += result.get("total", 0)
            overall_results["total_success"] += result.get("success_count", 0)
            overall_results["total_errors"] += result.get("error_count", 0)
            overall_results["pattern_results"].append(result)

        return overall_results


def get_argument_parser():
    """Return the argument parser for introspection."""
    parser = argparse.ArgumentParser(
        description="Buivolas - Simple Pattern Sentence Generation Agent"
    )
    parser.add_argument("--db-path", help="Database path (uses default if not specified)")
    parser.add_argument(
        "--model", default="gpt-4o-mini", help="LLM model to use (default: gpt-4o-mini)"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--dry-run", action="store_true", help="Don't save to database (for testing)"
    )

    # Pattern selection
    pattern_group = parser.add_mutually_exclusive_group(required=True)
    pattern_group.add_argument(
        "--patterns", nargs="+", help="Specific pattern IDs to generate"
    )
    pattern_group.add_argument(
        "--all-patterns", action="store_true", help="Generate for all patterns"
    )

    # Language and limits
    parser.add_argument(
        "--languages",
        nargs="+",
        required=True,
        choices=["en", "lt", "zh", "ko", "fr", "de", "es", "pt"],
        help="Target languages (en is always included)",
    )
    parser.add_argument(
        "--limit", type=int, default=10, help="Max sentences per pattern (default: 10)"
    )

    return parser


def main():
    """Main entry point for the buivolas agent."""
    parser = get_argument_parser()
    args = parser.parse_args()

    # Ensure 'en' is in languages
    if "en" not in args.languages:
        args.languages.insert(0, "en")

    # Create agent
    agent = BuivolasAgent(
        db_path=args.db_path, model=args.model, debug=args.debug, dry_run=args.dry_run
    )

    # Generate sentences
    if args.all_patterns:
        results = agent.generate_all_patterns(
            languages=args.languages, limit_per_pattern=args.limit
        )

        # Print summary
        logger.info("=" * 80)
        logger.info("BUIVOLAS AGENT REPORT - Pattern Sentence Generation")
        logger.info("=" * 80)
        logger.info(f"Patterns processed: {results['patterns_processed']}")
        logger.info(f"Total sentences: {results['total_sentences']}")
        logger.info(f"Successful: {results['total_success']}")
        logger.info(f"Errors: {results['total_errors']}")
        logger.info(f"Languages: {', '.join(args.languages)}")
        if args.dry_run:
            logger.info("DRY RUN - No database changes made")
        logger.info("=" * 80)

    else:
        # Get pattern definitions
        pattern_dict = {p["pattern_id"]: p for p in SIMPLE_PATTERNS}
        patterns_to_generate = []

        for pattern_id in args.patterns:
            if pattern_id in pattern_dict:
                patterns_to_generate.append(pattern_dict[pattern_id])
            else:
                logger.error(f"Unknown pattern: {pattern_id}")
                available = ", ".join(pattern_dict.keys())
                logger.error(f"Available patterns: {available}")
                sys.exit(1)

        # Generate for each pattern
        total_success = 0
        total_errors = 0

        for pattern in patterns_to_generate:
            result = agent.generate_for_pattern(pattern, args.languages, limit=args.limit)
            total_success += result.get("success_count", 0)
            total_errors += result.get("error_count", 0)

        # Print summary
        logger.info("=" * 80)
        logger.info("BUIVOLAS AGENT REPORT - Pattern Sentence Generation")
        logger.info("=" * 80)
        logger.info(f"Patterns: {', '.join(args.patterns)}")
        logger.info(f"Successful: {total_success}")
        logger.info(f"Errors: {total_errors}")
        logger.info(f"Languages: {', '.join(args.languages)}")
        if args.dry_run:
            logger.info("DRY RUN - No database changes made")
        logger.info("=" * 80)


if __name__ == "__main__":
    sys.exit(main())
