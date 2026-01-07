"""
Helpers to fix Lithuanian noun declensions moved out from agent.

Functions here mirror the behavior previously implemented inside
`src/agents/vilkas/agent.py::_fix_lithuanian_noun_declensions`.
"""

import logging
import time
from typing import Dict, Optional

from wordfreq.storage.models.schema import Lemma
from wordfreq.storage.translation_helpers import get_translation
from wordfreq.translation.client import LinguisticClient

logger = logging.getLogger(__name__)


def fix_lithuanian_noun_declensions(
    agent,
    limit: Optional[int] = None,
    model: Optional[str] = None,
    throttle: float = 1.0,
    dry_run: bool = False,
    source: str = "llm",
    guid: Optional[str] = None,
) -> Dict[str, any]:
    """Generate missing Lithuanian noun declensions using provided `agent`.

    The `agent` is expected to provide methods and attributes used by
    the original implementation: `get_session()`, `check_noun_declension_coverage()`,
    `config`, `db_path`, and `debug`.
    """
    effective_model = model if model is not None else agent.config.model

    from wordfreq.translation.generate_lithuanian_noun_forms import (
        get_lithuanian_noun_lemmas,
        process_lemma,
    )

    logger.info("Finding Lithuanian nouns needing declensions...")

    # If GUID is specified, process that specific lemma directly
    if guid:
        session = agent.get_session()
        try:
            lemma = session.query(Lemma).filter(Lemma.guid == guid).first()
            if not lemma:
                logger.info(f"Lemma with GUID {guid} not found")
                return {
                    "total_needing_fix": 0,
                    "processed": 0,
                    "successful": 0,
                    "failed": 0,
                    "dry_run": dry_run,
                    "guid_filter": guid,
                }

            if lemma.pos_type != "noun":
                logger.info(f"Lemma with GUID {guid} is not a noun (it's {lemma.pos_type})")
                return {
                    "total_needing_fix": 0,
                    "processed": 0,
                    "successful": 0,
                    "failed": 0,
                    "dry_run": dry_run,
                    "guid_filter": guid,
                }

            nouns_needing_declensions = [
                {
                    "guid": lemma.guid,
                    "english": lemma.lemma_text,
                    "lithuanian": get_translation(session, lemma, "lt")
                    or "(from LemmaTranslation)",
                    "pos_subtype": lemma.pos_subtype,
                    "difficulty_level": lemma.difficulty_level,
                    "current_form_count": 0,
                }
            ]
            total_needs_fix = 1
        finally:
            session.close()
    else:
        check_results = agent.check_noun_declension_coverage()
        if "error" in check_results:
            return check_results

        nouns_needing_declensions = check_results["nouns_needing_declensions"]
        total_needs_fix = len(nouns_needing_declensions)

    if total_needs_fix == 0:
        logger.info("No Lithuanian nouns need declensions!")
        return {
            "total_needing_fix": 0,
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "dry_run": dry_run,
        }

    logger.info(f"Found {total_needs_fix} Lithuanian nouns needing declensions")

    # Apply limit if specified
    if limit:
        nouns_to_process = nouns_needing_declensions[:limit]
        logger.info(f"Processing limited to {limit} nouns")
    else:
        nouns_to_process = nouns_needing_declensions

    if dry_run:
        logger.info(f"DRY RUN: Would process {len(nouns_to_process)} nouns:")
        for noun in nouns_to_process[:10]:
            logger.info(
                f"  - {noun['english']} -> {noun['lithuanian']} (level {noun['difficulty_level']})"
            )
        if len(nouns_to_process) > 10:
            logger.info(f"  ... and {len(nouns_to_process) - 10} more")
        return {
            "total_needing_fix": total_needs_fix,
            "would_process": len(nouns_to_process),
            "dry_run": True,
            "sample": nouns_to_process[:10],
        }

    # Initialize client for LLM-based generation
    client = LinguisticClient(model=effective_model, db_path=agent.db_path, debug=agent.debug)

    # Process each noun
    successful = 0
    failed = 0

    session = agent.get_session()
    try:
        for i, noun_info in enumerate(nouns_to_process, 1):
            logger.info(
                f"\n[{i}/{len(nouns_to_process)}] Processing: {noun_info['english']} -> {noun_info['lithuanian']}"
            )

            lemma = session.query(Lemma).filter(Lemma.guid == noun_info["guid"]).first()

            if not lemma:
                logger.error(f"Could not find lemma with GUID {noun_info['guid']}")
                failed += 1
                continue

            success = process_lemma(
                client=client, lemma_id=lemma.id, db_path=agent.db_path, source=source
            )

            if success:
                successful += 1
                logger.info(f"Successfully generated declensions for '{noun_info['english']}'")
            else:
                failed += 1
                logger.error(f"Failed to generate declensions for '{noun_info['english']}'")

            if i < len(nouns_to_process):
                time.sleep(throttle)

    finally:
        session.close()

    logger.info(f"\n{'='*60}")
    logger.info("Fix complete:")
    logger.info(f"  Total needing fix: {total_needs_fix}")
    logger.info(f"  Processed: {len(nouns_to_process)}")
    logger.info(f"  Successful: {successful}")
    logger.info(f"  Failed: {failed}")
    logger.info(f"{'='*60}")

    return {
        "total_needing_fix": total_needs_fix,
        "processed": len(nouns_to_process),
        "successful": successful,
        "failed": failed,
        "dry_run": dry_run,
    }
