"""
Helpers to fix French verb conjugations moved out from agent.

Functions here mirror the behavior previously implemented inside
`src/agents/vilkas/agent.py::_fix_french_verb_conjugations`.
"""

import logging
import time
from typing import Dict, Optional

from wordfreq.storage.models.schema import Lemma
from wordfreq.storage.translation_helpers import get_translation
from wordfreq.translation.client import LinguisticClient

logger = logging.getLogger(__name__)


def fix_french_verb_conjugations(
    agent,
    limit: Optional[int] = None,
    model: Optional[str] = None,
    throttle: float = 1.0,
    dry_run: bool = False,
    guid: Optional[str] = None,
) -> Dict[str, any]:
    """Generate missing French verb conjugations using provided `agent`.

    The `agent` is expected to provide methods and attributes used by
    the original implementation: `get_session()`, `check_verb_conjugation_coverage()`,
    `config`, `db_path`, and `debug`.
    """
    effective_model = model if model is not None else agent.config.model

    from wordfreq.translation.generate_french_verb_forms import (
        get_french_verb_lemmas,
        process_lemma,
    )

    logger.info("Finding French verbs needing conjugations...")

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

            if lemma.pos_type != "verb":
                logger.info(f"Lemma with GUID {guid} is not a verb (it's {lemma.pos_type})")
                return {
                    "total_needing_fix": 0,
                    "processed": 0,
                    "successful": 0,
                    "failed": 0,
                    "dry_run": dry_run,
                    "guid_filter": guid,
                }

            verbs_needing_conjugations = [
                {
                    "guid": lemma.guid,
                    "english": lemma.lemma_text,
                    "translation": get_translation(session, lemma, "fr")
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
        check_results = agent.check_verb_conjugation_coverage(language_code="fr")
        if "error" in check_results:
            return check_results

        verbs_needing_conjugations = check_results["verbs_needing_conjugations"]
        total_needs_fix = len(verbs_needing_conjugations)

    if total_needs_fix == 0:
        logger.info("No French verbs need conjugations!")
        return {
            "total_needing_fix": 0,
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "dry_run": dry_run,
        }

    logger.info(f"Found {total_needs_fix} French verbs needing conjugations")

    # Apply limit if specified
    if limit:
        verbs_to_process = verbs_needing_conjugations[:limit]
        logger.info(f"Processing limited to {limit} verbs")
    else:
        verbs_to_process = verbs_needing_conjugations

    if dry_run:
        logger.info(f"DRY RUN: Would process {len(verbs_to_process)} verbs:")
        for verb in verbs_to_process[:10]:
            logger.info(
                f"  - {verb['english']} -> {verb['translation']} (level {verb['difficulty_level']})"
            )
        if len(verbs_to_process) > 10:
            logger.info(f"  ... and {len(verbs_to_process) - 10} more")
        return {
            "total_needing_fix": total_needs_fix,
            "would_process": len(verbs_to_process),
            "dry_run": True,
            "sample": verbs_to_process[:10],
        }

    # Initialize client for LLM-based generation
    client = LinguisticClient(model=effective_model, db_path=agent.db_path, debug=agent.debug)

    # Process each verb
    successful = 0
    failed = 0

    session = agent.get_session()
    try:
        for i, verb_info in enumerate(verbs_to_process, 1):
            logger.info(
                f"\n[{i}/{len(verbs_to_process)}] Processing: {verb_info['english']} -> {verb_info['translation']}"
            )

            lemma = session.query(Lemma).filter(Lemma.guid == verb_info["guid"]).first()

            if not lemma:
                logger.error(f"Could not find lemma with GUID {verb_info['guid']}")
                failed += 1
                continue

            success = process_lemma(client=client, lemma_id=lemma.id, db_path=agent.db_path)

            if success:
                successful += 1
                logger.info(f"Successfully generated conjugations for '{verb_info['english']}'")
            else:
                failed += 1
                logger.error(f"Failed to generate conjugations for '{verb_info['english']}'")

            if i < len(verbs_to_process):
                time.sleep(throttle)

    finally:
        session.close()

    logger.info(f"\n{'='*60}")
    logger.info("Fix complete:")
    logger.info(f"  Total needing fix: {total_needs_fix}")
    logger.info(f"  Processed: {len(verbs_to_process)}")
    logger.info(f"  Successful: {successful}")
    logger.info(f"  Failed: {failed}")
    logger.info(f"{'='*60}")

    return {
        "total_needing_fix": total_needs_fix,
        "processed": len(verbs_to_process),
        "successful": successful,
        "failed": failed,
        "dry_run": dry_run,
    }
