#!/usr/bin/env python3
"""
Common batch utilities for checking status and completing batches.

This script retrieves batch results and applies them for supported agents.
"""

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, Optional

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from agents.common.common_args import add_backend_args, add_common_args, get_data_source_config
from clients.batch_queue import BatchQueue, get_batch_manager
from wordfreq.storage.backend import create_session as create_backend_session
from wordfreq.storage.translation_helpers import LANGUAGE_FIELDS, set_translation
from wordfreq.translation.sentence import store_translation_results

logger = logging.getLogger(__name__)


def _group_completed_by_agent(requests: Iterable[BatchQueue]) -> Dict[str, list[BatchQueue]]:
    grouped: Dict[str, list[BatchQueue]] = defaultdict(list)
    for request in requests:
        grouped[request.agent_name].append(request)
    return grouped


def _apply_sentence_translations(
    requests: Iterable[BatchQueue], session, batch_id: str
) -> Dict[str, int]:
    sentences_updated = 0
    failed = 0

    for req in requests:
        sentence_id = req.entity_id
        if not sentence_id:
            continue

        try:
            response = json.loads(req.response_body)
            content = response["body"]["choices"][0]["message"]["content"]
            translations = json.loads(content)

            store_translation_results(sentence_id, translations, session)
            sentences_updated += 1

        except Exception as exc:
            failed += 1
            logger.error(
                "Failed to apply sentence translations for sentence %s (batch %s): %s",
                sentence_id,
                batch_id,
                exc,
            )
            session.rollback()

    return {"updated": sentences_updated, "failed": failed}


def _apply_voras_translations(
    requests: Iterable[BatchQueue], session, batch_id: str
) -> Dict[str, int]:
    from wordfreq.storage.crud.operation_log import log_translation_change
    from wordfreq.storage.models.schema import Lemma

    results = {"processed": 0, "updated": 0, "failed": 0}

    languages_to_update = [lc for lc in LANGUAGE_FIELDS.keys() if lc != "lt"]
    translation_field_map = {
        "zh": "chinese_translation",
        "ko": "korean_translation",
        "fr": "french_translation",
        "sw": "swahili_translation",
        "vi": "vietnamese_translation",
    }

    for req in requests:
        results["processed"] += 1

        try:
            response_data = json.loads(req.response_body)
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
                logger.warning("No translations found for request %s", req.custom_id)
                results["failed"] += 1
                continue

            lemma_id = req.entity_id
            lemma = session.query(Lemma).filter_by(id=lemma_id).first()

            if not lemma:
                logger.warning("Lemma %s not found for request %s", lemma_id, req.custom_id)
                results["failed"] += 1
                continue

            updated_count = 0
            for lang_code in languages_to_update:
                llm_field = translation_field_map.get(lang_code)
                translation = translations.get(llm_field, "").strip()

                if translation:
                    old_translation, new_translation = set_translation(
                        session, lemma, lang_code, translation
                    )
                    log_translation_change(
                        session=session,
                        source="voras-agent/batch",
                        operation_type="translation",
                        lemma_id=lemma.id,
                        language_code=lang_code,
                        old_translation=old_translation,
                        new_translation=new_translation,
                    )
                    updated_count += 1

            if updated_count > 0:
                session.commit()
                results["updated"] += 1
            else:
                results["failed"] += 1

        except Exception as exc:
            results["failed"] += 1
            session.rollback()
            logger.error(
                "Failed to apply voras translations for request %s (batch %s): %s",
                req.custom_id,
                batch_id,
                exc,
            )

    return results


def _report_voras_results(results: Dict[str, int]) -> None:
    logger.info("\n" + "=" * 80)
    logger.info("BATCH RESULTS SUMMARY (VORAS)")
    logger.info("=" * 80)
    logger.info("Total requests processed: %s", results["processed"])
    logger.info("Lemmas updated: %s", results["updated"])
    logger.info("Failed: %s", results["failed"])
    logger.info("=" * 80)


def get_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Common batch status/completion utility")
    add_common_args(parser)
    add_backend_args(parser)

    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Check status of a batch")
    status_parser.add_argument("--batch-id", required=True, help="Batch ID to check")

    complete_parser = subparsers.add_parser(
        "complete", help="Retrieve batch results and apply updates"
    )
    complete_parser.add_argument("--batch-id", required=True, help="Batch ID to complete")
    complete_parser.add_argument(
        "--agent",
        help="Optional agent name to restrict processing (e.g., zvirblis, voras)",
    )

    return parser


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    parser = get_argument_parser()
    args = parser.parse_args()

    config = get_data_source_config(args)
    manager = get_batch_manager(debug=args.debug)

    if args.command == "status":
        batch_info = manager.check_batch_status(args.batch_id)

        logger.info("=" * 80)
        logger.info("BATCH STATUS")
        logger.info("=" * 80)
        logger.info("Batch ID: %s", batch_info["id"])
        logger.info("Status: %s", batch_info["status"])
        logger.info("Created at: %s", batch_info.get("created_at"))

        counts = batch_info.get("request_counts", {})
        logger.info("Total requests: %s", counts.get("total", 0))
        logger.info("Completed: %s", counts.get("completed", 0))
        logger.info("Failed: %s", counts.get("failed", 0))
        logger.info("=" * 80)
        return 0

    if args.command == "complete":
        count = manager.retrieve_batch_results(args.batch_id)
        logger.info("Retrieved %s results from batch %s", count, args.batch_id)

        completed_requests = manager.get_completed_requests(batch_id=args.batch_id)
        if args.agent:
            completed_requests = [
                request for request in completed_requests if request.agent_name == args.agent
            ]

        if not completed_requests:
            logger.warning("No completed requests found for batch %s", args.batch_id)
            return 0

        grouped = _group_completed_by_agent(completed_requests)
        session = create_backend_session(config)
        try:
            for agent_name, requests in grouped.items():
                if agent_name == "zvirblis":
                    result = _apply_sentence_translations(requests, session, args.batch_id)
                    logger.info(
                        "Sentence translations applied: %s updated, %s failed",
                        result["updated"],
                        result["failed"],
                    )
                elif agent_name == "voras":
                    result = _apply_voras_translations(requests, session, args.batch_id)
                    _report_voras_results(result)
                else:
                    logger.warning(
                        "No completion handler for agent '%s' (batch %s)",
                        agent_name,
                        args.batch_id,
                    )
        finally:
            session.close()

        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
