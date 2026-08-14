#!/usr/bin/env python3
"""
Voverukas - Concept crawl ranker ("powering the crawl").

"Voverukas" means "little squirrel" in Lithuanian: it scampers across the
concept link-graph and decides which acorns to bury next. It complements
**Vovere** (the concept *generator*): Voverukas only ranks and reports, it
never creates or modifies concepts.

The agent runs the Voverukas ranking algorithm (a typed port of slmt's
"Powerrank") over every existing concept body, then surfaces the highest-ranked
"red links" -- ``[[wiki links]]`` whose target has no concept yet. That ranked
list is the worklist for which missing topics to create next: a red link cited
by many high-importance concepts ranks above one cited by a single obscure
concept.

Ranking itself is READ-ONLY (computed on the fly each run, nothing persisted).
The optional ``--resolve-qids``/``--create``/``--batch`` steps do write (cached
Q-ids and, for create/batch, new concepts).

``--batch`` submits one OpenAI Batch job for all ranked topics at ~50% cost: it
fetches every concept's inputs (Wikidata seed + source text) up front, queues a
single batch, and the resulting bodies are turned into concepts later via
``agents/common/batch.py complete``.

Usage:
    PYTHONPATH=src python src/agents/vovere/voverukas.py --limit 30
    PYTHONPATH=src python src/agents/vovere/voverukas.py --limit 50 --iterations 6 --debug
    PYTHONPATH=src python src/agents/vovere/voverukas.py --limit 10 --batch --model gpt-5.4-mini
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
import json

from clients.batch_queue import BatchRequestMetadata, get_batch_manager
from concepts.generate.entry import ConceptEntryGenerator
from concepts.pipeline import create_concept_from_qid
from storage.backend import create_session as create_backend_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.crud.concept import cache_wikidata_title
from storage.models.concept import (
    Concept,
    ConceptWikidataIndex,
    SubConcept,
    concept_slug_to_title,
    normalize_concept_slug,
    wiki_target_qid,
)
from storage.wikidata import (
    fetch_wikidata_concept_seed,
    resolve_titles_to_qids,
)
from wordfreq.voverukas import (
    DEFAULT_DAMPING,
    DEFAULT_ITERATIONS,
    build_link_graph,
    compute_ranks,
)

# Agent name recorded on queued batch requests; the completion handler in
# agents/common/batch.py dispatches on this name.
BATCH_AGENT_NAME = "voverukas"
BATCH_OPERATION = "generate_concept"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class VoverukasAgent:
    """Read-only agent that ranks wanted (red-link) concept topics."""

    def __init__(self, config: DataSourceConfig) -> None:
        """Initialize the agent.

        Args:
            config: DataSourceConfig with backend and debug settings.
        """
        self.config = config
        self.debug = config.debug
        if self.debug:
            logger.setLevel(logging.DEBUG)

    def rank_wanted(
        self,
        *,
        limit: int = 50,
        iterations: int = DEFAULT_ITERATIONS,
        damping: float = DEFAULT_DAMPING,
    ) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
        """Rank red-link targets by importance over the concept link-graph.

        Sub-encyclopedia topics never rank as wanted: slugs present in
        ``sub_concepts`` count as existing, and red links whose cached Q-id is
        rejected or filed as a sub-concept are diverted to the suppressed list.
        Q-id-form targets (``[[Q...]]``) name a specific entity rather than a
        creatable slug and are skipped outright.

        Args:
            limit: Maximum number of wanted slugs to return.
            iterations: Number of ranking dispersion passes.
            damping: Fraction of a node's rank dispersed across its out-links.

        Returns:
            A ``(wanted, suppressed)`` pair. ``wanted`` is a list of
            ``{"slug", "title", "score", "inbound"}`` dicts for the top wanted
            (missing) topics, ordered by descending score. ``suppressed``
            holds the same shape plus a ``"reason"`` field for ranked topics
            that were filtered out (rejected / filed as sub-concept /
            strictly excluded).
        """
        session = create_backend_session(self.config)
        try:
            bodies_by_slug: Dict[str, str] = {}
            existing_slugs = set()
            for slug, body in session.query(Concept.slug, Concept.body).all():
                existing_slugs.add(slug)
                bodies_by_slug[slug] = body or ""

            sub_slugs = {row[0] for row in session.query(SubConcept.slug).all()}

            # Red links whose cached Q-id has been triaged away from the main
            # encyclopedia, matched through the cached remote title.
            suppressed_reasons: Dict[str, str] = {}
            for index_row in (
                session.query(ConceptWikidataIndex)
                .filter(ConceptWikidataIndex.title.isnot(None))
                .filter(
                    ConceptWikidataIndex.rejected.is_(True)
                    | ConceptWikidataIndex.sub_concept_id.isnot(None)
                )
                .all()
            ):
                if index_row.rejected:
                    triage_reason = "rejected"
                elif index_row.sub_concept is not None and index_row.sub_concept.is_excluded:
                    triage_reason = "excluded"
                else:
                    triage_reason = "sub-concept"
                suppressed_reasons[normalize_concept_slug(index_row.title or "")] = triage_reason

            logger.info("Loaded %d concepts, %d sub-concepts", len(existing_slugs), len(sub_slugs))

            link_graph, inbound_counts = build_link_graph(bodies_by_slug)
            ranks = compute_ranks(
                link_graph,
                existing_slugs,
                iterations=iterations,
                damping=damping,
            )

            # Keep only targets that are linked-to but have no page yet.
            wanted: List[Dict[str, object]] = []
            suppressed: List[Dict[str, object]] = []
            for slug, score in ranks.top(n=len(ranks.scores)):
                if slug in existing_slugs or slug in sub_slugs:
                    continue
                if wiki_target_qid(slug):
                    continue
                item: Dict[str, object] = {
                    "slug": slug,
                    "title": concept_slug_to_title(slug),
                    "score": round(score, 4),
                    "inbound": inbound_counts.get(slug, 0),
                }
                suppression = suppressed_reasons.get(slug)
                if suppression is not None:
                    item["reason"] = suppression
                    suppressed.append(item)
                    continue
                wanted.append(item)
                if len(wanted) >= limit:
                    break
            return wanted, suppressed
        finally:
            session.close()

    def _make_body_generator(self) -> Any:
        """Return a (title, summary, sources) -> body callable backed by Vovere.

        Imported lazily so ranking-only runs do not require the LLM client.
        """
        generator = ConceptEntryGenerator(self.config)

        def generate(title: str, summary: str, sources: List[Dict[str, Any]]) -> str:
            return generator.generate_body(title, summary, sources)

        return generate

    def resolve_and_create(
        self,
        wanted: List[Dict[str, object]],
        *,
        create: bool,
        generate_body: bool,
    ) -> List[Dict[str, object]]:
        """Resolve ranked red-link titles to Q-ids (cached) and optionally create.

        Resolution uses a single batched Wikipedia API request for all titles.
        Every resolved Q-id is cached in ``concept_wikidata_index`` (title only,
        no concept yet). When ``create`` is set, each resolved Q-id is run
        through the shared concept-creation service.

        Args:
            wanted: Ranked wanted items from :meth:`rank_wanted`.
            create: If True, create a concept for each resolved Q-id.
            generate_body: If True (and creating), generate a Markdown body via
                Vovere; otherwise concepts are saved with sources but no body.

        Returns:
            ``wanted`` augmented in place with ``qid`` and (when creating)
            ``status``/``detail`` fields.
        """
        titles = [str(item["title"]) for item in wanted]
        qid_map = resolve_titles_to_qids(titles)

        body_generator = None
        if create and generate_body:
            body_generator = self._make_body_generator()

        session = create_backend_session(self.config)
        try:
            for item in wanted:
                qid = qid_map.get(str(item["title"]))
                item["qid"] = qid or ""
                if not qid:
                    if create:
                        item["status"] = "unresolved"
                    continue
                # Cache the qid<->title mapping regardless of creation.
                cache_wikidata_title(session, qid, str(item["title"]))
                if not create:
                    continue
                result = create_concept_from_qid(
                    session,
                    qid,
                    body_generator=body_generator,
                    source_model=self.config.model if body_generator else None,
                    include_regional_wikis=True,
                )
                item["status"] = result.status
                item["detail"] = result.detail
                logger.info(
                    "%s [%s] %s%s",
                    result.status.upper(),
                    qid,
                    item["title"],
                    f" - {result.detail}" if result.detail else "",
                )
            return wanted
        finally:
            session.close()

    def resolve_qids(self, wanted: List[Dict[str, object]]) -> Dict[str, Optional[str]]:
        """Batch-resolve ranked titles to Q-ids and annotate each item in place.

        Args:
            wanted: Ranked wanted items from :meth:`rank_wanted`.

        Returns:
            The title -> Q-id (or None) map used to annotate ``wanted``.
        """
        titles = [str(item["title"]) for item in wanted]
        qid_map = resolve_titles_to_qids(titles)
        for item in wanted:
            item["qid"] = qid_map.get(str(item["title"])) or ""
        return qid_map

    def submit_batch(
        self,
        wanted: List[Dict[str, object]],
        qid_map: Optional[Dict[str, Optional[str]]] = None,
    ) -> Dict[str, object]:
        """Queue concept-body generation for ranked topics as one Batch API job.

        Does the expensive work once, up front: resolves all titles to Q-ids,
        fetches every Wikidata seed and its source text, and builds one
        ``/v1/chat/completions`` request per resolvable topic. Each seed is
        stored alongside its request so the completion step (``agents/common/
        batch.py complete``) can create the concept from the *same* inputs
        without re-fetching. All requests are then submitted as a single batch.

        Args:
            wanted: Ranked wanted items from :meth:`rank_wanted`.
            qid_map: Optional pre-resolved title -> Q-id map (from
                :meth:`resolve_qids`); resolved here if omitted.

        Returns:
            ``{"batch_id", "queued", "skipped"}`` describing what was submitted.
        """
        generator = ConceptEntryGenerator(self.config)
        if not generator.model:
            raise ValueError("A model is required to submit a batch (set --model).")

        if qid_map is None:
            qid_map = self.resolve_qids(wanted)

        batch_manager = get_batch_manager(debug=self.debug)
        session = create_backend_session(self.config)
        queued = 0
        skipped = 0
        try:
            for item in wanted:
                title = str(item["title"])
                qid = qid_map.get(title)
                if not qid:
                    logger.info("SKIP (unresolved) %s", title)
                    skipped += 1
                    continue

                # Cache the qid<->title mapping regardless of batch success.
                cache_wikidata_title(session, qid, title)

                seed = fetch_wikidata_concept_seed(qid, include_regional_wikis=True)
                if seed is None:
                    logger.info("SKIP (no seed) [%s] %s", qid, title)
                    skipped += 1
                    continue

                request_body = generator.build_request_body(
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
                    logger.info("SKIP (already queued) [%s] %s: %s", qid, title, exc)
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
                        "source_model": generator.model,
                    },
                    ensure_ascii=False,
                )
                batch_manager.db.commit()
                logger.info("QUEUED [%s] %s", qid, title)
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
            backend_flag = ""
            if self.config.backend_type == BackendType.POSTGRES:
                backend_flag = " --postgres"
            elif self.config.backend_type == BackendType.JSONL:
                backend_flag = " --backend jsonl"
            logger.info(
                "Complete it later with: "
                "PYTHONPATH=src python src/agents/common/batch.py complete "
                "--batch-id %s --agent %s%s",
                batch_id,
                BATCH_AGENT_NAME,
                backend_flag,
            )
            return {"batch_id": batch_id, "queued": queued, "skipped": skipped}
        finally:
            session.close()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Voverukas - rank wanted (red-link) concept topics (read-only)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of ranked wanted topics to show (default: 50)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=DEFAULT_ITERATIONS,
        help=f"Number of ranking dispersion passes (default: {DEFAULT_ITERATIONS})",
    )
    parser.add_argument(
        "--damping",
        type=float,
        default=DEFAULT_DAMPING,
        help=f"Rank dispersed across out-links per pass (default: {DEFAULT_DAMPING})",
    )
    parser.add_argument(
        "--show-filtered",
        action="store_true",
        help=(
            "Also print ranked topics suppressed from the wanted list because "
            "their Q-id is rejected or filed as a sub-concept."
        ),
    )
    parser.add_argument(
        "--resolve-qids",
        action="store_true",
        help="Batch-resolve ranked titles to Wikidata Q-ids and cache them (read-only).",
    )
    parser.add_argument(
        "--create",
        action="store_true",
        help="Create a concept for each resolved Q-id (implies --resolve-qids).",
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
            "Fetch all inputs now and queue one OpenAI Batch job to generate every "
            "concept body (~50%% cheaper). Concepts are created later via "
            "'agents/common/batch.py complete'. Mutually exclusive with --create."
        ),
    )
    add_common_args(parser)
    add_backend_args(parser)
    add_llm_args(parser)

    args = parser.parse_args()

    if args.batch and args.create:
        parser.error("--batch and --create are mutually exclusive (batch creates later).")

    config = get_data_source_config(args)

    agent = VoverukasAgent(config)
    wanted, suppressed = agent.rank_wanted(
        limit=args.limit,
        iterations=args.iterations,
        damping=args.damping,
    )

    if suppressed and not args.show_filtered:
        logger.info(
            "%d ranked topics suppressed (rejected / sub-concept); "
            "use --show-filtered to list them.",
            len(suppressed),
        )

    if not wanted:
        logger.info("No wanted (red-link) topics found.")
        if args.show_filtered and suppressed:
            _print_suppressed_table(suppressed)
        return 0

    if args.batch:
        # Resolve and show the exact topics + Q-ids before asking to submit.
        qid_map = agent.resolve_qids(wanted)
        _print_wanted_table(wanted)
        resolvable = sum(1 for item in wanted if item.get("qid"))
        if not args.yes:
            confirm = input(
                f"\nFetch inputs for {resolvable} resolved topics and submit one batch? [y/N]: "
            )
            if confirm.strip().lower() != "y":
                logger.info("Aborted.")
                return 0
        result = agent.submit_batch(wanted, qid_map=qid_map)
        if not result["batch_id"]:
            return 0
        print(
            f"\nSubmitted batch {result['batch_id']}: "
            f"{result['queued']} queued, {result['skipped']} skipped."
        )
        return 0

    if args.resolve_qids or args.create:
        if args.create and not args.yes:
            generate_note = "without bodies" if args.no_body else "with generated bodies"
            confirm = input(f"Create up to {len(wanted)} concepts {generate_note}? [y/N]: ")
            if confirm.strip().lower() != "y":
                logger.info("Aborted.")
                return 0
        wanted = agent.resolve_and_create(
            wanted,
            create=args.create,
            generate_body=not args.no_body,
        )

    _print_wanted_table(wanted)
    if args.show_filtered and suppressed:
        _print_suppressed_table(suppressed)
    return 0


def _print_suppressed_table(suppressed: List[Dict[str, object]]) -> None:
    """Print ranked topics filtered out of the wanted list, with the reason."""
    print(f"\nSuppressed topics ({len(suppressed)}):\n")
    print(f"{'#':>4}  {'score':>10}  {'inbound':>7}  {'reason':>12}  topic")
    for index, item in enumerate(suppressed, 1):
        print(
            f"{index:>4}  {item['score']:>10}  {item['inbound']:>7}"
            f"  {str(item['reason']):>12}  {item['title']}"
        )


def _print_wanted_table(wanted: List[Dict[str, object]]) -> None:
    """Print the ranked wanted-topics table (score, inbound, Q-id, status)."""
    show_qid = "qid" in wanted[0]
    show_status = "status" in wanted[0]
    header = f"{'#':>4}  {'score':>10}  {'inbound':>7}"
    if show_qid:
        header += f"  {'Q-id':>9}"
    if show_status:
        header += f"  {'status':>10}"
    header += "  topic"
    print(f"\nTop {len(wanted)} wanted concept topics (by Voverukas rank):\n")
    print(header)
    for index, item in enumerate(wanted, 1):
        row = f"{index:>4}  {item['score']:>10}  {item['inbound']:>7}"
        if show_qid:
            row += f"  {str(item.get('qid') or '—'):>9}"
        if show_status:
            row += f"  {str(item.get('status') or '—'):>10}"
        row += f"  {item['title']}"
        print(row)


if __name__ == "__main__":
    sys.exit(main())
