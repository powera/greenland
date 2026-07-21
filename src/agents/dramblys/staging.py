"""
Dramblys Agent - Staging and Import Operations

This module handles the staging workflow for pending imports:
- Listing pending imports
- Approving pending imports
- Rejecting pending imports
- Staging new words for review
"""

import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from util.logging_config import get_logger
from agents.dramblys.synonym_screening import has_active_strong_synonym_candidate
from storage.backend.config import DataSourceConfig
from storage.models.imports import PendingImport, PendingImportSynonymCandidate, WordExclusion
from storage.translation_helpers import LANG_CODE_TO_LLM_FIELD
from wordfreq.translation.client import LinguisticClient

logger = get_logger(__name__)


def list_pending_imports(
    session: Any,
    pos_type: Optional[str] = None,
    pos_subtype: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    List words in the pending_imports staging table.

    Args:
        session: Database session
        pos_type: Filter by POS type (noun, verb, adjective, adverb)
        pos_subtype: Filter by POS subtype
        limit: Maximum number of results to return

    Returns:
        Dictionary with pending imports
    """
    logger.info("Listing pending imports...")

    try:
        query = session.query(PendingImport)

        if pos_type:
            query = query.filter(PendingImport.pos_type == pos_type)
        if pos_subtype:
            query = query.filter(PendingImport.pos_subtype == pos_subtype)

        query = query.order_by(PendingImport.frequency_rank.nullslast(), PendingImport.added_at)

        if limit:
            query = query.limit(limit)

        pending_imports = query.all()

        results = []
        for pending in pending_imports:
            synonym_candidate_count = int(
                session.query(PendingImportSynonymCandidate)
                .filter(
                    PendingImportSynonymCandidate.pending_import_id == pending.id,
                    PendingImportSynonymCandidate.status == "active",
                )
                .count()
            )
            strong_synonym_candidate_count = int(
                session.query(PendingImportSynonymCandidate)
                .filter(
                    PendingImportSynonymCandidate.pending_import_id == pending.id,
                    PendingImportSynonymCandidate.status == "active",
                    PendingImportSynonymCandidate.is_strong.is_(True),
                )
                .count()
            )
            results.append(
                {
                    "id": pending.id,
                    "english_word": pending.english_word,
                    "definition": pending.definition,
                    "translation": pending.disambiguation_translation,
                    "language": pending.disambiguation_language,
                    "pos_type": pending.pos_type,
                    "pos_subtype": pending.pos_subtype,
                    "source": pending.source,
                    "frequency_rank": pending.frequency_rank,
                    "notes": pending.notes,
                    "synonym_candidate_count": synonym_candidate_count,
                    "strong_synonym_candidate_count": strong_synonym_candidate_count,
                    "added_at": pending.added_at.isoformat() if pending.added_at else None,
                }
            )

        logger.info(f"Found {len(results)} pending imports")

        return {"count": len(results), "pending_imports": results}

    except Exception as e:
        logger.error(f"Error listing pending imports: {e}")
        return {"error": str(e), "count": 0, "pending_imports": []}


def _find_duplicate_lemma(
    session: Any,
    word: str,
    pos_type: Optional[str],
    pos_subtype: Optional[str],
) -> Optional[Any]:
    """Check if a lemma already exists for this word/POS/subtype combination.

    Returns the first matching Lemma, or None if no duplicate found.
    """
    from sqlalchemy import func

    from storage.models.schema import Lemma

    query = session.query(Lemma).filter(func.lower(Lemma.lemma_text) == word.strip().lower())

    if pos_type:
        query = query.filter(Lemma.pos_type == pos_type)

    if pos_subtype:
        query = query.filter(Lemma.pos_subtype == pos_subtype)

    return query.first()


def approve_pending_import(
    session: Any,
    pending_import_id: int,
    data_source_config: DataSourceConfig,
    model: str = "gpt-5.4-mini",
    debug: bool = False,
) -> Dict[str, Any]:
    """
    Approve a pending import and convert it to a full Lemma/DerivativeForm entry.

    This is step 2 of the two-step import process.  Queries the LLM for full
    definitions (including pos_subtype and translations), checks for duplicate
    lemmas, then creates the lemma with a proper GUID.

    Args:
        session: Database session
        pending_import_id: ID of the PendingImport record
        data_source_config: Data source configuration for LinguisticClient
        model: LLM model to use for processing
        debug: Debug flag

    Returns:
        Dictionary with approval results
    """
    logger.info(f"Approving pending import ID {pending_import_id}...")

    try:
        # Get the pending import
        pending = session.query(PendingImport).filter(PendingImport.id == pending_import_id).first()

        if not pending:
            logger.error(f"Pending import ID {pending_import_id} not found")
            return {"error": f"Pending import ID {pending_import_id} not found", "success": False}

        if has_active_strong_synonym_candidate(session, pending_import_id):
            logger.info(
                "Pending import ID %s has active strong synonym candidates; refusing normal approval",
                pending_import_id,
            )
            return {
                "success": False,
                "word": pending.english_word,
                "error": (
                    "Strong synonym candidates exist. Use 'Use As Synonym' or "
                    "'Create Anyway' from the pending import detail page."
                ),
            }

        word = pending.english_word
        pending_definition = pending.definition
        pending_pos_type = pending.pos_type
        pending_pos_subtype = pending.pos_subtype

        logger.info(f"Approving word '{word}' (sense: {pending_definition[:60]}...)")

        # Use LinguisticClient to get full definitions from the LLM, including
        # pos_subtype (needed for GUID) and translations.
        client_config = DataSourceConfig(
            backend_type=data_source_config.backend_type,
            sqlite_path=data_source_config.sqlite_path,
            jsonl_data_dir=data_source_config.jsonl_data_dir,
            postgres_url=data_source_config.postgres_url,
            barsukas_url=data_source_config.barsukas_url,
            cache_only=data_source_config.cache_only,
            use_word2vec=data_source_config.use_word2vec,
            model=model,
            debug=debug,
            openai_api_key=data_source_config.openai_api_key,
            anthropic_api_key=data_source_config.anthropic_api_key,
            google_api_key=data_source_config.google_api_key,
        )
        client = LinguisticClient(config=client_config)

        example_sentence: Optional[str] = pending.example_sentence

        if pending_pos_type and pending_pos_subtype:
            # Already staged via the detail page — use stored values to avoid a redundant LLM call.
            logger.info(
                f"Using pre-staged data for '{word}': {pending_pos_type}/{pending_pos_subtype}"
            )
            definitions_list: List[Dict[str, Any]] = [
                {
                    "pos": pending_pos_type,
                    "pos_subtype": pending_pos_subtype,
                    "definition": pending_definition,
                    "lemma": word,
                }
            ]
        else:
            definitions_list, llm_success = client.query_definitions(
                word, example_sentence=example_sentence
            )
            if not llm_success or not definitions_list:
                logger.error(f"LLM query for definitions of '{word}' failed")
                return {
                    "success": False,
                    "word": word,
                    "error": f"Failed to get definitions from LLM for '{word}'",
                }

            # If the pending import has a pos_type, keep only definitions that
            # match that POS so we don't create unrelated senses.
            if pending_pos_type:
                matching_defs = [d for d in definitions_list if d.get("pos") == pending_pos_type]
                # Fall back to the full list if nothing matched (LLM may use
                # slightly different POS labels).
                if matching_defs:
                    definitions_list = matching_defs

        # Check for duplicates: for each definition the LLM returned, see if a
        # lemma with the same word + POS type + subtype already exists.
        filtered_definitions: List[Dict[str, Any]] = []
        for def_data in definitions_list:
            llm_pos_type = def_data.get("pos")
            llm_pos_subtype = def_data.get("pos_subtype")
            existing = _find_duplicate_lemma(session, word, llm_pos_type, llm_pos_subtype)
            if existing:
                logger.info(
                    f"Skipping duplicate: '{word}' already exists as "
                    f"{llm_pos_type}/{llm_pos_subtype} (lemma id={existing.id}, "
                    f"guid={existing.guid})"
                )
            else:
                filtered_definitions.append(def_data)

        if not filtered_definitions:
            # Every sense already exists — remove the pending import and report.
            session.delete(pending)
            session.commit()
            msg = f"'{word}' already exists in the database for all senses; removed from pending."
            logger.info(msg)
            return {"success": True, "word": word, "message": msg}

        try:
            from wordfreq.translation import word_processing

            success = word_processing.process_word(
                client.client,
                word,
                client.get_session,
                refresh=False,
                definitions_list=filtered_definitions,
            )
        except ValueError as e:
            # Handle subtype validation errors
            if "Unknown subtype" in str(e):
                logger.error(f"Subtype validation error for '{word}': {e}")
                logger.error(f"The LLM returned an invalid subtype. This word needs manual review.")
                return {"success": False, "word": word, "error": f"Invalid subtype: {e}"}
            raise

        if success:
            # Delete the pending import entry
            session.delete(pending)
            session.commit()

            # Look up the newly created lemma so callers can trigger follow-on tasks
            from storage.models.schema import Lemma

            new_lemma = (
                session.query(Lemma)
                .filter(Lemma.lemma_text == word)
                .order_by(Lemma.id.desc())
                .first()
            )
            new_lemma_id: Optional[int] = new_lemma.id if new_lemma else None

            logger.info(f"Successfully approved and imported '{word}' (lemma_id={new_lemma_id})")
            return {
                "success": True,
                "word": word,
                "lemma_id": new_lemma_id,
                "message": f"Successfully imported '{word}'",
            }
        else:
            logger.error(f"Failed to import '{word}'")
            return {"success": False, "word": word, "error": f"Failed to import '{word}'"}

    except Exception as e:
        logger.error(f"Error approving pending import: {e}")
        session.rollback()
        return {"error": str(e), "success": False}


def reject_pending_import(
    session: Any,
    pending_import_id: int,
    reason: str = "manual_rejection",
    add_to_exclusions: bool = True,
) -> Dict[str, Any]:
    """
    Reject a pending import and optionally add to exclusions list.

    Args:
        session: Database session
        pending_import_id: ID of the PendingImport record
        reason: Reason for rejection
        add_to_exclusions: If True, add to WordExclusion table

    Returns:
        Dictionary with rejection results
    """
    logger.info(f"Rejecting pending import ID {pending_import_id}...")

    try:
        # Get the pending import
        pending = session.query(PendingImport).filter(PendingImport.id == pending_import_id).first()

        if not pending:
            logger.error(f"Pending import ID {pending_import_id} not found")
            return {"error": f"Pending import ID {pending_import_id} not found", "success": False}

        word = pending.english_word

        # Add to exclusions if requested
        if add_to_exclusions:
            # Check if already excluded
            existing_exclusion = (
                session.query(WordExclusion)
                .filter(WordExclusion.excluded_word == word, WordExclusion.language_code == "en")
                .first()
            )

            if not existing_exclusion:
                exclusion = WordExclusion(
                    excluded_word=word,
                    language_code="en",
                    exclusion_reason=reason,
                    notes=f"Rejected from pending import. Original definition: {pending.definition[:100]}",
                )
                session.add(exclusion)
                logger.info(f"Added '{word}' to exclusions")

        # Delete the pending import
        session.delete(pending)
        session.commit()

        logger.info(f"Rejected pending import for '{word}'")
        return {
            "success": True,
            "word": word,
            "added_to_exclusions": add_to_exclusions,
            "message": f"Rejected '{word}'",
        }

    except Exception as e:
        logger.error(f"Error rejecting pending import: {e}")
        session.rollback()
        return {"error": str(e), "success": False}


def stage_missing_words_for_import(
    session: Any,
    missing_words: List[Dict[str, Any]],
    db_path: str,
    limit: Optional[int] = None,
    model: str = "gpt-5.4-mini",
    throttle: float = 1.0,
    dry_run: bool = False,
    target_language: str = "lt",
    debug: bool = False,
) -> Dict[str, Any]:
    """
    Stage high-frequency missing words to the pending_imports table.

    This is step 1 of a two-step import process:
    1. Identify candidate words and query LLM for definitions/translations -> PendingImport
    2. Review/approve pending imports -> Convert to Lemma/DerivativeForm

    Args:
        session: Database session
        missing_words: List of missing words from check_high_frequency_missing_words
        db_path: Database path for LinguisticClient
        limit: Maximum number of words to stage
        model: LLM model to use for definitions
        throttle: Seconds to wait between API calls
        dry_run: If True, show what would be staged without making changes
        target_language: Language code for disambiguation translations (default: lt)
        debug: Debug flag

    Returns:
        Dictionary with staging results
    """
    logger.info("Staging high-frequency missing words for import...")

    total_missing = len(missing_words)

    if total_missing == 0:
        logger.info("No high-frequency missing words found!")
        return {
            "total_missing": 0,
            "staged": 0,
            "skipped_already_pending": 0,
            "failed": 0,
            "dry_run": dry_run,
        }

    logger.info(f"Found {total_missing} high-frequency missing words")

    # Apply limit if specified
    if limit:
        words_to_stage = missing_words[:limit]
        logger.info(f"Staging limited to {limit} words")
    else:
        words_to_stage = missing_words

    if dry_run:
        logger.info(f"DRY RUN: Would stage {len(words_to_stage)} words:")
        for word_info in words_to_stage[:20]:
            corpus_str = ", ".join(
                [f"{c['corpus']}:{c['rank']}" for c in word_info["corpus_frequencies"][:2]]
            )
            logger.info(
                f"  - '{word_info['word']}' (overall rank: {word_info['overall_rank']}, {corpus_str})"
            )
        if len(words_to_stage) > 20:
            logger.info(f"  ... and {len(words_to_stage) - 20} more")
        return {
            "total_missing": total_missing,
            "would_stage": len(words_to_stage),
            "dry_run": True,
            "sample": words_to_stage[:20],
        }

    # Initialize client for LLM-based definitions
    client = LinguisticClient(model=model, db_path=db_path, debug=debug)

    staged = 0
    skipped_already_pending = 0
    failed = 0

    try:
        for i, word_info in enumerate(words_to_stage, 1):
            word = word_info["word"]
            rank = word_info["overall_rank"]
            logger.info(f"\n[{i}/{len(words_to_stage)}] Staging: '{word}' (rank: {rank})")

            # Check if already in pending_imports
            existing_pending = (
                session.query(PendingImport).filter(PendingImport.english_word == word).first()
            )

            if existing_pending:
                logger.info(f"Word '{word}' already in pending imports, skipping")
                skipped_already_pending += 1
                continue

            # Query LLM for definition and translation
            # Use the linguistic client to get comprehensive word data
            definitions_list, success = client.query_definitions(word)
            if not success:
                logger.error(f"Failed to get definitions for '{word}'")
                failed += 1
                if i < len(words_to_stage):
                    time.sleep(throttle)
                continue

            word_data = {"definitions": definitions_list}

            if not word_data or "definitions" not in word_data:
                logger.error(f"Failed to get definitions for '{word}'")
                failed += 1
                if i < len(words_to_stage):
                    time.sleep(throttle)
                continue

            # For each definition/sense, create a pending import entry
            definitions = word_data.get("definitions", [])
            for definition_data in definitions:
                definition_text = definition_data.get("definition", "")
                # The schema uses "pos" not "pos_type"
                pos_type = definition_data.get("pos", None)
                pos_subtype = definition_data.get("pos_subtype", None)

                # Get translation for disambiguation. The schema keys are LLM
                # field names ("lithuanian_translation"), not language codes, so
                # map through LANG_CODE_TO_LLM_FIELD rather than building
                # f"{target_language}_translation" -- that produced
                # "lt_translation", which never matched, so the disambiguation
                # translation was always empty.
                translation_key = LANG_CODE_TO_LLM_FIELD[target_language]
                translation = definition_data.get(translation_key, "")

                if not definition_text:
                    logger.warning(f"Missing definition for '{word}', skipping this sense")
                    continue

                # Translation is optional - we can use definition as fallback for disambiguation
                if not translation:
                    logger.debug(
                        f"No {target_language} translation for '{word}', will use definition for disambiguation"
                    )

                # Create pending import entry
                pending = PendingImport(
                    english_word=word,
                    definition=definition_text,
                    disambiguation_translation=translation,
                    disambiguation_language=target_language,
                    pos_type=pos_type,
                    pos_subtype=pos_subtype,
                    source="dramblys_frequency_check",
                    frequency_rank=rank,
                    notes=f"Found in top frequency words",
                )

                session.add(pending)
                staged += 1
                logger.info(
                    f"Staged '{word}' ({pos_type}/{pos_subtype}): {definition_text[:60]}..."
                )

            session.commit()

            # Throttle to avoid overloading the API
            if i < len(words_to_stage):
                time.sleep(throttle)

    except Exception as e:
        logger.error(f"Error during staging: {e}")
        session.rollback()
        return {
            "error": str(e),
            "total_missing": total_missing,
            "staged": staged,
            "skipped_already_pending": skipped_already_pending,
            "failed": failed,
            "dry_run": dry_run,
        }

    logger.info(f"\n{'='*60}")
    logger.info(f"Staging complete:")
    logger.info(f"  Total missing: {total_missing}")
    logger.info(f"  Processed: {len(words_to_stage)}")
    logger.info(f"  Staged: {staged}")
    logger.info(f"  Skipped (already pending): {skipped_already_pending}")
    logger.info(f"  Failed: {failed}")
    logger.info(f"{'='*60}")

    return {
        "total_missing": total_missing,
        "processed": len(words_to_stage),
        "staged": staged,
        "skipped_already_pending": skipped_already_pending,
        "failed": failed,
        "dry_run": dry_run,
    }
