#!/usr/bin/env python3
"""
Dramblys - Missing Words Detection Agent

This agent runs autonomously to identify missing words that should be in the
dictionary. It scans frequency corpora, checks category coverage, and identifies
high-priority words to add.

"Dramblys" means "elephant" in Lithuanian - never forgets what's missing!
"""

import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import constants
from wordfreq.storage.database import create_database_session
from wordfreq.storage.models.schema import Lemma, WordToken, WordFrequency, Corpus, DerivativeForm
from wordfreq.storage.models.imports import PendingImport, WordExclusion
from wordfreq.translation.client import LinguisticClient

# Import validation and staging operations
from agents.dramblys.validation import is_valid_word
from agents.dramblys import staging

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class DramblysAgent:
    """Agent for detecting missing words in the dictionary."""

    def __init__(self, db_path: str = None, debug: bool = False):
        """
        Initialize the Dramblys agent.

        Args:
            db_path: Database path (uses default if None)
            debug: Enable debug logging
        """
        self.db_path = db_path or constants.WORDFREQ_DB_PATH
        self.debug = debug

        if debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self):
        """Get database session."""
        return create_database_session(self.db_path)

    def check_high_frequency_missing_words(
        self, top_n: int = 5000, min_rank: int = 1
    ) -> Dict[str, any]:
        """
        Check for high-frequency words in corpora that are missing from lemmas.

        Args:
            top_n: Check top N words by frequency
            min_rank: Minimum frequency rank to consider

        Returns:
            Dictionary with missing words and their frequency info
        """
        logger.info(f"Checking top {top_n} frequency words for missing lemmas...")

        session = self.get_session()
        try:
            # Get all existing lemma texts (English)
            existing_lemmas = set()
            lemmas = session.query(Lemma).all()
            for lemma in lemmas:
                existing_lemmas.add(lemma.lemma_text.lower())

            # Also get all English derivative forms
            english_forms = (
                session.query(DerivativeForm).filter(DerivativeForm.language_code == "en").all()
            )
            for form in english_forms:
                existing_lemmas.add(form.derivative_form_text.lower())

            # Get excluded words (words we've decided not to import)
            excluded_words = set()
            exclusions = (
                session.query(WordExclusion).filter(WordExclusion.language_code == "en").all()
            )
            for exclusion in exclusions:
                excluded_words.add(exclusion.excluded_word.lower())

            logger.info(f"Found {len(existing_lemmas)} existing English words in database")
            logger.info(f"Found {len(excluded_words)} excluded words")

            # Get high-frequency words from word_tokens
            high_freq_tokens = (
                session.query(WordToken)
                .filter(
                    WordToken.language_code == "en",
                    WordToken.frequency_rank.isnot(None),
                    WordToken.frequency_rank >= min_rank,
                )
                .order_by(WordToken.frequency_rank)
                .limit(top_n)
                .all()
            )

            logger.info(f"Checking {len(high_freq_tokens)} high-frequency tokens")

            # Find missing words
            missing_words = []
            for token in high_freq_tokens:
                word = token.token
                word_lower = word.lower()

                # Skip if already in database
                if word_lower in existing_lemmas:
                    continue

                # Skip if explicitly excluded
                if word_lower in excluded_words:
                    continue

                # Skip if not a valid word (use imported validation function)
                if not is_valid_word(word):
                    continue

                # Get frequency data
                frequencies = (
                    session.query(WordFrequency)
                    .filter(WordFrequency.word_token_id == token.id)
                    .all()
                )

                corpus_info = []
                for freq in frequencies:
                    corpus = session.query(Corpus).filter(Corpus.id == freq.corpus_id).first()
                    if corpus:
                        corpus_info.append(
                            {"corpus": corpus.name, "rank": freq.rank, "frequency": freq.frequency}
                        )

                missing_words.append(
                    {
                        "word": word,
                        "overall_rank": token.frequency_rank,
                        "corpus_frequencies": corpus_info,
                    }
                )

            logger.info(f"Found {len(missing_words)} high-frequency missing words")

            return {
                "total_checked": len(high_freq_tokens),
                "missing_count": len(missing_words),
                "missing_words": missing_words,
                "existing_word_count": len(existing_lemmas),
            }

        except Exception as e:
            logger.error(f"Error checking high-frequency missing words: {e}")
            return {"error": str(e), "total_checked": 0, "missing_count": 0, "missing_words": []}
        finally:
            session.close()

    def check_orphaned_derivative_forms(self) -> Dict[str, any]:
        """
        Find derivative forms that exist in the database but have no lemma entry.

        Returns:
            Dictionary with orphaned forms
        """
        logger.info("Checking for derivative forms without corresponding lemmas...")

        session = self.get_session()
        try:
            # Get all English derivative forms
            derivative_forms = (
                session.query(DerivativeForm).filter(DerivativeForm.language_code == "en").all()
            )

            logger.info(f"Found {len(derivative_forms)} English derivative forms")

            # Get all lemma IDs
            existing_lemma_ids = set()
            lemmas = session.query(Lemma.id).all()
            for lemma_id_tuple in lemmas:
                existing_lemma_ids.add(lemma_id_tuple[0])

            # Find orphaned forms
            orphaned_forms = []
            for form in derivative_forms:
                if form.lemma_id not in existing_lemma_ids:
                    orphaned_forms.append(
                        {
                            "derivative_form_id": form.id,
                            "word": form.derivative_form_text,
                            "grammatical_form": form.grammatical_form,
                            "lemma_id": form.lemma_id,
                        }
                    )

            logger.info(f"Found {len(orphaned_forms)} orphaned derivative forms")

            return {
                "total_forms_checked": len(derivative_forms),
                "orphaned_count": len(orphaned_forms),
                "orphaned_forms": orphaned_forms,
            }

        except Exception as e:
            logger.error(f"Error checking orphaned derivative forms: {e}")
            return {
                "error": str(e),
                "total_forms_checked": 0,
                "orphaned_count": 0,
                "orphaned_forms": [],
            }
        finally:
            session.close()

    def check_subtype_coverage(self, min_expected: int = 10) -> Dict[str, any]:
        """
        Check coverage of different POS subtypes and identify underrepresented ones.

        Args:
            min_expected: Minimum expected count for a subtype to be well-covered

        Returns:
            Dictionary with subtype coverage info
        """
        logger.info("Checking POS subtype coverage...")

        session = self.get_session()
        try:
            from sqlalchemy import func

            # Get counts by subtype
            subtype_counts = (
                session.query(
                    Lemma.pos_type, Lemma.pos_subtype, func.count(Lemma.id).label("count")
                )
                .filter(Lemma.pos_subtype.isnot(None), Lemma.pos_subtype != "")
                .group_by(Lemma.pos_type, Lemma.pos_subtype)
                .all()
            )

            logger.info(f"Found {len(subtype_counts)} subtypes")

            # Categorize by coverage
            well_covered = []
            under_covered = []

            for pos_type, pos_subtype, count in subtype_counts:
                entry = {"pos_type": pos_type, "pos_subtype": pos_subtype, "count": count}

                if count >= min_expected:
                    well_covered.append(entry)
                else:
                    under_covered.append(entry)

            # Sort under-covered by count (ascending)
            under_covered.sort(key=lambda x: x["count"])

            logger.info(f"Well-covered subtypes: {len(well_covered)}")
            logger.info(f"Under-covered subtypes: {len(under_covered)}")

            return {
                "total_subtypes": len(subtype_counts),
                "well_covered_count": len(well_covered),
                "under_covered_count": len(under_covered),
                "well_covered": well_covered,
                "under_covered": under_covered,
                "min_expected_threshold": min_expected,
            }

        except Exception as e:
            logger.error(f"Error checking subtype coverage: {e}")
            return {
                "error": str(e),
                "total_subtypes": 0,
                "well_covered_count": 0,
                "under_covered_count": 0,
                "well_covered": [],
                "under_covered": [],
            }
        finally:
            session.close()

    def find_words_for_subtype(
        self, pos_type: str, pos_subtype: str, top_n: int = 250, model: str = "gpt-5-mini"
    ) -> Dict[str, any]:
        """
        Use LLM to identify which high-frequency words have meanings in a specific POS subtype.

        Args:
            pos_type: Part of speech (noun, verb, adjective, adverb)
            pos_subtype: Specific subtype (e.g., 'animals', 'physical_action')
            top_n: Number of top frequency words to review
            model: LLM model to use

        Returns:
            Dictionary with words that fit the subtype
        """
        logger.info(f"Finding {pos_type} words for subtype '{pos_subtype}' in top {top_n} words...")

        session = self.get_session()
        try:
            # Get all high-frequency tokens (we'll filter to top N after removing stopwords/existing)
            all_tokens = (
                session.query(WordToken)
                .filter(WordToken.language_code == "en", WordToken.frequency_rank.isnot(None))
                .order_by(WordToken.frequency_rank)
                .all()
            )

            # Get existing words with derivative forms
            existing_tokens = set()
            for token in all_tokens:
                if len(token.derivative_forms) > 0:
                    existing_tokens.add(token.token.lower())

            # Filter: valid words, not stopwords, not already defined, then take top N
            word_list = []
            for token in all_tokens:
                if len(word_list) >= top_n:
                    break
                if not is_valid_word(token.token):
                    continue
                if token.token.lower() in existing_tokens:
                    continue
                word_list.append(token.token)

            logger.info(
                f"After filtering stopwords and existing words, reviewing top {len(word_list)} undefined words"
            )
            logger.info(f"Querying LLM to identify {pos_type}/{pos_subtype} words in this list...")

            # Query LLM
            from clients.unified_client import UnifiedLLMClient
            from clients.types import Schema, SchemaProperty

            client = UnifiedLLMClient(debug=self.debug)

            schema = Schema(
                name="SubtypeWords",
                description=f"Words that have meanings in the {pos_subtype} {pos_type} category",
                properties={
                    "matches": SchemaProperty(
                        type="array",
                        description=f"Words from the list that have at least one meaning as a {pos_subtype} {pos_type}",
                        array_items_schema=Schema(
                            name="Match",
                            description=f"A word that matches the {pos_subtype} {pos_type} category",
                            properties={
                                "word": SchemaProperty("string", "The word from the list"),
                                "definition": SchemaProperty(
                                    "string",
                                    f"The specific definition that fits {pos_subtype} {pos_type}",
                                ),
                                "confidence": SchemaProperty(
                                    "number", "Confidence 0-1 that this word fits the category"
                                ),
                            },
                        ),
                    )
                },
            )

            prompt = f"""Review this list of high-frequency English words and identify which ones have at least one meaning that fits the category: {pos_type} / {pos_subtype}.

Word list:
{", ".join(word_list[:100])}

For each word that has a meaning in this category, provide:
1. The word
2. The specific definition that fits the category
3. Your confidence (0-1)

Only include words where you're confident they have a {pos_subtype} {pos_type} meaning.
"""

            response = client.generate_chat(prompt=prompt, model=model, json_schema=schema)

            if response.structured_data and "matches" in response.structured_data:
                matches = response.structured_data["matches"]
                logger.info(f"Found {len(matches)} words with {pos_type}/{pos_subtype} meanings")

                return {
                    "pos_type": pos_type,
                    "pos_subtype": pos_subtype,
                    "total_words_reviewed": len(word_list),
                    "matches_found": len(matches),
                    "matches": matches,
                }
            else:
                logger.error("Invalid response from LLM")
                return {
                    "error": "Invalid LLM response",
                    "pos_type": pos_type,
                    "pos_subtype": pos_subtype,
                    "matches_found": 0,
                    "matches": [],
                }

        except Exception as e:
            logger.error(f"Error finding words for subtype: {e}")
            return {
                "error": str(e),
                "pos_type": pos_type,
                "pos_subtype": pos_subtype,
                "matches_found": 0,
                "matches": [],
            }
        finally:
            session.close()

    def add_words_for_subtype(
        self,
        pos_type: str,
        pos_subtype: str,
        top_n: int = 250,
        model: str = "gpt-5-mini",
        throttle: float = 1.0,
        dry_run: bool = False,
        stage_only: bool = False,
        target_language: str = "lt",
    ) -> Dict[str, any]:
        """
        Find and add words for a specific POS subtype.

        Args:
            pos_type: Part of speech (noun, verb, adjective, adverb)
            pos_subtype: Specific subtype (e.g., 'animals', 'physical_action')
            top_n: Number of top frequency words to review
            model: LLM model to use
            throttle: Seconds to wait between API calls
            dry_run: If True, show what would be added without making changes
            stage_only: If True, add to pending_imports instead of processing directly
            target_language: Language code for disambiguation (default: lt)

        Returns:
            Dictionary with results
        """
        logger.info(
            f"{'Staging' if stage_only else 'Adding'} {pos_type}/{pos_subtype} words from top {top_n}..."
        )

        # Find matching words
        find_results = self.find_words_for_subtype(pos_type, pos_subtype, top_n, model)

        if "error" in find_results:
            return find_results

        matches = find_results["matches"]

        if dry_run:
            logger.info(f"DRY RUN: Would {'stage' if stage_only else 'add'} {len(matches)} words:")
            for match in matches[:20]:
                logger.info(f"  - '{match['word']}': {match['definition'][:60]}...")
            if len(matches) > 20:
                logger.info(f"  ... and {len(matches) - 20} more")
            return {
                "pos_type": pos_type,
                "pos_subtype": pos_subtype,
                "would_add": len(matches),
                "dry_run": True,
                "stage_only": stage_only,
                "sample": matches[:20],
            }

        # Process each matched word
        session = self.get_session()
        client = LinguisticClient(model=model, db_path=self.db_path, debug=self.debug)

        successful = 0
        failed = 0
        skipped = 0
        staged = 0

        for i, match in enumerate(matches, 1):
            word = match["word"]
            target_definition = match["definition"]

            logger.info(
                f"[{i}/{len(matches)}] {'Staging' if stage_only else 'Processing'} '{word}' for {pos_type}/{pos_subtype}"
            )

            # Check if this word already has this specific meaning
            word_token = (
                session.query(WordToken)
                .filter(WordToken.token == word, WordToken.language_code == "en")
                .first()
            )

            if word_token:
                # Check if this specific meaning already exists
                has_meaning = False
                for df in word_token.derivative_forms:
                    if (
                        df.lemma.pos_type == pos_type
                        and df.lemma.pos_subtype == pos_subtype
                        and target_definition.lower() in df.lemma.definition_text.lower()
                    ):
                        has_meaning = True
                        break

                if has_meaning:
                    logger.info(
                        f"Word '{word}' already has this {pos_type}/{pos_subtype} meaning, skipping"
                    )
                    skipped += 1
                    continue

            if stage_only:
                # Add to pending imports instead of processing directly
                # Check if already pending
                existing_pending = (
                    session.query(PendingImport)
                    .filter(
                        PendingImport.english_word == word,
                        PendingImport.pos_type == pos_type,
                        PendingImport.pos_subtype == pos_subtype,
                    )
                    .first()
                )

                if existing_pending:
                    logger.info(
                        f"Word '{word}' already in pending imports for {pos_type}/{pos_subtype}, skipping"
                    )
                    skipped += 1
                    continue

                # Get translation from LinguisticClient
                try:
                    word_data = client.get_word_definitions(word)
                    translation = ""
                    if word_data and "definitions" in word_data:
                        for defn in word_data["definitions"]:
                            if (
                                defn.get("pos_type") == pos_type
                                and defn.get("pos_subtype") == pos_subtype
                            ):
                                translation = defn.get("translations", {}).get(target_language, "")
                                break

                    if not translation:
                        logger.warning(
                            f"No translation found for '{word}', using definition as fallback"
                        )
                        translation = target_definition[:50]

                    pending = PendingImport(
                        english_word=word,
                        definition=target_definition,
                        disambiguation_translation=translation,
                        disambiguation_language=target_language,
                        pos_type=pos_type,
                        pos_subtype=pos_subtype,
                        source=f"dramblys_subtype_{pos_subtype}",
                        notes=f"Found via subtype search for {pos_type}/{pos_subtype}",
                    )
                    session.add(pending)
                    session.commit()
                    staged += 1
                    logger.info(f"Staged '{word}' to pending imports")

                except Exception as e:
                    logger.error(f"Failed to stage '{word}': {e}")
                    failed += 1
                    session.rollback()
            else:
                # Process the word directly to get all definitions
                success = client.process_word(word, refresh=False)

                if success:
                    successful += 1
                    logger.info(f"Successfully added '{word}'")
                else:
                    failed += 1
                    logger.error(f"Failed to add '{word}'")

            # Throttle
            if i < len(matches):
                time.sleep(throttle)

        logger.info(f"\nComplete:")
        logger.info(f"  Matches found: {len(matches)}")
        if stage_only:
            logger.info(f"  Staged: {staged}")
        else:
            logger.info(f"  Successful: {successful}")
        logger.info(f"  Failed: {failed}")
        logger.info(f"  Skipped (already exist): {skipped}")

        result = {
            "pos_type": pos_type,
            "pos_subtype": pos_subtype,
            "matches_found": len(matches),
            "failed": failed,
            "skipped": skipped,
            "dry_run": dry_run,
            "stage_only": stage_only,
        }

        if stage_only:
            result["staged"] = staged
        else:
            result["successful"] = successful

        return result

    def check_difficulty_level_distribution(self) -> Dict[str, any]:
        """
        Check distribution of words across difficulty levels.

        Returns:
            Dictionary with level distribution info
        """
        logger.info("Checking difficulty level distribution...")

        session = self.get_session()
        try:
            from sqlalchemy import func

            # Get counts by difficulty level
            level_counts = (
                session.query(Lemma.difficulty_level, func.count(Lemma.id).label("count"))
                .filter(
                    Lemma.difficulty_level.isnot(None),
                    Lemma.guid.isnot(None),  # Only count trakaido words
                )
                .group_by(Lemma.difficulty_level)
                .order_by(Lemma.difficulty_level)
                .all()
            )

            distribution = {}
            total_words = 0
            for level, count in level_counts:
                distribution[level] = count
                total_words += count

            # Identify gaps and imbalances
            gaps = []
            imbalanced = []
            avg_per_level = total_words / 20 if total_words > 0 else 0

            for level in range(1, 21):
                count = distribution.get(level, 0)

                if count == 0:
                    gaps.append(level)
                elif avg_per_level > 0 and count < avg_per_level * 0.5:
                    imbalanced.append(
                        {"level": level, "count": count, "expected_avg": avg_per_level}
                    )

            logger.info(f"Total trakaido words: {total_words}")
            logger.info(f"Level gaps: {len(gaps)}")
            logger.info(f"Imbalanced levels: {len(imbalanced)}")

            return {
                "total_words": total_words,
                "distribution": distribution,
                "average_per_level": avg_per_level,
                "gaps": gaps,
                "imbalanced": imbalanced,
            }

        except Exception as e:
            logger.error(f"Error checking difficulty level distribution: {e}")
            return {
                "error": str(e),
                "total_words": 0,
                "distribution": {},
                "gaps": [],
                "imbalanced": [],
            }
        finally:
            session.close()

    def stage_missing_words_for_import(
        self,
        top_n: int = 5000,
        limit: Optional[int] = None,
        model: str = "gpt-5-mini",
        throttle: float = 1.0,
        dry_run: bool = False,
        target_language: str = "lt",
    ) -> Dict[str, any]:
        """
        Stage high-frequency missing words to the pending_imports table.

        Delegates to staging module.

        Args:
            top_n: Check top N words by frequency
            limit: Maximum number of words to stage
            model: LLM model to use for definitions
            throttle: Seconds to wait between API calls
            dry_run: If True, show what would be staged without making changes
            target_language: Language code for disambiguation translations (default: lt)

        Returns:
            Dictionary with staging results
        """
        # Get missing words check results
        check_results = self.check_high_frequency_missing_words(top_n=top_n)

        if "error" in check_results:
            return check_results

        missing_words = check_results["missing_words"]
        session = self.get_session()

        try:
            return staging.stage_missing_words_for_import(
                session=session,
                missing_words=missing_words,
                db_path=self.db_path,
                limit=limit,
                model=model,
                throttle=throttle,
                dry_run=dry_run,
                target_language=target_language,
                debug=self.debug,
            )
        finally:
            session.close()

    def fix_missing_words(
        self,
        top_n: int = 5000,
        limit: Optional[int] = None,
        model: str = "gpt-5-mini",
        throttle: float = 1.0,
        dry_run: bool = False,
    ) -> Dict[str, any]:
        """
        Process high-frequency missing words using LLM to add them to the database.

        Args:
            top_n: Check top N words by frequency (default: 5000)
            limit: Maximum number of words to process
            model: LLM model to use
            throttle: Seconds to wait between API calls
            dry_run: If True, show what would be fixed WITHOUT making any LLM calls

        Returns:
            Dictionary with fix results
        """
        logger.info("Finding high-frequency missing words to process...")

        # Get missing words check results
        check_results = self.check_high_frequency_missing_words(top_n=top_n)

        if "error" in check_results:
            return check_results

        missing_words = check_results["missing_words"]
        total_missing = len(missing_words)

        if total_missing == 0:
            logger.info("No high-frequency missing words found!")
            return {
                "total_missing": 0,
                "processed": 0,
                "successful": 0,
                "failed": 0,
                "dry_run": dry_run,
            }

        logger.info(f"Found {total_missing} high-frequency missing words")

        # Apply limit if specified
        if limit:
            words_to_process = missing_words[:limit]
            logger.info(f"Processing limited to {limit} words")
        else:
            words_to_process = missing_words

        if dry_run:
            logger.info(f"DRY RUN: Would process {len(words_to_process)} words:")
            for word_info in words_to_process[:20]:
                corpus_str = ", ".join(
                    [f"{c['corpus']}:{c['rank']}" for c in word_info["corpus_frequencies"][:2]]
                )
                logger.info(
                    f"  - '{word_info['word']}' (overall rank: {word_info['overall_rank']}, {corpus_str})"
                )
            if len(words_to_process) > 20:
                logger.info(f"  ... and {len(words_to_process) - 20} more")
            return {
                "total_missing": total_missing,
                "would_process": len(words_to_process),
                "dry_run": True,
                "sample": words_to_process[:20],
            }

        # Initialize client for LLM-based processing
        client = LinguisticClient(model=model, db_path=self.db_path, debug=self.debug)

        # Process each word
        successful = 0
        failed = 0

        for i, word_info in enumerate(words_to_process, 1):
            word = word_info["word"]
            logger.info(
                f"\n[{i}/{len(words_to_process)}] Processing: '{word}' (rank: {word_info['overall_rank']})"
            )

            success = client.process_word(word, refresh=False)

            if success:
                successful += 1
                logger.info(f"Successfully processed '{word}'")
            else:
                failed += 1
                logger.error(f"Failed to process '{word}'")

            # Throttle to avoid overloading the API
            if i < len(words_to_process):
                time.sleep(throttle)

        logger.info(f"\n{'='*60}")
        logger.info(f"Fix complete:")
        logger.info(f"  Total missing: {total_missing}")
        logger.info(f"  Processed: {len(words_to_process)}")
        logger.info(f"  Successful: {successful}")
        logger.info(f"  Failed: {failed}")
        logger.info(f"{'='*60}")

        return {
            "total_missing": total_missing,
            "processed": len(words_to_process),
            "successful": successful,
            "failed": failed,
            "dry_run": dry_run,
        }

    def list_pending_imports(
        self,
        pos_type: Optional[str] = None,
        pos_subtype: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, any]:
        """Delegate to staging module."""
        session = self.get_session()
        try:
            return staging.list_pending_imports(session, pos_type, pos_subtype, limit)
        finally:
            session.close()

    def approve_pending_import(
        self, pending_import_id: int, model: str = "gpt-5-mini"
    ) -> Dict[str, any]:
        """Delegate to staging module."""
        session = self.get_session()
        try:
            return staging.approve_pending_import(
                session, pending_import_id, self.db_path, model, self.debug
            )
        finally:
            session.close()

    def reject_pending_import(
        self,
        pending_import_id: int,
        reason: str = "manual_rejection",
        add_to_exclusions: bool = True,
    ) -> Dict[str, any]:
        """Delegate to staging module."""
        session = self.get_session()
        try:
            return staging.reject_pending_import(
                session, pending_import_id, reason, add_to_exclusions
            )
        finally:
            session.close()

    def run_full_check(
        self,
        output_file: Optional[str] = None,
        top_n_frequency: int = 5000,
        min_subtype_count: int = 10,
    ) -> Dict[str, any]:
        """
        Run all missing words checks and generate a comprehensive report.

        Args:
            output_file: Optional path to write JSON report
            top_n_frequency: Number of top frequency words to check
            min_subtype_count: Minimum expected count for subtypes

        Returns:
            Dictionary with all check results
        """
        logger.info("Starting full missing words detection check...")
        start_time = datetime.now()

        results = {
            "timestamp": start_time.isoformat(),
            "database_path": self.db_path,
            "checks": {
                "high_frequency_missing": self.check_high_frequency_missing_words(
                    top_n=top_n_frequency
                ),
                "orphaned_forms": self.check_orphaned_derivative_forms(),
                "subtype_coverage": self.check_subtype_coverage(min_expected=min_subtype_count),
                "difficulty_distribution": self.check_difficulty_level_distribution(),
            },
        }

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        results["duration_seconds"] = duration

        # Print summary
        self._print_summary(results, start_time, duration)

        # Write to output file if requested
        if output_file:
            import json

            try:
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)
                logger.info(f"Report written to: {output_file}")
            except Exception as e:
                logger.error(f"Failed to write output file: {e}")

        return results

    def _print_frequency_check(self, freq_check: Dict, max_words: int = 10):
        """Print high-frequency missing words check results."""
        print(f"\n{'='*80}")
        print(f"HIGH-FREQUENCY MISSING WORDS:")
        print(f"  Frequency tokens checked: {freq_check['total_checked']}")
        print(f"  Missing words found: {freq_check['missing_count']}")
        print(f"  Existing words in database: {freq_check.get('existing_word_count', 'N/A')}")

        if freq_check["missing_count"] > 0:
            print(f"\n  Top {min(max_words, freq_check['missing_count'])} missing by rank:")
            for i, word_info in enumerate(freq_check["missing_words"][:max_words], 1):
                corpus_str = ", ".join(
                    [
                        f"{c['corpus']}:{c['rank']}"
                        for c in word_info.get("corpus_frequencies", [])[:2]
                    ]
                )
                print(
                    f"    {i}. '{word_info['word']}' (rank: {word_info['overall_rank']}) [{corpus_str}]"
                )
        print(f"{'='*80}\n")

    def _print_summary(self, results: Dict, start_time: datetime, duration: float):
        """Print a summary of the check results."""
        logger.info("=" * 80)
        logger.info("DRAMBLYS AGENT REPORT - Missing Words Detection")
        logger.info("=" * 80)
        logger.info(f"Timestamp: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info("")

        # High-frequency missing words
        if "high_frequency_missing" in results["checks"]:
            freq_check = results["checks"]["high_frequency_missing"]
            logger.info(f"HIGH-FREQUENCY MISSING WORDS:")
            logger.info(f"  Frequency tokens checked: {freq_check['total_checked']}")
            logger.info(f"  Missing words found: {freq_check['missing_count']}")
            logger.info(
                f"  Existing words in database: {freq_check.get('existing_word_count', 'N/A')}"
            )
            if freq_check["missing_count"] > 0:
                logger.info(f"  Top 10 missing by rank:")
                for i, word_info in enumerate(freq_check["missing_words"][:10], 1):
                    logger.info(
                        f"    {i}. '{word_info['word']}' (rank: {word_info['overall_rank']})"
                    )
            logger.info("")

        # Orphaned forms
        if "orphaned_forms" in results["checks"]:
            orphan_check = results["checks"]["orphaned_forms"]
            logger.info(f"ORPHANED DERIVATIVE FORMS:")
            logger.info(f"  Total forms checked: {orphan_check['total_forms_checked']}")
            logger.info(f"  Orphaned forms: {orphan_check['orphaned_count']}")
            logger.info("")

        # Subtype coverage
        if "subtype_coverage" in results["checks"]:
            subtype_check = results["checks"]["subtype_coverage"]
            logger.info(f"POS SUBTYPE COVERAGE:")
            logger.info(f"  Total subtypes: {subtype_check['total_subtypes']}")
            logger.info(f"  Well-covered: {subtype_check['well_covered_count']}")
            logger.info(f"  Under-covered: {subtype_check['under_covered_count']}")
            if subtype_check["under_covered_count"] > 0:
                logger.info(f"  Most under-covered subtypes:")
                for i, subtype in enumerate(subtype_check["under_covered"][:5], 1):
                    logger.info(
                        f"    {i}. {subtype['pos_subtype']} ({subtype['pos_type']}): {subtype['count']} words"
                    )
            logger.info("")

        # Difficulty distribution
        if "difficulty_distribution" in results["checks"]:
            dist_check = results["checks"]["difficulty_distribution"]
            logger.info(f"DIFFICULTY LEVEL DISTRIBUTION:")
            logger.info(f"  Total trakaido words: {dist_check['total_words']}")
            logger.info(f"  Average per level: {dist_check['average_per_level']:.1f}")
            logger.info(f"  Empty levels: {len(dist_check['gaps'])}")
            if dist_check["gaps"]:
                logger.info(f"    Levels: {dist_check['gaps']}")
            logger.info(f"  Imbalanced levels: {len(dist_check['imbalanced'])}")
            if dist_check["imbalanced"]:
                for level_info in dist_check["imbalanced"][:5]:
                    logger.info(
                        f"    Level {level_info['level']}: {level_info['count']} words (expected ~{level_info['expected_avg']:.0f})"
                    )

        logger.info("=" * 80)
