#!/usr/bin/env python3
"""
Voveraite - create concepts from an explicit list of Wikidata Q-ids.

"Voveraite" is another "little squirrel" diminutive, kin to **Vovere** (the
concept *generator*) and **Voverukas** (the red-link *ranker*). Where Voverukas
*discovers* topics by ranking red links, Voveraite takes a hand-picked list of
Wikidata Q-ids and turns each into a concept. It reuses the family's plumbing --
the shared Q-id concept service, the Vovere body generator, and the OpenAI Batch
queue -- but skips ranking and title->Q-id resolution entirely, since the Q-ids
are given.

Modes:
    --batch   Queue one OpenAI Batch job for every Q-id's body (~50% cheaper).
              Concepts are created later via ``agents/common/batch.py complete``.
    --create  Create each concept inline now (one LLM call per Q-id), or with
              --no-body save sources without generating a body.
    (default) Resolve + report each Q-id's seed without writing anything.

Concept creation is idempotent: a Q-id already linked to a concept (or whose
seeded title already exists) is skipped.

Usage:
    PYTHONPATH=src python src/agents/vovere/voveraite.py Q8768 Q8743 Q8704
    PYTHONPATH=src python src/agents/vovere/voveraite.py Q8768 Q8743 --create --model gpt-5.4-mini
    PYTHONPATH=src python src/agents/vovere/voveraite.py Q8768 Q8743 --batch --model gpt-5.4-mini
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

# Add src directory to path (this file lives at src/agents/vovere/)
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_llm_args,
    get_data_source_config,
)
from clients.batch_queue import BatchRequestMetadata, get_batch_manager
from storage.backend import create_session as create_backend_session
from storage.backend.config import DataSourceConfig
from storage.concept_service import create_concept_from_qid
from storage.crud.concept import cache_wikidata_title
from storage.wikidata import fetch_wikidata_concept_seed, normalize_qid

# Agent name recorded on queued batch requests; the completion handler in
# agents/common/batch.py dispatches on this name.
BATCH_AGENT_NAME = "voveraite"
BATCH_OPERATION = "generate_concept"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class VoveraiteAgent:
    """Create concepts from an explicit list of Wikidata Q-ids."""

    def __init__(self, config: DataSourceConfig) -> None:
        """Initialize the agent.

        Args:
            config: DataSourceConfig with backend, model, and debug settings.
        """
        self.config = config
        self.debug = config.debug
        if self.debug:
            logger.setLevel(logging.DEBUG)

    def _make_body_generator(self) -> Any:
        """Return a (title, summary, sources) -> body callable backed by Vovere.

        Imported lazily so resolve-only runs do not require the LLM client.
        """
        from agents.vovere.vovere import VovereAgent

        agent = VovereAgent(self.config)

        def generate(title: str, summary: str, sources: List[Dict[str, Any]]) -> str:
            return agent.generate_body(title, summary, sources)

        return generate

    def create(self, qids: List[str], *, generate_body: bool) -> List[Dict[str, object]]:
        """Create a concept for each Q-id via the shared concept service.

        Args:
            qids: Wikidata Q-ids (any case; normalized by the service).
            generate_body: If True, generate a Markdown body via Vovere;
                otherwise concepts are saved with sources but no body.

        Returns:
            One result dict per Q-id with ``qid``/``title``/``status``/``detail``.
        """
        body_generator = self._make_body_generator() if generate_body else None

        results: List[Dict[str, object]] = []
        session = create_backend_session(self.config)
        try:
            for raw_qid in qids:
                result = create_concept_from_qid(
                    session,
                    raw_qid,
                    body_generator=body_generator,
                    source_model=self.config.model if body_generator else None,
                    include_regional_wikis=True,
                )
                results.append(
                    {
                        "qid": result.qid,
                        "title": result.title,
                        "status": result.status,
                        "detail": result.detail,
                    }
                )
                logger.info(
                    "%s [%s] %s%s",
                    result.status.upper(),
                    result.qid,
                    result.title,
                    f" - {result.detail}" if result.detail else "",
                )
            return results
        finally:
            session.close()

    def submit_batch(self, qids: List[str]) -> Dict[str, object]:
        """Queue concept-body generation for each Q-id as one Batch API job.

        Fetches every Wikidata seed up front and builds one
        ``/v1/chat/completions`` request per resolvable Q-id, stashing the seed
        alongside each request so the completion step (``agents/common/batch.py
        complete``) can create the concept from the same inputs without
        re-fetching. All requests are submitted as a single batch.

        Args:
            qids: Wikidata Q-ids (any case; normalized).

        Returns:
            ``{"batch_id", "queued", "skipped"}`` describing what was submitted.
        """
        from agents.vovere.vovere import VovereAgent

        vovere = VovereAgent(self.config)
        if not vovere.model:
            raise ValueError("A model is required to submit a batch (set --model).")

        batch_manager = get_batch_manager(debug=self.debug)
        session = create_backend_session(self.config)
        queued = 0
        skipped = 0
        try:
            for raw_qid in qids:
                qid = normalize_qid(raw_qid)
                if qid is None:
                    logger.info("SKIP (invalid Q-id) %s", raw_qid)
                    skipped += 1
                    continue

                seed = fetch_wikidata_concept_seed(qid, include_regional_wikis=True)
                if seed is None:
                    logger.info("SKIP (no seed) [%s]", qid)
                    skipped += 1
                    continue

                # Cache the qid<->title mapping regardless of batch success.
                cache_wikidata_title(session, qid, seed.title)

                request_body = vovere.build_request_body(
                    seed.title, seed.summary, list(seed.sources)
                )

                custom_id = f"{BATCH_AGENT_NAME}_{seed.qid}"
                metadata = BatchRequestMetadata(
                    custom_id=custom_id,
                    agent_name=BATCH_AGENT_NAME,
                    operation_type=BATCH_OPERATION,
                    entity_type="concept",
                )
                try:
                    record = batch_manager.queue_request(
                        custom_id=custom_id,
                        request_body=request_body,
                        metadata=metadata,
                        endpoint="/v1/chat/completions",
                    )
                except ValueError as exc:
                    logger.info("SKIP (already queued) [%s] %s: %s", qid, seed.title, exc)
                    skipped += 1
                    continue

                # Stash the full seed + model so the completion step can build
                # the concept from the same inputs without a second fetch.
                record.additional_metadata = json.dumps(
                    {
                        **metadata.to_dict(),
                        "qid": seed.qid,
                        "seed": {
                            "qid": seed.qid,
                            "title": seed.title,
                            "summary": seed.summary,
                            "sources": list(seed.sources),
                        },
                        "source_model": vovere.model,
                    },
                    ensure_ascii=False,
                )
                batch_manager.db.commit()
                logger.info("QUEUED [%s] %s", qid, seed.title)
                queued += 1

            if queued == 0:
                logger.info("Nothing to submit (queued 0 requests).")
                return {"batch_id": None, "queued": 0, "skipped": skipped}

            pending = batch_manager.get_pending_requests(
                agent_name=BATCH_AGENT_NAME, operation_type=BATCH_OPERATION
            )
            batch_id, _file_id = batch_manager.submit_batch(
                pending,
                batch_metadata={"agent": BATCH_AGENT_NAME, "operation": BATCH_OPERATION},
            )
            logger.info("Submitted batch %s with %d requests", batch_id, len(pending))
            logger.info(
                "Complete it later with: "
                "PYTHONPATH=src python src/agents/common/batch.py complete "
                "--batch-id %s --agent %s",
                batch_id,
                BATCH_AGENT_NAME,
            )
            return {"batch_id": batch_id, "queued": queued, "skipped": skipped}
        finally:
            session.close()

    def resolve(self, qids: List[str]) -> List[Dict[str, object]]:
        """Fetch and report each Q-id's Wikidata seed without writing anything.

        Args:
            qids: Wikidata Q-ids (any case; normalized).

        Returns:
            One result dict per Q-id with ``qid``/``title``/``resolved`` fields.
        """
        results: List[Dict[str, object]] = []
        for raw_qid in qids:
            qid = normalize_qid(raw_qid)
            if qid is None:
                logger.info("INVALID %s", raw_qid)
                results.append({"qid": raw_qid, "title": "", "resolved": False})
                continue
            seed = fetch_wikidata_concept_seed(qid)
            if seed is None:
                logger.info("UNRESOLVED [%s]", qid)
                results.append({"qid": qid, "title": "", "resolved": False})
                continue
            logger.info("RESOLVED [%s] %s", qid, seed.title)
            results.append({"qid": qid, "title": seed.title, "resolved": True})
        return results


def _print_resolution(resolved: List[Dict[str, object]]) -> None:
    """Print a Q-id -> title table for resolved (and unresolved) Q-ids."""
    print(f"\n{'Q-id':<12} {'Status':<12} Title")
    print("-" * 60)
    for item in resolved:
        status = "resolved" if item["resolved"] else "UNRESOLVED"
        print(f"{str(item['qid']):<12} {status:<12} {item['title']}")
    n_ok = sum(1 for item in resolved if item["resolved"])
    print(f"\n{n_ok}/{len(resolved)} Q-ids resolved.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Voveraite - create concepts from explicit Wikidata Q-ids"
    )
    parser.add_argument(
        "qids",
        nargs="+",
        metavar="QID",
        help="Wikidata Q-ids to create concepts for (e.g. Q8768 Q8743).",
    )
    parser.add_argument(
        "--create",
        action="store_true",
        help="Create a concept for each Q-id now (one LLM call per Q-id).",
    )
    parser.add_argument(
        "--no-body",
        action="store_true",
        help="With --create, save concepts without generating an LLM body.",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help=(
            "Queue one OpenAI Batch job to generate every concept body "
            "(~50%% cheaper). Concepts are created later via "
            "'agents/common/batch.py complete'. Mutually exclusive with --create."
        ),
    )
    add_common_args(parser)
    add_backend_args(parser)
    add_llm_args(parser)
    args = parser.parse_args()

    if args.batch and args.create:
        parser.error("--batch and --create are mutually exclusive.")
    if args.no_body and not args.create:
        parser.error("--no-body only applies with --create.")

    config = get_data_source_config(args)
    agent = VoveraiteAgent(config)

    # Always resolve every Q-id first and show what was found. For read-only
    # runs that report *is* the output; for write runs it is the confirmation
    # preview (seed lookups are cached, so re-fetching during create/batch is
    # free).
    resolved = agent.resolve(args.qids)
    _print_resolution(resolved)

    if not (args.batch or args.create):
        return 0

    resolvable = [str(item["qid"]) for item in resolved if item["resolved"]]
    if not resolvable:
        logger.info("No Q-ids resolved; nothing to do.")
        return 0

    action = "Submit one batch to generate" if args.batch else "Create"
    body_note = " (no bodies)" if args.create and args.no_body else " (with generated bodies)"
    if not args.yes:
        confirm = input(f"\n{action} {len(resolvable)} concept(s){body_note}? [y/N]: ")
        if confirm.strip().lower() != "y":
            logger.info("Aborted.")
            return 0

    if args.batch:
        summary = agent.submit_batch(resolvable)
        logger.info(
            "Batch %s: queued %s, skipped %s",
            summary["batch_id"],
            summary["queued"],
            summary["skipped"],
        )
        return 0

    agent.create(resolvable, generate_body=not args.no_body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
