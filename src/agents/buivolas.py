#!/usr/bin/env python3
"""
Buivolas - Simple Pattern Sentence Generation Agent

This agent generates simple pattern-based sentences for language learning,
creating candidate sentences and translating them into multiple languages
using batch processing.

"Buivolas" means "water buffalo" in Lithuanian - muscular and traveling in herds,
like the large batches of sentences this agent generates!

Workflow:
  1. Generate candidate sentences (all combinations) without translations
  2. Batch translate candidates into target languages

Usage:
  # Generate candidate sentences for specific patterns
  python buivolas.py generate-candidates --patterns where_is_noun my_noun_is_color --limit 100

  # Generate candidates for all patterns
  python buivolas.py generate-candidates --all-patterns --limit 1000

  # Submit batch translation job for untranslated sentences
  python buivolas.py submit-batch --languages lt zh fr --limit 500

  # Check status of batch jobs
  python buivolas.py check-batch --batch-id batch_xxx

  # Retrieve and apply batch translation results
  python buivolas.py retrieve-batch --batch-id batch_xxx
"""

import argparse
import itertools
import json
import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import constants
from agents.common_args import (
    add_common_args,
    add_llm_args,
    add_backend_args,
    get_backend_config,
)
from clients.batch_queue import (
    BatchQueueManager,
    BatchRequestMetadata,
    create_batch_database_session,
)
from clients.openai_batch_client import OpenAIBatchClient
from wordfreq.patterns.simple_patterns import SIMPLE_PATTERNS
from wordfreq.storage.backend import create_session as create_backend_session
from wordfreq.storage.backend.config import BackendConfig, BackendType
from wordfreq.storage.models.schema import (
    Lemma,
    LemmaTranslation,
    Sentence,
    SentenceTranslation,
    SentenceWord,
)
from wordfreq.storage.translation_helpers import get_translation, LANGUAGE_NAMES
from wordfreq.translation.sentence import (
    build_translation_prompt,
    build_response_schema,
    store_translation_results,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)



def strip_disambiguation(text: str) -> str:
    """
    Strip disambiguation info from lemma text.

    Removes parenthetical content from any position in the text.
    Examples:
        "mouse (computer)" -> "mouse"
        "they(f.) walk" -> "they walk"
        "(computer) monitor" -> "monitor"

    Args:
        text: Lemma text possibly containing parenthetical disambiguation

    Returns:
        Text with parenthetical content removed and extra spaces cleaned up
    """
    # Remove all parenthetical content (including the parentheses)
    result = re.sub(r'\s*\([^)]*\)\s*', ' ', text)
    # Clean up multiple spaces and strip
    result = re.sub(r'\s+', ' ', result).strip()
    return result


class BuivolasAgent:
    """Agent for generating pattern-based simple sentences."""

    def __init__(
        self,
        db_path: str = None,
        backend_config: BackendConfig = None,
        model: str = "gpt-4o-mini",
        debug: bool = False,
        dry_run: bool = False,
    ):
        """
        Initialize the Buivolas agent.

        Args:
            db_path: Database path (uses default if None) - for backward compatibility
            backend_config: Backend configuration (if provided, overrides db_path)
            model: LLM model to use for translations
            debug: Enable debug logging
            dry_run: Don't save to database
        """
        # Set up backend configuration
        if backend_config is not None:
            self.backend_config = backend_config
        elif db_path is not None:
            # Backward compatibility: db_path implies SQLite backend
            self.backend_config = BackendConfig(
                backend_type=BackendType.SQLITE, sqlite_path=db_path
            )
        else:
            # Use default SQLite path
            self.backend_config = BackendConfig(
                backend_type=BackendType.SQLITE, sqlite_path=constants.WORDFREQ_DB_PATH
            )

        # Keep db_path for backward compatibility
        if self.backend_config.backend_type == BackendType.SQLITE:
            self.db_path = self.backend_config.sqlite_path
        else:
            self.db_path = None

        self.model = model
        self.debug = debug
        self.dry_run = dry_run

        if debug:
            logger.setLevel(logging.DEBUG)

        # Initialize batch client and queue manager
        self.batch_client = OpenAIBatchClient(debug=debug)
        self.batch_session = create_batch_database_session()
        self.batch_manager = BatchQueueManager(self.batch_session, self.batch_client, debug=debug)

    def get_session(self):
        """Get database session using backend abstraction."""
        return create_backend_session(self.backend_config)

    def get_lemmas_for_slot(
        self, session, slot: Dict
    ) -> List[Tuple[Lemma, str]]:
        """
        Get all lemmas matching a slot specification.

        Args:
            session: Database session
            slot: Slot specification dict

        Returns:
            List of (lemma, guid) tuples
        """
        query = session.query(Lemma).filter(
            Lemma.guid.isnot(None),
            Lemma.pos_type == slot["pos_type"],
        )

        # Filter by subtype - if specified, only match that subtype
        # If None, match lemmas with no subtype
        if slot.get("pos_subtype") is not None:
            query = query.filter(Lemma.pos_subtype == slot["pos_subtype"])
        else:
            # For None subtype, allow either NULL or any subtype (to maximize combinations)
            # Actually, let's be strict: None means no subtype
            query = query.filter(Lemma.pos_subtype.is_(None))

        # Filter by difficulty range
        if slot.get("min_level"):
            query = query.filter(Lemma.difficulty_level >= slot["min_level"])
        if slot.get("max_level"):
            query = query.filter(Lemma.difficulty_level <= slot["max_level"])

        lemmas = query.all()
        return [(lemma, lemma.guid) for lemma in lemmas]

    def generate_all_combinations(
        self, session, pattern: Dict, max_combinations: int = None
    ) -> List[Dict]:
        """
        Generate all possible combinations for a pattern (cartesian product).

        Args:
            session: Database session
            pattern: Pattern definition
            max_combinations: Maximum combinations to generate (None = unlimited)

        Returns:
            List of filled pattern dictionaries
        """
        # Get lemmas for each slot
        slot_lemmas = {}
        slot_names = []

        for slot in pattern["slots"]:
            lemmas = self.get_lemmas_for_slot(session, slot)
            if not lemmas:
                logger.warning(
                    f"No lemmas found for slot {slot['name']} "
                    f"(pos_type={slot['pos_type']}, pos_subtype={slot.get('pos_subtype')})"
                )
                return []
            slot_lemmas[slot["name"]] = lemmas
            slot_names.append(slot["name"])
            logger.info(f"Slot {slot['name']}: {len(lemmas)} lemmas")

        # Generate cartesian product of all slot combinations
        slot_lists = [slot_lemmas[name] for name in slot_names]
        total_combinations = 1
        for lst in slot_lists:
            total_combinations *= len(lst)

        logger.info(
            f"Pattern {pattern['pattern_id']}: {total_combinations} total combinations possible"
        )

        if max_combinations and total_combinations > max_combinations:
            logger.warning(
                f"Limiting to {max_combinations} combinations (from {total_combinations})"
            )

        combinations = []
        for i, combo_tuple in enumerate(itertools.product(*slot_lists)):
            if max_combinations and i >= max_combinations:
                break

            combination = {
                "pattern_id": pattern["pattern_id"],
                "lemmas": {}
            }

            for slot_name, (lemma, guid) in zip(slot_names, combo_tuple):
                combination["lemmas"][slot_name] = (lemma, guid)

            combinations.append(combination)

        logger.info(f"Generated {len(combinations)} combinations for pattern {pattern['pattern_id']}")
        return combinations

    def build_template_text(self, pattern: Dict, filled_slots: Dict[str, Tuple[Lemma, str]]) -> str:
        """
        Build the mechanical English template text from a pattern and filled slots.

        Args:
            pattern: Pattern definition
            filled_slots: Dict mapping slot names to (Lemma, guid) tuples

        Returns:
            Template text with placeholders filled in
        """
        en_sentence = pattern["en_template"]
        for slot_name, (lemma, guid) in filled_slots.items():
            # Strip disambiguation info from lemma text (e.g., "mouse (computer)" -> "mouse")
            lemma_text = strip_disambiguation(lemma.lemma_text)
            en_sentence = en_sentence.replace(f"[{slot_name}]", lemma_text)
        return en_sentence

    def lookup_fixed_words(self, session, pattern: Dict) -> List[Tuple[Lemma, str]]:
        """
        Look up lemmas for fixed words in the pattern template.

        Args:
            session: Database session
            pattern: Pattern definition

        Returns:
            List of (lemma, guid) tuples for fixed words
        """
        fixed_lemmas = []
        for fixed_word in pattern.get("fixed_words", []):
            query = session.query(Lemma).filter(
                Lemma.lemma_text == fixed_word["lemma_text"],
                Lemma.pos_type == fixed_word["pos_type"],
                Lemma.guid.isnot(None)
            )
            lemma = query.first()
            if lemma:
                fixed_lemmas.append((lemma, lemma.guid))
            else:
                logger.warning(
                    f"Could not find fixed word '{fixed_word['lemma_text']}' "
                    f"(pos_type={fixed_word['pos_type']}) for pattern {pattern['pattern_id']}"
                )
        return fixed_lemmas

    def save_candidate_sentence(
        self, session, pattern: Dict, combination: Dict, template_text: str
    ):
        """
        Save a candidate sentence to the database without translations.

        Args:
            session: Database session
            pattern: Pattern definition
            combination: Filled combination dict
            template_text: The mechanical English template text

        Returns:
            Sentence object if saved successfully,
            "duplicate" string if duplicate found,
            None if save failed
        """
        if self.dry_run:
            logger.debug(f"[DRY RUN] Would save candidate: {template_text}")
            return None

        try:
            # Check for duplicate based on pattern and lemmas used
            # Find sentences with same pattern (including rejected ones to avoid regenerating)
            pattern_source = f"pattern:{pattern['pattern_id']}"
            existing_sentences = (
                session.query(Sentence)
                .filter_by(source_filename=pattern_source)
                .all()
            )

            # Build set of lemma IDs for this combination
            combination_lemma_ids = set(lemma.id for lemma, guid in combination["lemmas"].values())

            # Check each existing sentence to see if it uses the same lemmas
            for existing_sentence in existing_sentences:
                # Get lemma IDs used in this sentence
                existing_lemma_ids = set(
                    sw.lemma_id
                    for sw in session.query(SentenceWord)
                    .filter_by(sentence_id=existing_sentence.id, language_code="en")
                    .all()
                    if sw.lemma_id is not None
                )

                # If same lemmas are used, this is a duplicate
                if combination_lemma_ids == existing_lemma_ids:
                    # Log whether it was rejected or just a regular duplicate
                    status = "rejected" if existing_sentence.rejected else "duplicate"
                    logger.debug(
                        f"Skipping {status} sentence for pattern {pattern['pattern_id']}: "
                        f"{template_text} (already exists as sentence {existing_sentence.id})"
                    )
                    return "duplicate"

            # No duplicate found, create new sentence
            sentence = Sentence(
                pattern_type=pattern.get("pattern_type"),
                source_filename=pattern_source,
                verified=False,
            )
            session.add(sentence)
            session.flush()  # Get sentence ID

            # Add only the mechanical English "translation" (template)
            # This will be replaced with proper English when batch translation runs
            translation = SentenceTranslation(
                sentence_id=sentence.id,
                language_code="en",
                translation_text=template_text,
                verified=False,
            )
            session.add(translation)

            # Add word links (for English only, for now)
            position = 0

            # Add slot variables
            for slot_name, (lemma, guid) in combination["lemmas"].items():
                # Strip disambiguation info when storing the word in the sentence
                # (e.g., "mouse (computer)" -> "mouse") to match the actual sentence text
                lemma_text = strip_disambiguation(lemma.lemma_text)

                sentence_word = SentenceWord(
                    sentence_id=sentence.id,
                    lemma_id=lemma.id,
                    language_code="en",
                    position=position,
                    word_role=slot_name,
                    english_text=lemma_text,
                    target_language_text=lemma_text,
                )
                session.add(sentence_word)
                position += 1

            # Add fixed words as dependencies
            fixed_lemmas = self.lookup_fixed_words(session, pattern)
            for lemma, guid in fixed_lemmas:
                sentence_word = SentenceWord(
                    sentence_id=sentence.id,
                    lemma_id=lemma.id,
                    language_code="en",
                    position=position,
                    word_role="fixed",
                    english_text=lemma.lemma_text,
                    target_language_text=lemma.lemma_text,
                )
                session.add(sentence_word)
                position += 1

            session.commit()
            return sentence

        except Exception as e:
            logger.error(f"Failed to save candidate sentence: {e}")
            session.rollback()
            return None

    def generate_candidates_for_pattern(
        self, pattern: Dict, max_combinations: int = None
    ) -> Dict:
        """
        Generate candidate sentences for a specific pattern (without translations).

        Args:
            pattern: Pattern definition
            max_combinations: Maximum combinations to generate

        Returns:
            Dictionary with generation results
        """
        logger.info(f"Generating candidates for pattern: {pattern['pattern_id']}")

        session = self.get_session()
        try:
            # Generate all combinations
            combinations = self.generate_all_combinations(session, pattern, max_combinations)

            if not combinations:
                return {
                    "pattern_id": pattern["pattern_id"],
                    "success": False,
                    "error": "No valid lemma combinations found",
                }

            # Save candidates to database
            results = {
                "pattern_id": pattern["pattern_id"],
                "total": len(combinations),
                "success_count": 0,
                "duplicate_count": 0,
                "error_count": 0,
            }

            for i, combo in enumerate(combinations, 1):
                if i % 100 == 0:
                    logger.info(f"Processed {i}/{len(combinations)} candidates...")

                template_text = self.build_template_text(pattern, combo["lemmas"])
                result = self.save_candidate_sentence(session, pattern, combo, template_text)

                if result == "duplicate":
                    results["duplicate_count"] += 1
                elif result or self.dry_run:
                    results["success_count"] += 1
                else:
                    results["error_count"] += 1

            logger.info(
                f"Pattern {pattern['pattern_id']}: "
                f"saved {results['success_count']}/{results['total']} candidates, "
                f"{results['duplicate_count']} duplicates skipped"
            )
            return results

        finally:
            session.close()

    def generate_candidates_all_patterns(self, max_per_pattern: int = None) -> Dict:
        """
        Generate candidate sentences for all defined patterns.

        Args:
            max_per_pattern: Max combinations per pattern

        Returns:
            Dictionary with overall results
        """
        logger.info(f"Generating candidates for {len(SIMPLE_PATTERNS)} patterns")

        overall_results = {
            "patterns_processed": 0,
            "total_candidates": 0,
            "total_success": 0,
            "total_duplicates": 0,
            "total_errors": 0,
            "pattern_results": [],
        }

        for pattern in SIMPLE_PATTERNS:
            result = self.generate_candidates_for_pattern(pattern, max_combinations=max_per_pattern)
            overall_results["patterns_processed"] += 1
            overall_results["total_candidates"] += result.get("total", 0)
            overall_results["total_success"] += result.get("success_count", 0)
            overall_results["total_duplicates"] += result.get("duplicate_count", 0)
            overall_results["total_errors"] += result.get("error_count", 0)
            overall_results["pattern_results"].append(result)

        return overall_results

    def submit_batch_translation(
        self, target_languages: List[str], limit: int = None, pattern_id: str = None
    ) -> Tuple[str, int]:
        """
        Submit a batch translation job for untranslated sentences.

        Args:
            target_languages: List of language codes to translate to (e.g., ['lt', 'zh'])
            limit: Maximum number of sentences to translate (distributed across patterns)
            pattern_id: Optional pattern_id filter

        Returns:
            Tuple of (batch_id, number of requests queued)
        """
        session = self.get_session()
        try:
            # Find sentences that only have English translation
            from sqlalchemy import func as sql_func

            # If a specific pattern is requested, just query that pattern
            if pattern_id:
                query = (
                    session.query(Sentence)
                    .join(SentenceTranslation)
                    .filter(SentenceTranslation.language_code == "en")
                    .filter(Sentence.source_filename == f"pattern:{pattern_id}")
                )

                # Group by sentence and filter for those with only one translation
                sentences_with_only_en = (
                    session.query(Sentence.id, sql_func.count(SentenceTranslation.id))
                    .join(SentenceTranslation)
                    .filter(Sentence.source_filename == f"pattern:{pattern_id}")
                    .group_by(Sentence.id)
                    .having(sql_func.count(SentenceTranslation.id) == 1)
                    .subquery()
                )

                query = query.filter(Sentence.id.in_(
                    session.query(sentences_with_only_en.c.id)
                ))

                if limit:
                    query = query.limit(limit)

                sentences = query.all()
                logger.info(f"Found {len(sentences)} untranslated sentences for pattern {pattern_id}")

            else:
                # No specific pattern - distribute limit across all patterns
                # First, get all pattern IDs with untranslated sentences
                pattern_source_query = (
                    session.query(Sentence.source_filename)
                    .join(SentenceTranslation)
                    .filter(SentenceTranslation.language_code == "en")
                    .filter(Sentence.source_filename.like("pattern:%"))
                    .distinct()
                )

                # Find sentences with only English translation
                sentences_with_only_en = (
                    session.query(Sentence.id, sql_func.count(SentenceTranslation.id))
                    .join(SentenceTranslation)
                    .group_by(Sentence.id)
                    .having(sql_func.count(SentenceTranslation.id) == 1)
                    .subquery()
                )

                pattern_source_query = pattern_source_query.filter(
                    Sentence.id.in_(session.query(sentences_with_only_en.c.id))
                )

                pattern_sources = [row[0] for row in pattern_source_query.all()]

                if not pattern_sources:
                    logger.warning("No untranslated sentences found")
                    return None, 0

                logger.info(f"Found {len(pattern_sources)} patterns with untranslated sentences")

                # Distribute limit across patterns
                sentences = []
                if limit:
                    per_pattern_limit = max(1, limit // len(pattern_sources))
                    logger.info(f"Distributing limit of {limit} across {len(pattern_sources)} patterns ({per_pattern_limit} per pattern)")
                else:
                    per_pattern_limit = None

                for pattern_source in pattern_sources:
                    pattern_query = (
                        session.query(Sentence)
                        .filter(Sentence.source_filename == pattern_source)
                        .filter(Sentence.id.in_(session.query(sentences_with_only_en.c.id)))
                    )

                    if per_pattern_limit:
                        pattern_query = pattern_query.limit(per_pattern_limit)

                    pattern_sentences = pattern_query.all()
                    sentences.extend(pattern_sentences)

                    if limit and len(sentences) >= limit:
                        sentences = sentences[:limit]
                        break

                logger.info(f"Selected {len(sentences)} untranslated sentences across patterns")

            if not sentences:
                logger.warning("No untranslated sentences found")
                return None, 0

            # Queue batch requests
            requests_queued = 0
            for sentence in sentences:
                # Get word links for this sentence
                sentence_words = (
                    session.query(SentenceWord)
                    .filter_by(sentence_id=sentence.id, language_code="en")
                    .all()
                )

                # Use shared helper to build prompt
                try:
                    context, prompt = build_translation_prompt(
                        sentence, sentence_words, target_languages, session
                    )
                except ValueError:
                    # No English translation found
                    continue

                # Build batch request
                custom_id = f"sentence_{sentence.id}"

                # Combine context and prompt for batch API
                full_prompt = f"{context}\n\n{prompt}"

                # Use shared helper to build response schema
                inner_schema = build_response_schema(target_languages)

                # Wrap in OpenAI Batch API format
                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "SentenceTranslations",
                        "strict": True,
                        "schema": inner_schema
                    }
                }

                request_body = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": full_prompt}],
                    "response_format": response_format
                }

                metadata = BatchRequestMetadata(
                    custom_id=custom_id,
                    agent_name="buivolas",
                    operation_type="translate_sentence",
                    entity_id=sentence.id,
                    entity_type="sentence"
                )

                try:
                    self.batch_manager.queue_request(
                        custom_id=custom_id,
                        request_body=request_body,
                        metadata=metadata,
                        endpoint="/v1/chat/completions"
                    )
                    requests_queued += 1
                except ValueError as e:
                    # Request already exists
                    logger.debug(f"Skipping sentence {sentence.id}: {e}")

            logger.info(f"Queued {requests_queued} translation requests")

            # Submit batch
            if requests_queued > 0:
                pending_requests = self.batch_manager.get_pending_requests(
                    agent_name="buivolas",
                    operation_type="translate_sentence"
                )
                batch_id, file_id = self.batch_manager.submit_batch(
                    pending_requests,
                    batch_metadata={"agent": "buivolas", "operation": "translate_sentences"}
                )
                logger.info(f"Submitted batch {batch_id} with {len(pending_requests)} requests")
                return batch_id, len(pending_requests)

            return None, 0

        finally:
            session.close()

    def check_batch_status(self, batch_id: str) -> Dict:
        """Check status of a batch translation job."""
        return self.batch_manager.check_batch_status(batch_id)

    def retrieve_batch_results(self, batch_id: str) -> int:
        """
        Retrieve and apply batch translation results.

        Args:
            batch_id: Batch ID to retrieve

        Returns:
            Number of sentences updated
        """
        # Retrieve results from batch API
        count = self.batch_manager.retrieve_batch_results(batch_id)
        logger.info(f"Retrieved {count} results from batch {batch_id}")

        # Apply results to sentences
        session = self.get_session()
        try:
            completed_requests = self.batch_manager.get_completed_requests(batch_id=batch_id)
            sentences_updated = 0

            for req in completed_requests:
                sentence_id = req.entity_id
                if not sentence_id:
                    continue

                # Parse response and store results
                try:
                    response = json.loads(req.response_body)
                    # Extract content from ChatCompletion response
                    content = response["body"]["choices"][0]["message"]["content"]
                    translations = json.loads(content)

                    # Use shared helper to store translation results
                    store_translation_results(sentence_id, translations, session)
                    sentences_updated += 1

                except Exception as e:
                    logger.error(f"Failed to apply results for sentence {sentence_id}: {e}")
                    session.rollback()

            logger.info(f"Updated {sentences_updated} sentences with translations")
            return sentences_updated

        finally:
            session.close()


def get_argument_parser():
    """Return the argument parser for introspection."""
    parser = argparse.ArgumentParser(
        description="Buivolas - Simple Pattern Sentence Generation Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate candidates for all patterns (limited to 1000 per pattern)
  python buivolas.py generate-candidates --all-patterns --limit 1000

  # Generate candidates for specific patterns
  python buivolas.py generate-candidates --patterns where_is_noun my_noun_is_color

  # Submit batch translation for untranslated sentences
  python buivolas.py submit-batch --languages lt zh fr --limit 500

  # Check batch status
  python buivolas.py check-batch --batch-id batch_abc123

  # Retrieve and apply batch results
  python buivolas.py retrieve-batch --batch-id batch_abc123
        """
    )

    # Common arguments
    add_common_args(parser)
    add_llm_args(parser, default_model="gpt-5-mini")
    add_backend_args(parser)

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Command to execute", required=True)

    # generate-candidates command
    gen_parser = subparsers.add_parser(
        "generate-candidates",
        help="Generate candidate sentences without translations"
    )
    gen_group = gen_parser.add_mutually_exclusive_group(required=True)
    gen_group.add_argument(
        "--patterns", nargs="+", help="Specific pattern IDs to generate"
    )
    gen_group.add_argument(
        "--all-patterns", action="store_true", help="Generate for all patterns"
    )
    gen_parser.add_argument(
        "--limit", type=int, help="Max combinations per pattern (default: unlimited)"
    )

    # submit-batch command
    submit_parser = subparsers.add_parser(
        "submit-batch",
        help="Submit batch translation job for untranslated sentences"
    )
    submit_parser.add_argument(
        "--languages",
        nargs="+",
        required=True,
        choices=["lt", "zh", "ko", "fr", "de", "es", "pt"],
        help="Target languages to translate to"
    )
    submit_parser.add_argument(
        "--limit", type=int, help="Max sentences to translate"
    )
    submit_parser.add_argument(
        "--pattern-id", help="Only translate sentences from this pattern"
    )

    # check-batch command
    check_parser = subparsers.add_parser(
        "check-batch",
        help="Check status of a batch translation job"
    )
    check_parser.add_argument(
        "--batch-id", required=True, help="Batch ID to check"
    )

    # retrieve-batch command
    retrieve_parser = subparsers.add_parser(
        "retrieve-batch",
        help="Retrieve and apply batch translation results"
    )
    retrieve_parser.add_argument(
        "--batch-id", required=True, help="Batch ID to retrieve"
    )

    # list-batches command
    list_parser = subparsers.add_parser(
        "list-batches",
        help="List active batch translation jobs"
    )

    return parser


def main():
    """Main entry point for the buivolas agent."""
    parser = get_argument_parser()
    args = parser.parse_args()

    # Create backend configuration using common helper
    backend_config = get_backend_config(args)

    # Create agent
    if backend_config:
        agent = BuivolasAgent(
            backend_config=backend_config, model=args.model, debug=args.debug, dry_run=args.dry_run
        )
    else:
        agent = BuivolasAgent(
            db_path=args.db_path, model=args.model, debug=args.debug, dry_run=args.dry_run
        )

    # Handle commands
    if args.command == "generate-candidates":
        pattern_dict = {p["pattern_id"]: p for p in SIMPLE_PATTERNS}

        if args.all_patterns:
            results = agent.generate_candidates_all_patterns(max_per_pattern=args.limit)

            # Print summary
            logger.info("=" * 80)
            logger.info("BUIVOLAS - CANDIDATE GENERATION REPORT")
            logger.info("=" * 80)
            logger.info(f"Patterns processed: {results['patterns_processed']}")
            logger.info(f"Total candidates: {results['total_candidates']}")
            logger.info(f"Successful: {results['total_success']}")
            logger.info(f"Duplicates: {results['total_duplicates']}")
            logger.info(f"Errors: {results['total_errors']}")
            if args.dry_run:
                logger.info("DRY RUN - No database changes made")
            logger.info("=" * 80)

        else:
            patterns_to_generate = []
            for pattern_id in args.patterns:
                if pattern_id in pattern_dict:
                    patterns_to_generate.append(pattern_dict[pattern_id])
                else:
                    logger.error(f"Unknown pattern: {pattern_id}")
                    available = ", ".join(pattern_dict.keys())
                    logger.error(f"Available patterns: {available}")
                    return 1

            # Generate for each pattern
            total_success = 0
            total_duplicates = 0
            total_errors = 0
            total_candidates = 0

            for pattern in patterns_to_generate:
                result = agent.generate_candidates_for_pattern(pattern, max_combinations=args.limit)
                total_candidates += result.get("total", 0)
                total_success += result.get("success_count", 0)
                total_duplicates += result.get("duplicate_count", 0)
                total_errors += result.get("error_count", 0)

            # Print summary
            logger.info("=" * 80)
            logger.info("BUIVOLAS - CANDIDATE GENERATION REPORT")
            logger.info("=" * 80)
            logger.info(f"Patterns: {', '.join(args.patterns)}")
            logger.info(f"Total candidates: {total_candidates}")
            logger.info(f"Successful: {total_success}")
            logger.info(f"Duplicates: {total_duplicates}")
            logger.info(f"Errors: {total_errors}")
            if args.dry_run:
                logger.info("DRY RUN - No database changes made")
            logger.info("=" * 80)

    elif args.command == "submit-batch":
        batch_id, count = agent.submit_batch_translation(
            target_languages=args.languages,
            limit=args.limit,
            pattern_id=args.pattern_id
        )

        if batch_id:
            logger.info("=" * 80)
            logger.info("BUIVOLAS - BATCH SUBMISSION REPORT")
            logger.info("=" * 80)
            logger.info(f"Batch ID: {batch_id}")
            logger.info(f"Requests submitted: {count}")
            logger.info(f"Target languages: {', '.join(args.languages)}")
            logger.info("=" * 80)
            logger.info(f"Check status with: python buivolas.py check-batch --batch-id {batch_id}")
        else:
            logger.warning("No batch submitted (no untranslated sentences found)")

    elif args.command == "check-batch":
        batch_info = agent.check_batch_status(args.batch_id)

        logger.info("=" * 80)
        logger.info("BUIVOLAS - BATCH STATUS")
        logger.info("=" * 80)
        logger.info(f"Batch ID: {batch_info['id']}")
        logger.info(f"Status: {batch_info['status']}")
        logger.info(f"Created at: {batch_info.get('created_at')}")

        counts = batch_info.get("request_counts", {})
        logger.info(f"Total requests: {counts.get('total', 0)}")
        logger.info(f"Completed: {counts.get('completed', 0)}")
        logger.info(f"Failed: {counts.get('failed', 0)}")
        logger.info("=" * 80)

        if batch_info['status'] == 'completed':
            logger.info(f"Retrieve results with: python buivolas.py retrieve-batch --batch-id {args.batch_id}")

    elif args.command == "retrieve-batch":
        count = agent.retrieve_batch_results(args.batch_id)

        logger.info("=" * 80)
        logger.info("BUIVOLAS - BATCH RESULTS APPLIED")
        logger.info("=" * 80)
        logger.info(f"Batch ID: {args.batch_id}")
        logger.info(f"Sentences updated: {count}")
        logger.info("=" * 80)

    elif args.command == "list-batches":
        active_batches = agent.batch_manager.list_active_batches()

        logger.info("=" * 80)
        logger.info("BUIVOLAS - ACTIVE BATCHES")
        logger.info("=" * 80)

        if active_batches:
            for batch_id in active_batches:
                # Check status with OpenAI to sync local database
                try:
                    batch_info = agent.batch_manager.check_batch_status(batch_id)
                    openai_status = batch_info.get('status', 'unknown')
                    logger.info(f"\nBatch: {batch_id}")
                    logger.info(f"  OpenAI Status: {openai_status}")

                    # Show request counts from OpenAI if available
                    if 'request_counts' in batch_info:
                        counts = batch_info['request_counts']
                        logger.info(f"  Total: {counts.get('total', 0)}, Completed: {counts.get('completed', 0)}, Failed: {counts.get('failed', 0)}")

                    # Also show local database summary
                    summary = agent.batch_manager.get_batch_summary(batch_id)
                    logger.info(f"  Local DB status counts: {summary['status_counts']}")
                except Exception as e:
                    logger.warning(f"  Failed to check status for {batch_id}: {e}")
                    # Fall back to local summary only
                    summary = agent.batch_manager.get_batch_summary(batch_id)
                    logger.info(f"\nBatch: {batch_id}")
                    logger.info(f"  Total requests: {summary['total_requests']}")
                    logger.info(f"  Status counts: {summary['status_counts']}")
        else:
            logger.info("No active batches")

        logger.info("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
