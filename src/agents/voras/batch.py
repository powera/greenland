"""
Voras Agent - Batch Operations

This module handles batch processing operations:
- Submitting batches to OpenAI
- Checking batch status
- Retrieving and processing batch results
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from clients.batch_queue import get_batch_manager
from wordfreq.storage.crud.operation_log import log_translation_change
from wordfreq.storage.translation_helpers import (
    LANGUAGE_FIELDS,
    get_translation,
    set_translation,
    get_language_name
)

logger = logging.getLogger(__name__)


def submit_batch(debug: bool = False, agent_name: str = "voras", metadata: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Submit all pending batch requests to OpenAI.

    Args:
        debug: Debug flag
        agent_name: Filter by agent name (default: "voras")
        metadata: Optional metadata to attach to the batch

    Returns:
        Dictionary with batch_id and file_id
    """
    batch_manager = get_batch_manager(debug=debug)

    # Get all pending requests for this agent
    pending = batch_manager.get_pending_requests(agent_name=agent_name)

    if not pending:
        logger.warning("No pending batch requests found")
        return {"batch_id": None, "file_id": None, "count": 0}

    logger.info(f"Submitting {len(pending)} pending requests as a batch...")

    # Submit batch
    batch_id, file_id = batch_manager.submit_batch(pending, batch_metadata=metadata)

    logger.info(f"Batch submitted successfully!")
    logger.info(f"  Batch ID: {batch_id}")
    logger.info(f"  File ID: {file_id}")
    logger.info(f"  Request count: {len(pending)}")
    logger.info(f"\nTo check status: use --batch-status {batch_id}")
    logger.info(f"To retrieve results: use --batch-retrieve {batch_id}")

    return {
        "batch_id": batch_id,
        "file_id": file_id,
        "count": len(pending)
    }


def check_batch_status(batch_id: str, debug: bool = False) -> Dict[str, Any]:
    """Check the status of a submitted batch.

    Args:
        batch_id: OpenAI batch ID
        debug: Debug flag

    Returns:
        Batch status information
    """
    batch_manager = get_batch_manager(debug=debug)
    batch_info = batch_manager.check_batch_status(batch_id)

    status = batch_info["status"]
    counts = batch_info.get("request_counts", {})

    logger.info(f"Batch {batch_id} status: {status}")
    logger.info(f"  Total requests: {counts.get('total', 0)}")
    logger.info(f"  Completed: {counts.get('completed', 0)}")
    logger.info(f"  Failed: {counts.get('failed', 0)}")

    return batch_info


def retrieve_batch_results(batch_id: str, session, debug: bool = False) -> Dict[str, Any]:
    """Retrieve and process results from a completed batch.

    Args:
        batch_id: OpenAI batch ID
        session: Database session
        debug: Debug flag

    Returns:
        Dictionary with processing results
    """
    from wordfreq.storage.models.schema import Lemma

    batch_manager = get_batch_manager(debug=debug)

    # Download results from OpenAI and store in batch queue database
    result_count = batch_manager.retrieve_batch_results(batch_id)
    logger.info(f"Retrieved {result_count} results from batch {batch_id}")

    # Get completed requests
    completed = batch_manager.get_completed_requests(
        agent_name="voras",
        batch_id=batch_id
    )

    # Process each result and update the linguistics database
    results = {
        "total_processed": 0,
        "total_updated": 0,
        "total_failed": 0,
        "by_language": {}
    }

    # Initialize language tracking
    languages_to_update = [lc for lc in LANGUAGE_FIELDS.keys() if lc != "lt"]
    for lang_code in languages_to_update:
        results["by_language"][lang_code] = {
            "language_name": get_language_name(lang_code),
            "updated": 0,
            "failed": 0
        }

    translation_field_map = {
        "zh": "chinese_translation",
        "ko": "korean_translation",
        "fr": "french_translation",
        "sw": "swahili_translation",
        "vi": "vietnamese_translation"
    }

    for req in completed:
        results["total_processed"] += 1

        try:
            # Parse response
            response_data = json.loads(req.response_body)

            # Extract translations from the response
            # The response structure matches OpenAI Responses API
            translations = {}
            if response_data.get("output"):
                for output_item in response_data["output"]:
                    if output_item.get("type") == "message" and output_item.get("content"):
                        for content_item in output_item["content"]:
                            if content_item.get("type") == "output_text":
                                text_content = content_item.get("text", "")
                                if text_content:
                                    translations = json.loads(text_content)
                                break

            if not translations:
                logger.warning(f"No translations found in response for request {req.custom_id}")
                results["total_failed"] += 1
                continue

            # Get the lemma from database
            lemma_id = req.entity_id
            lemma = session.query(Lemma).filter_by(id=lemma_id).first()

            if not lemma:
                logger.warning(f"Lemma {lemma_id} not found for request {req.custom_id}")
                results["total_failed"] += 1
                continue

            # Update translations
            updated_count = 0
            for lang_code in languages_to_update:
                llm_field = translation_field_map.get(lang_code)
                translation = translations.get(llm_field, "").strip()

                if translation:
                    # Use helper function which returns (old_translation, new_translation)
                    old_translation, new_translation = set_translation(session, lemma, lang_code, translation)

                    # Log the change
                    log_translation_change(
                        session=session,
                        source=f"voras-agent/batch",
                        operation_type="translation",
                        lemma_id=lemma.id,
                        language_code=lang_code,
                        old_translation=old_translation,
                        new_translation=new_translation
                    )

                    results["by_language"][lang_code]["updated"] += 1
                    updated_count += 1
                else:
                    results["by_language"][lang_code]["failed"] += 1

            if updated_count > 0:
                session.commit()
                results["total_updated"] += 1
                logger.info(f"Updated {updated_count} translations for '{lemma.lemma_text}' (ID: {lemma_id})")

        except Exception as e:
            logger.error(f"Error processing result for {req.custom_id}: {e}")
            results["total_failed"] += 1
            session.rollback()

    # Print summary
    logger.info("\n" + "=" * 80)
    logger.info("BATCH RESULTS SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total requests processed: {results['total_processed']}")
    logger.info(f"Lemmas updated: {results['total_updated']}")
    logger.info(f"Failed: {results['total_failed']}")
    logger.info("\nBy language:")
    for lang_code in languages_to_update:
        lang_result = results["by_language"][lang_code]
        logger.info(
            f"  {lang_result['language_name']}: "
            f"{lang_result['updated']} updated, {lang_result['failed']} failed"
        )
    logger.info("=" * 80)

    return results
