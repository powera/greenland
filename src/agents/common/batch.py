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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from agents.common.common_args import add_backend_args, add_common_args, get_data_source_config
from clients.batch_queue import BatchQueue, get_batch_manager
from util.telemetry import CostConfig
from storage.backend import create_session as create_backend_session
from storage.translation_helpers import LANGUAGE_FIELDS, set_translation
from sentences.batch_completion import apply_sentence_translation_results

logger = logging.getLogger(__name__)

# Batch API provides 50% discount on token costs
BATCH_DISCOUNT = 0.5


@dataclass
class BatchUsage:
    """Aggregated usage statistics for a batch."""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_reasoning_tokens: int = 0
    request_count: int = 0
    model_name: Optional[str] = None

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def actual_output_tokens(self) -> int:
        """Output tokens excluding reasoning (what you actually see)."""
        return self.total_output_tokens - self.total_reasoning_tokens

    def calculate_cost(self, apply_batch_discount: bool = True) -> float:
        """Calculate cost based on token usage and model.

        Args:
            apply_batch_discount: Whether to apply the 50% batch discount (default True)

        Returns:
            Estimated cost in USD
        """
        if not self.model_name:
            return 0.0

        base_cost = CostConfig.estimate_cost(
            tokens_in=self.total_input_tokens,
            tokens_out=self.total_output_tokens,
            model=self.model_name,
        )

        if apply_batch_discount:
            return base_cost * BATCH_DISCOUNT
        return base_cost


def _extract_usage_from_response(
    response_body: Optional[str],
) -> Tuple[int, int, int, Optional[str]]:
    """Extract token usage from a batch response body.

    Args:
        response_body: JSON string of the response body

    Returns:
        Tuple of (input_tokens, output_tokens, reasoning_tokens, model_name)
    """
    if not response_body:
        return 0, 0, 0, None

    try:
        response = json.loads(response_body)
    except json.JSONDecodeError:
        return 0, 0, 0, None

    input_tokens = 0
    output_tokens = 0
    reasoning_tokens = 0
    model_name = None

    # Handle chat completions format: {"body": {"usage": {...}, "model": ...}}
    if "body" in response:
        body = response["body"]
        usage = body.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        model_name = body.get("model")

        # Extract reasoning tokens from completion_tokens_details
        completion_details = usage.get("completion_tokens_details", {})
        reasoning_tokens = completion_details.get("reasoning_tokens", 0)

    # Handle responses API format: {"usage": {...}, "model": ...}
    elif "usage" in response:
        usage = response.get("usage", {})
        input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0))
        output_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0))
        model_name = response.get("model")

        # Extract reasoning tokens from output_tokens_details
        output_details = usage.get("output_tokens_details", {})
        reasoning_tokens = output_details.get("reasoning_tokens", 0)

    return input_tokens, output_tokens, reasoning_tokens, model_name


def aggregate_batch_usage(requests: Iterable[BatchQueue]) -> BatchUsage:
    """Aggregate usage statistics from batch requests.

    Args:
        requests: Iterable of BatchQueue records with response_body populated

    Returns:
        BatchUsage with aggregated statistics
    """
    usage = BatchUsage()

    for req in requests:
        input_tokens, output_tokens, reasoning_tokens, model_name = _extract_usage_from_response(
            req.response_body
        )
        usage.total_input_tokens += input_tokens
        usage.total_output_tokens += output_tokens
        usage.total_reasoning_tokens += reasoning_tokens
        usage.request_count += 1

        # Use the first model name we find
        if model_name and not usage.model_name:
            usage.model_name = model_name

    return usage


def _report_batch_usage(usage: BatchUsage) -> None:
    """Log batch usage and pricing information."""
    logger.info("")
    logger.info("=" * 80)
    logger.info("BATCH USAGE & PRICING")
    logger.info("=" * 80)
    logger.info("Requests processed: %d", usage.request_count)
    logger.info("Input tokens:       %d", usage.total_input_tokens)
    logger.info("Output tokens:      %d", usage.total_output_tokens)

    # Show reasoning breakdown if present
    if usage.total_reasoning_tokens > 0:
        reasoning_pct = (
            (usage.total_reasoning_tokens / usage.total_output_tokens * 100)
            if usage.total_output_tokens
            else 0
        )
        logger.info("  - Reasoning:      %d (%.0f%%)", usage.total_reasoning_tokens, reasoning_pct)
        logger.info(
            "  - Actual output:  %d (%.0f%%)", usage.actual_output_tokens, 100 - reasoning_pct
        )

    logger.info("Total tokens:       %d", usage.total_tokens)
    logger.info("-" * 40)

    if usage.model_name:
        logger.info("Model: %s", usage.model_name)
        base_cost = usage.calculate_cost(apply_batch_discount=False)
        batch_cost = usage.calculate_cost(apply_batch_discount=True)
        logger.info("Base cost (non-batch): $%.4f", base_cost)
        logger.info("Batch cost (50%% off): $%.4f", batch_cost)
        logger.info("Savings:               $%.4f", base_cost - batch_cost)
    else:
        logger.info("Model: Unknown (unable to calculate pricing)")

    logger.info("=" * 80)


def _group_completed_by_agent(requests: Iterable[BatchQueue]) -> Dict[str, list[BatchQueue]]:
    grouped: Dict[str, list[BatchQueue]] = defaultdict(list)
    for request in requests:
        grouped[request.agent_name].append(request)
    return grouped


def _apply_sentence_translations(
    requests: Iterable[BatchQueue], session: Any, batch_id: str
) -> Dict[str, int]:
    return apply_sentence_translation_results(requests, session, batch_id)


def _apply_voras_translations(
    requests: Iterable[BatchQueue], session: Any, batch_id: str
) -> Dict[str, int]:
    from storage.crud.operation_log import log_translation_change
    from storage.models.schema import Lemma

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
            if not req.response_body:
                continue
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


def _extract_chat_completion_text(response_body: Optional[str]) -> Optional[str]:
    """Pull the assistant message text from a stored chat-completions response.

    Args:
        response_body: JSON string of the batch result's ``response`` object.

    Returns:
        The message content, or None if it could not be located.
    """
    if not response_body:
        return None
    try:
        response = json.loads(response_body)
    except json.JSONDecodeError:
        return None

    body = response.get("body") if isinstance(response.get("body"), dict) else response
    choices = body.get("choices") if isinstance(body, dict) else None
    if not choices:
        return None
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    return content.strip() if isinstance(content, str) else None


def _apply_concept_seed_bodies(
    requests: Iterable[BatchQueue], session: Any, batch_id: str
) -> Dict[str, int]:
    """Create concepts from stashed (seed + generated body) batch results.

    Shared by every agent that queues concept-body generation (``voverukas``,
    ``voveraite``). Each request stashed the full Wikidata seed and model in its
    metadata at submit time, so concept creation needs no further outbound
    calls: the body is the LLM output, the seed is the stored input.

    Args:
        requests: Completed BatchQueue records for a concept-body agent.
        session: Database session.
        batch_id: The batch ID (for logging only).

    Returns:
        ``{"processed", "created", "skipped", "failed"}`` counts.
    """
    from storage.concept_service import create_concept_from_seed
    from storage.wikidata import WikidataConceptSeed

    results = {"processed": 0, "created": 0, "skipped": 0, "failed": 0}

    for req in requests:
        results["processed"] += 1
        try:
            metadata = json.loads(req.additional_metadata) if req.additional_metadata else {}
            seed_data = metadata.get("seed")
            if not seed_data:
                logger.warning("No stashed seed for request %s; skipping", req.custom_id)
                results["failed"] += 1
                continue

            body = _extract_chat_completion_text(req.response_body)
            if not body:
                logger.warning("No generated body for request %s; skipping", req.custom_id)
                results["failed"] += 1
                continue

            seed = WikidataConceptSeed(
                qid=seed_data["qid"],
                title=seed_data["title"],
                summary=seed_data.get("summary", ""),
                sources=list(seed_data.get("sources", [])),
            )
            result = create_concept_from_seed(
                session,
                seed,
                body=body,
                source_model=metadata.get("source_model"),
            )
            if result.status == "created":
                session.commit()
                results["created"] += 1
            else:
                # "exists" / "unresolved" / "failed" — nothing persisted.
                results["skipped" if result.status == "exists" else "failed"] += 1
            logger.info(
                "%s [%s] %s%s",
                result.status.upper(),
                seed.qid,
                seed.title,
                f" - {result.detail}" if result.detail else "",
            )
        except Exception as exc:
            session.rollback()
            results["failed"] += 1
            logger.error(
                "Failed to create concept for request %s (batch %s): %s",
                req.custom_id,
                batch_id,
                exc,
            )

    return results


def _report_concept_seed_results(results: Dict[str, int], agent_name: str) -> None:
    logger.info("\n" + "=" * 80)
    logger.info("BATCH RESULTS SUMMARY (%s)", agent_name.upper())
    logger.info("=" * 80)
    logger.info("Total requests processed: %s", results["processed"])
    logger.info("Concepts created: %s", results["created"])
    logger.info("Skipped (already exist): %s", results["skipped"])
    logger.info("Failed: %s", results["failed"])
    logger.info("=" * 80)


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

        # Calculate and report usage/pricing before applying results
        usage = aggregate_batch_usage(completed_requests)
        _report_batch_usage(usage)

        grouped = _group_completed_by_agent(completed_requests)
        session = create_backend_session(config)
        try:
            for agent_name, requests in grouped.items():
                if agent_name in ("zvirblis", "barsukas_decompose"):
                    result = _apply_sentence_translations(requests, session, args.batch_id)
                    logger.info(
                        "Sentence translations applied: %s updated, %s failed",
                        result["updated"],
                        result["failed"],
                    )
                elif agent_name == "voras":
                    result = _apply_voras_translations(requests, session, args.batch_id)
                    _report_voras_results(result)
                elif agent_name in ("voverukas", "voveraite"):
                    result = _apply_concept_seed_bodies(requests, session, args.batch_id)
                    _report_concept_seed_results(result, agent_name)
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
