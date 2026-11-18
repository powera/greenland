"""Durable, GUID-specific OpenAI batch curriculum review (see docs/curriculum_review.md)."""

import argparse
import fcntl
import hashlib
import json
import random
from collections import Counter
import sqlite3
import subprocess
import sys
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Sequence

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session

import constants
from clients.openai.batch_client import OpenAIBatchClient, batch_response_text
from clients.batch_queue import BatchQueueManager, create_batch_database_session
from clients.openai.client import OpenAIClient, build_responses_request
from quality.level_placement import (
    LevelPlacer,
    MenuLevel,
    PLACEMENT_JSON_SCHEMA,
    build_context,
    build_prompt,
    parse_placement,
)
from reports.curriculum_bands import PlannedMove, apply_moves, band_of
from reports.level_candidates import PlacementQuery, query_for_lemma
from storage.backend import BackendType, DataSourceConfig, create_session
from storage.backup import create_backup
from storage.models.schema import Lemma
from storage.models.operation_log import OperationLog
from storage.crud.curriculum_level import (
    get_curriculum_level,
    set_curriculum_level,
    list_curriculum_levels,
    normalize_cefr,
)
from storage.crud.operation_log import log_entity_operation
from wordfreq.data.cohorts import COHORT_LEVELS
from quality.curriculum_volumes import VolumeAllocator, balance_volumes, volume_context


def release_rows(commit: str) -> dict[str, dict[str, Any]]:
    """Read committed base records, independent of untracked review inventories."""
    paths = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", commit, "data/release/lemmas"], text=True
    ).splitlines()
    records: dict[str, dict[str, Any]] = {}
    for path in paths:
        if path.endswith("/base.jsonl"):
            content = subprocess.check_output(["git", "show", f"{commit}:{path}"], text=True)
            for line in content.splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                records[row["guid"]] = row
    return records


def fingerprint(lemma: Lemma, query: PlacementQuery) -> str:
    """Detect sense, placement and CEFR evidence edits between preparation and approval."""
    payload = [
        lemma.guid,
        lemma.lemma_text,
        lemma.definition_text,
        lemma.disambiguation,
        lemma.pos_type,
        lemma.pos_subtype,
        lemma.difficulty_level,
        asdict(query),
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def destinations(
    menu: Sequence[MenuLevel],
    query: PlacementQuery,
    *,
    cefr_pass: bool = False,
    b2_exception: bool = False,
) -> list[MenuLevel]:
    """Topic-only by default; advanced or missing CEFR evidence never opens core."""
    tiers = [tier.upper().split(".")[0] for source, tier in query.tiers if source == "cefr"]
    order = {"A1": 0, "A2": 1, "B1": 2, "B2": 3, "C1": 4, "C2": 5}
    tier = max(tiers, key=lambda item: order.get(item, 6), default="unranked")
    core = cefr_pass and (tier in ("A1", "A2", "B1") or (tier == "B2" and b2_exception))
    return [
        item
        for item in menu
        if item.level not in COHORT_LEVELS
        and (band_of(item.level) == "topic" or (core and 100 <= item.level <= 499))
    ] + [MenuLevel(1399, "Staging: placement undecided")]


class ReviewStore:
    """Separate local SQLite journal; never changes curriculum when collecting answers."""

    def __init__(self, path: Path) -> None:
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS journal (key TEXT PRIMARY KEY, payload TEXT NOT NULL)"
        )

        if self.get("run_id") is None:
            self.put("run_id", uuid.uuid4().hex)

    def get(self, key: str) -> Any:
        row = self.db.execute("SELECT payload FROM journal WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, payload: Any) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO journal VALUES (?, ?)",
                (key, json.dumps(payload, sort_keys=True)),
            )

    def rows(self) -> list[dict[str, Any]]:
        return [
            json.loads(row[0])
            for row in self.db.execute(
                "SELECT payload FROM journal WHERE key LIKE 'sense:%' ORDER BY key"
            )
        ]


def prepare(
    session: Session,
    store: ReviewStore,
    old: str,
    new: str,
    phase: str,
    model: str,
    *,
    catalogue: Sequence[dict[str, Any]] = (),
    cefr_pass: bool = False,
    b2_exceptions: Sequence[str] = (),
    inventory: bool = False,
    limit: int | None = None,
    seed: int = 20261117,
) -> int:
    """Freeze a complete phase before submitting anything; resume only identical runs."""
    settings = dict(
        old=old,
        new=new,
        phase=phase,
        model=model,
        catalogue=list(catalogue),
        cefr_pass=cefr_pass,
        b2_exceptions=list(b2_exceptions),
    )
    if inventory:
        if phase != "staging" or (limit is not None and limit < 1):
            raise ValueError("Inventory sampling requires staging and a positive limit")
        settings.update(inventory=True, limit=limit, seed=seed)
    previous = store.get("settings")
    if previous is not None and previous != settings:
        raise ValueError("Use a separate review database for different settings")
    store.put("settings", settings)
    if inventory:
        selection = store.get("selection")
        if selection is None:
            population = [
                row[0]
                for row in session.query(Lemma.guid)
                .filter(
                    Lemma.difficulty_level == constants.STAGING_DIFFICULTY_LEVEL,
                    Lemma.guid.isnot(None),
                )
                .order_by(Lemma.guid)
            ]
            if limit is not None and limit > len(population):
                raise ValueError("Requested sample exceeds staging inventory")
            sampled_guids = sorted(random.Random(seed).sample(population, limit or len(population)))
            selection = dict(
                guids=sampled_guids,
                population=len(population),
                seed=seed,
                source_level=constants.STAGING_DIFFICULTY_LEVEL,
            )
            store.put("selection", selection)
        guids = selection["guids"]
    else:
        before, after = release_rows(old), release_rows(new)
        guids = sorted(after.keys() - before.keys())
    placer = LevelPlacer(session, {})
    occupied = {row[0] for row in session.query(Lemma.difficulty_level).distinct()}
    occupied.update(placer.titles)
    # Editorial notes include the approved boundaries and illustrative examples.
    notes = {row.level: row.notes for row in list_curriculum_levels(session) if row.notes}
    placer.menu = [
        MenuLevel(
            item.level,
            item.name + (": " + notes[item.level] if item.level in notes else ""),
            item.cefr,
        )
        for item in placer.menu
    ]
    for entry in catalogue:
        number = entry["level"]
        existing = get_curriculum_level(session, number) if type(number) is int else None
        if (
            type(number) is not int
            or band_of(number) != "topic"
            or (
                number in occupied
                and not (
                    existing
                    and existing.name == entry["name"]
                    and existing.notes == catalogue_notes(entry)
                )
            )
        ):
            raise ValueError(f"Proposed topic number is occupied or invalid: {number}")
        occupied.add(number)
        placer.menu = [item for item in placer.menu if item.level != number]
        placer.menu.append(
            MenuLevel(
                number,
                entry["name"] + ": " + catalogue_notes(entry),
                existing.cefr if existing else entry.get("cefr"),
            )
        )
    # Untitled occupied topics remain destinations, with nearby family title and real samples.
    for number in sorted(value for value in occupied if isinstance(value, int)):
        if (
            band_of(number) == "topic"
            and number not in placer.titles
            and not any(entry.level == number for entry in placer.menu)
        ):
            parents = [value for value in placer.titles if 1000 <= value < number]
            title = placer.titles[max(parents)] if parents else "Untitled topic"
            placer.menu.append(MenuLevel(number, f"{title} — existing extension {number}"))
    count = 0
    for guid in guids:
        lemma = session.query(Lemma).filter(Lemma.guid == guid).one_or_none()
        if lemma is None:
            raise ValueError(f"Release sense missing locally: {guid}")
        # Cohorts and established core placements are protected even if inventory differs.
        level = lemma.difficulty_level
        if level in COHORT_LEVELS or (level is not None and 1 <= level <= 499):
            continue
        selected = (
            (phase == "topics" and band_of(level) == "topic")
            or (phase == "staging" and level == 1399)
            or (phase == "unlevelled" and level in (None, -1))
        )
        if not selected:
            continue
        count += 1
        if store.get("sense:" + guid) is not None:
            continue
        query = query_for_lemma(session, lemma, placer.index)
        menu = destinations(
            placer.menu, query, cefr_pass=cefr_pass, b2_exception=guid in b2_exceptions
        )
        senses = placer.other_senses(query)
        weights = placer.word_weights(query)
        owner = placer.lean_owner(weights, senses)
        shortlist = placer.shortlist(query, None if owner else weights)
        shortlist = [entry for entry in shortlist if entry.level in {item.level for item in menu}]
        prompt = build_prompt(
            query,
            shortlist,
            menu,
            weights,
            "bulk review never offers levels below 100",
            senses,
            owner,
        )
        allowed = [item.level for item in menu]
        context = build_context([item for item in menu if item.level != 1399])
        context += (
            "\nConservative general-unit policy: spelling-level CEFR is only a permission "
            "to consider levels 100–499, never a reason to prefer them. Judge the exact "
            "definition. A familiar headword can have a formal, technical, figurative or "
            "otherwise advanced secondary sense. Prefer its matching advanced landing "
            "point in that case. Only choose a general unit when this specific sense is "
            "clearly ordinary everyday vocabulary and a direct match for that unit; "
            "explain that sense-level evidence in the reasoning. In uncertainty, prefer "
            "an appropriate advanced unit or no suitable level; do not default downward.\n"
        )
        context += volume_context()
        context += (
            "\nFor adverbs, distinguish ordinary B1-or-easier units 105/324 from advanced units. "
            "Advanced general manner/usage belongs in 1340/1341; prefer 1342 for degree/focus, "
            "1343 for stance/evidence/certainty, 1344 for discourse linking, and 1345 for "
            "time/frequency/direction when the DEFINITION fits. Domain-specific senses may "
            "still belong to their domain. Never use an unoffered level.\n"
        )
        context += (
            "\n1399 | Staging: placement undecided. fit=none means no suitable level; "
            "do not force a fit. Judge this GUID and definition independently of siblings. "
            "80–120 entries is a planning guideline, never a quota. "
            "B2 core placement is an exceptional editorial decision, justify explicitly. "
            "Only the destinations in this context are allowed. "
            "The current level may be wrong. Preserve on-topic senses.\n"
        )
        # Enforce the menu in the provider schema as well as validating on receipt.
        schema = {
            **PLACEMENT_JSON_SCHEMA,
            "properties": {
                **PLACEMENT_JSON_SCHEMA["properties"],
                "level": {"type": "integer", "enum": [0, *allowed]},
                "alternatives": {"type": "array", "items": {"type": "integer", "enum": allowed}},
            },
        }
        request = dict(
            custom_id=guid,
            method="POST",
            url="/v1/responses",
            body=build_responses_request(
                model,
                "",
                messages=[
                    dict(role="system", content=context),
                    dict(role="user", content=f"GUID: {guid}; current level: {level}\n" + prompt),
                ],
                max_tokens=4096,
                json_schema=schema,
            ),
        )
        store.put(
            "sense:" + guid,
            dict(
                guid=guid,
                current_level=level,
                fingerprint=fingerprint(lemma, query),
                allowed=allowed,
                shortlist=[entry.level for entry in shortlist if entry.level in allowed],
                request=request,
            ),
        )
    store.put("prepared", True)
    return count


def checked_suggestion(payload: Any, record: dict[str, Any]) -> dict[str, Any]:
    """Validate a complete answer against this sense's frozen destination policy."""
    if not isinstance(payload, dict):
        raise ValueError("Expected an object")
    if (
        type(payload.get("level")) is not int
        or not isinstance(payload.get("alternatives"), list)
        or any(type(value) is not int for value in payload["alternatives"])
        or not isinstance(payload.get("reasoning"), str)
    ):
        raise ValueError("Invalid placement types")
    suggestion = parse_placement(payload, record["allowed"], record["shortlist"], None)
    if suggestion.problems or not suggestion.reasoning:
        raise ValueError(f"Invalid answer: {suggestion.problems}")
    return asdict(suggestion)


def collect(store: ReviewStore, responses: Sequence[dict[str, Any]]) -> None:
    """Persist successes and per-GUID failures; retry failed GUIDs in a fresh batch."""
    for result in responses:
        guid = result.get("custom_id")
        record = store.get("sense:" + str(guid))
        if record is None:
            raise ValueError(f"Unknown batch GUID: {guid}")
        if record.get("suggestion"):
            continue
        try:
            envelope = result.get("response") or {}
            if envelope.get("status_code") != 200 or result.get("error"):
                raise ValueError(f"Batch request failed: {result}")
            payload = json.loads(batch_response_text(envelope))
            record["suggestion"] = checked_suggestion(payload, record)
            record["raw_response"] = result
            record.pop("error", None)
        except (ValueError, TypeError, KeyError) as exc:
            record["error"] = str(exc)
        store.put("sense:" + str(guid), record)


def approved_moves(
    session: Session, store: ReviewStore, approvals: dict[str, int]
) -> list[PlannedMove]:
    """Validate every approved GUID before allowing any writes."""
    placer = LevelPlacer(session, {})
    moves: list[PlannedMove] = []
    for guid, target in approvals.items():
        record = store.get("sense:" + guid)
        if record is None or not record.get("suggestion"):
            raise ValueError(f"No reviewed suggestion: {guid}")
        suggestion = record["suggestion"]
        if type(target) is not int or target not in record["allowed"]:
            raise ValueError(f"Destination is not allowed: {guid}")
        if target not in [suggestion["level"], *suggestion["alternatives"], 1399]:
            raise ValueError(f"Destination was not suggested: {guid}")
        lemma = session.query(Lemma).filter(Lemma.guid == guid).populate_existing().one()
        query = query_for_lemma(session, lemma, placer.index)
        if lemma.difficulty_level in COHORT_LEVELS or (
            lemma.difficulty_level is not None and 1 <= lemma.difficulty_level <= 499
        ):
            raise ValueError(f"Protected placement: {guid}")
        if fingerprint(lemma, query) != record["fingerprint"]:
            raise ValueError(f"Stale sense or evidence: {guid}")
        if target != lemma.difficulty_level:
            moves.append(
                PlannedMove(lemma.id, guid, lemma.difficulty_level, target, suggestion["reasoning"])
            )
    return moves


def catalogue_notes(entry: dict[str, Any]) -> str:
    """Keep boundaries and examples editorial, rather than shipping them as app metadata."""
    examples = entry.get("examples", [])
    return str(entry["boundary"]) + (
        "\nExamples (illustrative, not mandatory members): " + ", ".join(examples)
        if examples
        else ""
    )


def install_topics(
    session: Session, config: DataSourceConfig, catalogue: Sequence[dict[str, Any]]
) -> int:
    """Install an approved catalogue atomically, backing up before the first write."""
    session.connection().exec_driver_sql("BEGIN IMMEDIATE")
    additions: list[dict[str, Any]] = []
    seen: set[int] = set()
    for entry in catalogue:
        number = entry["level"]
        if type(number) is not int or band_of(number) != "topic" or number in seen:
            raise ValueError(f"Invalid or duplicate topic number: {number}")
        seen.add(number)
        existing = get_curriculum_level(session, number)
        if existing:
            if existing.name != entry["name"] or existing.notes != catalogue_notes(entry):
                raise ValueError(f"Topic metadata conflict: {number}")
            continue
        if session.query(Lemma).filter(Lemma.difficulty_level == number).first():
            raise ValueError(f"Topic number occupied by existing lemmas: {number}")
        additions.append(entry)
    if additions:
        print("Minor backup:", create_backup(config, "add-review-topics", tier="minor"))
        for addition in additions:
            set_curriculum_level(
                session,
                addition["level"],
                addition["name"],
                cefr=addition.get("cefr"),
                notes=catalogue_notes(addition),
                source="curriculum-review/install-topics",
            )
    session.commit()
    return len(additions)


def update_levels(
    session: Session, config: DataSourceConfig, entries: Sequence[dict[str, Any]]
) -> int:
    """Apply explicit level names/metadata; staging requires reserved=True acknowledgement."""
    session.connection().exec_driver_sql("BEGIN IMMEDIATE")
    updates: list[tuple[dict[str, Any], Any]] = []
    seen: set[int] = set()
    for entry in entries:
        number = entry["level"]
        if (
            type(number) is not int
            or not constants.MIN_DIFFICULTY_LEVEL <= number <= constants.MAX_DIFFICULTY_LEVEL
            or number in seen
            or (number == constants.STAGING_DIFFICULTY_LEVEL and entry.get("reserved") is not True)
        ):
            raise ValueError(f"Invalid, reserved or duplicate curriculum level: {number}")
        seen.add(number)
        existing = get_curriculum_level(session, number)
        name = entry.get("name", existing.name if existing else "")
        cefr = normalize_cefr(entry.get("cefr", existing.cefr if existing else None))
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"A title is required: {number}")
        notes = entry.get("notes", existing.notes if existing else None)
        if existing and existing.name == name and existing.cefr == cefr and existing.notes == notes:
            continue
        if (
            "expected_cefr" in entry
            and (existing.cefr if existing else None) != entry["expected_cefr"]
        ):
            raise ValueError(f"CEFR metadata changed since preview: {number}")
        updates.append((dict(entry, name=name, cefr=cefr, notes=notes), existing))
    if updates:
        print("Minor backup:", create_backup(config, "name-topic-levels", tier="minor"), flush=True)
        for patch, original in updates:
            set_curriculum_level(
                session,
                patch["level"],
                patch["name"],
                cefr=patch["cefr"],
                prerequisites=original.get_prerequisites() if original else (),
                extra=original.get_extra() if original else None,
                notes=patch["notes"],
                source="curriculum-review/update-levels",
            )
    session.commit()
    return len(updates)


def run_one(
    session: Session, store: ReviewStore, guid: str, client: OpenAIClient
) -> dict[str, Any]:
    """Make one synchronous call, persist its suggestion, and leave assignment unchanged.

    Intent is durable before calling; reruns never automatically spend again.
    """
    record = store.get("sense:" + guid)
    if record is None:
        raise ValueError(f"No prepared request for {guid}")
    if store.get("active") or store.get("submitting"):
        raise ValueError("Collect or reconcile the active batch before a single run")
    if record.get("single_attempt") or record.get("suggestion"):
        raise ValueError(f"Already attempted or reviewed: {guid}")
    for entry in store.get("settings")["catalogue"]:
        registered = get_curriculum_level(session, entry["level"])
        if (
            registered is None
            or registered.name != entry["name"]
            or registered.notes != catalogue_notes(entry)
        ):
            raise ValueError(f"Install approved topic metadata before calling: {entry['level']}")
    lemma = session.query(Lemma).filter(Lemma.guid == guid).one()
    placer = LevelPlacer(session, {})
    if fingerprint(lemma, query_for_lemma(session, lemma, placer.index)) != record["fingerprint"]:
        raise ValueError(f"Stale sense or evidence: {guid}")
    body = record["request"]["body"]
    record["single_attempt"] = {"model": body["model"], "status": "started"}
    store.put("sense:" + guid, record)
    response = client.generate_chat(
        prompt="",
        model=body["model"],
        messages=body["input"],
        json_schema=body["text"]["format"]["schema"],
        max_tokens=body["max_output_tokens"],
    )
    # Save the returned data before validation or any primary-database writes.
    record["single_response"] = dict(
        structured_data=response.structured_data,
        usage=response.usage.to_dict() if response.usage else None,
        additional_thought=response.additional_thought,
    )
    record["single_attempt"]["status"] = "returned"
    store.put("sense:" + guid, record)
    collect(
        store,
        [
            dict(
                custom_id=guid,
                response=dict(
                    status_code=200,
                    body=dict(
                        status="completed",
                        output=[
                            dict(
                                type="message",
                                content=[
                                    dict(
                                        type="output_text",
                                        text=json.dumps(response.structured_data),
                                    )
                                ],
                            )
                        ],
                    ),
                ),
            )
        ],
    )
    saved: dict[str, Any] = store.get("sense:" + guid)
    log_entity_operation(
        session,
        source="curriculum-review/run-one/" + body["model"],
        operation_type="curriculum_placement_suggestion",
        entity_guid=guid,
        lemma_id=lemma.id,
        fact=dict(
            current_level=record["current_level"],
            suggestion=saved.get("suggestion"),
            error=saved.get("error"),
            response=record["single_response"],
        ),
    )
    session.commit()
    return saved


def apply_results(session: Session, config: DataSourceConfig, store: ReviewStore) -> dict[str, int]:
    """Apply authorized valid results; park no-fit senses and isolate stale records.

    Primary-database receipts make recovery idempotent across the two databases.
    """
    if session.new or session.dirty or session.deleted:
        raise ValueError("Cannot apply results with pending session writes")
    session.rollback()
    session.connection().exec_driver_sql("BEGIN IMMEDIATE")
    source = "curriculum-review/results/" + store.get("run_id")
    placer = LevelPlacer(session, {})
    counts = dict(moved=0, kept=0, blocked=0)
    ready: list[tuple[dict[str, Any], Lemma, int]] = []
    recovered: list[dict[str, Any]] = []
    allocator = VolumeAllocator(session)
    for record in store.rows():
        if not record.get("suggestion") or record.get("applied"):
            continue
        guid = record["guid"]
        lemma = session.query(Lemma).filter(Lemma.guid == guid).populate_existing().one_or_none()
        if lemma is None:
            record["apply_error"] = "Sense is missing"
            store.put("sense:" + guid, record)
            counts["blocked"] += 1
            continue
        query = query_for_lemma(session, lemma, placer.index)
        receipt = (
            session.query(OperationLog)
            .filter(
                OperationLog.source == source,
                OperationLog.entity_guid == guid,
                OperationLog.operation_type == "curriculum_placement_applied",
            )
            .order_by(OperationLog.id.desc())
            .first()
        )
        if receipt is not None:
            fact = json.loads(receipt.fact)
            if fact.get("original_fingerprint") == record["fingerprint"] and fact.get(
                "applied_fingerprint"
            ) == fingerprint(lemma, query):
                record["applied"] = dict(level=lemma.difficulty_level, receipt_id=receipt.id)
                recovered.append(record)
                continue
        suggestion = record["suggestion"]
        target = 1399 if suggestion["fit"] == "none" else suggestion["level"]
        protected = lemma.difficulty_level in COHORT_LEVELS or (
            lemma.difficulty_level is not None and 1 <= lemma.difficulty_level <= 499
        )
        if (
            protected
            or fingerprint(lemma, query) != record["fingerprint"]
            or type(target) is not int
            or target not in record["allowed"]
            or suggestion["fit"] not in ("good", "acceptable", "none")
            or (
                target != 1399
                and get_curriculum_level(session, target) is None
                and session.query(Lemma.id).filter(Lemma.difficulty_level == target).first() is None
            )
        ):
            record["apply_error"] = (
                "Stale sense/evidence, protected placement, or invalid destination"
            )
            store.put("sense:" + guid, record)
            counts["blocked"] += 1
            continue
        target = allocator.choose(target, record["allowed"], lemma.difficulty_level)
        ready.append((record, lemma, target))
    moves = [
        PlannedMove(
            lemma.id,
            record["guid"],
            lemma.difficulty_level,
            target,
            record["suggestion"]["reasoning"],
        )
        for record, lemma, target in ready
        if target != lemma.difficulty_level
    ]
    if moves:
        print(
            "Minor backup:", create_backup(config, "apply-topic-review", tier="minor"), flush=True
        )
    apply_moves(session, moves, source=source)
    for record, lemma, target in ready:
        log_entity_operation(
            session,
            source=source,
            operation_type="curriculum_placement_suggestion",
            entity_guid=record["guid"],
            lemma_id=lemma.id,
            fact=dict(
                current_level=record["current_level"],
                suggestion=record["suggestion"],
                model=record["request"]["body"]["model"],
            ),
        )
        receipt = log_entity_operation(
            session,
            source=source,
            operation_type="curriculum_placement_applied",
            entity_guid=record["guid"],
            lemma_id=lemma.id,
            fact=dict(
                original_fingerprint=record["fingerprint"],
                applied_fingerprint=fingerprint(
                    lemma, query_for_lemma(session, lemma, placer.index)
                ),
                level=target,
                suggestion=record["suggestion"],
            ),
        )
        record["applied"] = dict(level=target, receipt_id=receipt.id)
        record.pop("apply_error", None)
        counts["moved" if target != record["current_level"] else "kept"] += 1
    session.commit()
    for record in recovered + [item[0] for item in ready]:
        store.put("sense:" + record["guid"], record)
    return counts


def submit_all(
    session: Session,
    store: ReviewStore,
    manager: BatchQueueManager,
    batch_size: int,
    *,
    apply_on_collect: bool,
    dry_run: bool = False,
    limit: int | None = None,
) -> list[str]:
    """Submit through the shared queue; Barsukas owns tracking and completion."""
    from workqueue.handlers.level_placement import PLACEMENT_JOB
    from workqueue.llm_batch import start_batch_run

    if not store.get("prepared") or batch_size < 1:
        raise ValueError("A complete prepared inventory and positive batch size are required")
    if store.get("active") or store.get("submitting") or store.get("uploaded"):
        raise ValueError("Reconcile the legacy submission before submitting to the regular queue")
    if store.get("jobs"):
        raise ValueError(
            "Legacy batch journals are historical; use a fresh review for regular queue submission"
        )
    records = [record for record in store.rows() if not record.get("suggestion")]
    if limit is not None:
        if limit < 1:
            raise ValueError("--limit must be positive")
        records = records[:limit]
    settings = store.get("settings")
    if settings["phase"] == "staging" and not store.get("topics_complete") and not dry_run:
        raise ValueError("Complete the topic review before staging submission")
    for entry in settings["catalogue"]:
        existing = get_curriculum_level(session, entry["level"])
        if (
            existing is None
            or existing.name != entry["name"]
            or existing.notes != catalogue_notes(entry)
        ):
            raise ValueError(f"Install approved topic metadata before submission: {entry['level']}")
    submission_id = uuid.uuid4().hex
    states: list[dict[str, Any]] = []
    for position, record in enumerate(records):
        lemma = session.query(Lemma).filter(Lemma.guid == record["guid"]).one()
        states.append(
            dict(
                lemma_id=lemma.id,
                record=record,
                review_id=store.get("run_id"),
                backup_group=f"{submission_id}:{position // batch_size}",
                apply_results=apply_on_collect,
            )
        )
    report = start_batch_run(
        session,
        manager,
        PLACEMENT_JOB,
        states,
        settings["model"],
        items_per_batch=batch_size,
        dry_run=dry_run,
    )
    if not dry_run:
        history = store.get("queue_runs") or []
        history.append(
            dict(run_id=report.run_id, batch_ids=report.batch_ids, apply_results=apply_on_collect)
        )
        store.put("queue_runs", history)
    print(
        json.dumps(
            dict(
                run_id=report.run_id,
                calls=report.calls,
                batch_ids=report.batch_ids,
                dry_run=dry_run,
                skipped_in_flight=report.skipped_in_flight,
            )
        ),
        flush=True,
    )
    return report.batch_ids


def refresh_results(session: Session, store: ReviewStore) -> None:
    """Mirror shared-queue results for local previews; completion never needs this file."""
    source = "curriculum-review/results/" + str(store.get("run_id"))
    logs = (
        session.query(OperationLog).filter(OperationLog.source == source).order_by(OperationLog.id)
    )
    for log in logs:
        record = store.get("sense:" + str(log.entity_guid))
        if record is None:
            continue
        fact = json.loads(log.fact)
        if fact.get("suggestion"):
            record["suggestion"] = fact["suggestion"]
        if log.operation_type == "curriculum_placement_applied":
            record["applied"] = dict(level=fact["level"], receipt_id=log.id)
        store.put("sense:" + str(log.entity_guid), record)


def collect_all(
    session: Session, config: DataSourceConfig, store: ReviewStore, client: OpenAIBatchClient
) -> bool:
    """Collect all terminal jobs and apply results when submission authorized it."""
    jobs: list[dict[str, Any]] = store.get("jobs") or []
    if not jobs:
        raise ValueError("No submit-all jobs to collect")
    complete = True
    for job in jobs:
        if not job.get("batch_id"):
            raise ValueError("Finish or reconcile submission before collecting")
        if job.get("collected"):
            continue
        status = client.get_batch_status(job["batch_id"])
        job["status"] = status["status"]
        job["remote"] = status
        print(
            json.dumps(
                dict(
                    batch_id=job["batch_id"],
                    status=status["status"],
                    counts=status.get("request_counts"),
                )
            ),
            flush=True,
        )
        if status["status"] in ("completed", "failed", "expired", "cancelled"):
            if status.get("output_file_id"):
                responses = client.download_batch_results(status["output_file_id"])
                allowed = set(job["guids"])
                if any(result.get("custom_id") not in allowed for result in responses):
                    raise ValueError("Batch output contains a GUID outside this job")
                collect(store, responses)
            if status.get("error_file_id"):
                job["errors"] = client.download_batch_results(status["error_file_id"])
            job["collected"] = True
        else:
            complete = False
        store.put("jobs", jobs)
    if store.get("batch_policy")["apply_on_collect"]:
        print(json.dumps(dict(application=apply_results(session, config, store))), flush=True)
    return complete


def placement_stats(session: Session, store: ReviewStore, batch_session: Session) -> dict[str, Any]:
    """Count actual destinations for this fixed cohort, including unresolved staging."""
    from clients.batch_queue import BatchQueue, request_extra

    refresh_results(session, store)
    records = store.rows()
    original = {record["guid"]: record["current_level"] for record in records}
    current = {
        row.guid: row.difficulty_level
        for row in session.query(Lemma).filter(Lemma.guid.in_(original))
    }
    titles = {row.level: row for row in list_curriculum_levels(session)}
    destinations = Counter(current.values())
    outcomes: dict[str, str] = {}
    for row in (
        batch_session.query(BatchQueue)
        .filter(BatchQueue.agent_name == "curriculum_review")
        .order_by(BatchQueue.id)
    ):
        extra = request_extra(row)
        state = extra.get("state") or {}
        if state.get("review_id") == store.get("run_id"):
            guid = state["record"]["guid"]
            outcomes[guid] = str(extra.get("outcome") or row.status)
    return dict(
        selected=len(records),
        missing=len(original.keys() - current.keys()),
        selection=store.get("selection"),
        moved=sum(current[guid] != old for guid, old in original.items() if guid in current),
        still_staging=destinations.get(constants.STAGING_DIFFICULTY_LEVEL, 0),
        valid_suggestions=sum(bool(record.get("suggestion")) for record in records),
        applied=sum(bool(record.get("applied")) for record in records),
        no_suitable_level=sum(
            record.get("suggestion", {}).get("fit") == "none" for record in records
        ),
        queue_outcomes=dict(Counter(outcomes.values())),
        destinations=[
            dict(
                level=level,
                name=(
                    titles[level].name
                    if level in titles
                    else (
                        "Staging: placement undecided"
                        if level == constants.STAGING_DIFFICULTY_LEVEL
                        else "Untitled"
                    )
                ),
                cefr=titles[level].cefr if level in titles else None,
                count=count,
            )
            for level, count in sorted(
                destinations.items(), key=lambda pair: (pair[0] is None, pair[0] or 0)
            )
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[
            "prepare",
            "stats",
            "submit",
            "collect",
            "preview",
            "apply",
            "attach",
            "install-topics",
            "update-levels",
            "run-one",
            "apply-results",
            "balance-volumes",
            "submit-all",
            "collect-all",
            "watch",
        ],
    )
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--guid", help="Exactly one prepared sense for a synchronous test")
    parser.add_argument("--db-path", default=constants.WORDFREQ_DB_PATH)
    parser.add_argument("--old", default="6e3f0114")
    parser.add_argument("--new", default="641589ba")
    parser.add_argument("--phase", choices=["topics", "staging", "unlevelled"], default="topics")
    parser.add_argument("--model", default="gpt-5-mini")
    parser.add_argument("--catalogue", type=Path)
    parser.add_argument("--cefr-pass", action="store_true")
    parser.add_argument(
        "--b2-exceptions", type=Path, help="JSON list of explicitly approved exceptional GUIDs"
    )
    parser.add_argument("--approvals", type=Path, help="JSON object: GUID -> approved destination")
    parser.add_argument(
        "--topic-review",
        type=Path,
        help="Completed topic review required before staging submission",
    )
    parser.add_argument(
        "--batch-id", help="Reconcile an ambiguous submission using its OpenAI batch ID"
    )
    parser.add_argument(
        "--limit", type=int, help="Inventory sample size, or items considered by submit"
    )
    parser.add_argument(
        "--inventory",
        action="store_true",
        help="Sample the current staging inventory instead of a release diff",
    )
    parser.add_argument("--seed", type=int, default=20261117)
    parser.add_argument(
        "--topics-reviewed",
        action="store_true",
        help="Acknowledge completed editorial review, including manually resolved failures",
    )
    parser.add_argument("--output", type=Path, help="JSON statistics output path")
    parser.add_argument("--batch-size", type=int, default=325)
    parser.add_argument(
        "--apply-results",
        action="store_true",
        help="Authorize applying valid primary placements, parking no-fit senses at 1399",
    )
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan regular queue submission without writes or model calls",
    )
    args = parser.parse_args()
    config = DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=str(args.db_path))
    lock_handle = args.review.with_suffix(args.review.suffix + ".lock").open("a")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_handle.close()
        raise ValueError("Another command is using this review journal") from None
    store = ReviewStore(args.review)
    session = create_session(config)
    try:
        if args.action == "stats":
            batch_session = create_batch_database_session()
            try:
                report = placement_stats(session, store, batch_session)
            finally:
                batch_session.close()
            rendered = json.dumps(report, indent=2)
            if args.output:
                args.output.write_text(rendered + "\n")
            print(rendered)
        elif args.action == "balance-volumes":
            print(json.dumps(balance_volumes(session, config, dry_run=args.dry_run), indent=2))
        elif args.action == "apply-results":
            print(json.dumps(apply_results(session, config, store)), flush=True)
        elif args.action in ("submit", "submit-all"):
            if store.get("settings")["phase"] == "staging" and args.topics_reviewed:
                if not args.dry_run:
                    store.put(
                        "topics_complete",
                        dict(acknowledged=True, source="explicit editorial acknowledgement"),
                    )
            elif store.get("settings")["phase"] == "staging" and not store.get("topics_complete"):
                if not args.topic_review:
                    raise ValueError("--topic-review is required before staging")
                topics = ReviewStore(args.topic_review)
                try:
                    refresh_results(session, topics)
                    same_release = all(
                        topics.get("settings")[key] == store.get("settings")[key]
                        for key in ("old", "new")
                    )
                    if (
                        not topics.get("prepared")
                        or topics.get("settings")["phase"] != "topics"
                        or not same_release
                        or not topics.rows()
                        or any(not row.get("suggestion") for row in topics.rows())
                    ):
                        raise ValueError("Complete topic suggestions before staging submission")
                    if not args.dry_run:
                        store.put("topics_complete", True)
                finally:
                    topics.db.close()
            batch_session = create_batch_database_session()
            try:
                manager = BatchQueueManager(batch_session)
                if not args.dry_run:
                    refresh_results(session, store)
                submit_all(
                    session,
                    store,
                    manager,
                    args.batch_size,
                    apply_on_collect=args.apply_results,
                    dry_run=args.dry_run,
                    limit=(args.limit or 500) if args.action == "submit" else None,
                )
            finally:
                batch_session.close()
        elif args.action in ("collect-all", "watch"):
            if store.get("queue_runs"):
                raise ValueError(
                    "Regular queue jobs are completed by Barsukas or python -m agents.common.batch complete --batch-id <id>; this command is for legacy journals"
                )
            if args.poll_seconds < 1:
                raise ValueError("--poll-seconds must be positive")
            client = OpenAIBatchClient()
            failures = 0
            while True:
                try:
                    done = collect_all(session, config, store, client)
                    failures = 0
                except Exception as exc:
                    session.rollback()
                    failures += 1
                    print(f"Collection failure {failures}: {exc}", flush=True)
                    if args.action != "watch" or failures >= 5:
                        raise
                    time.sleep(args.poll_seconds)
                    continue
                if done or args.action == "collect-all":
                    break
                time.sleep(args.poll_seconds)
        elif args.action == "update-levels":
            if not args.catalogue:
                raise ValueError("--catalogue metadata JSON is required")
            print(
                f"Updated {update_levels(session, config, json.loads(args.catalogue.read_text()))} curriculum levels"
            )
        elif args.action == "install-topics":
            if not args.catalogue:
                raise ValueError("--catalogue is required")
            print(
                f"Installed {install_topics(session, config, json.loads(args.catalogue.read_text()))} topics"
            )
        elif args.action == "run-one":
            if not args.guid:
                raise ValueError("--guid is required")
            print(json.dumps(run_one(session, store, args.guid, OpenAIClient()), indent=2))
            if args.apply_results:
                print(json.dumps(apply_results(session, config, store)), flush=True)
        elif args.action == "prepare":
            print(
                prepare(
                    session,
                    store,
                    args.old,
                    args.new,
                    args.phase,
                    args.model,
                    catalogue=json.loads(args.catalogue.read_text()) if args.catalogue else [],
                    cefr_pass=args.cefr_pass,
                    inventory=args.inventory,
                    limit=args.limit,
                    seed=args.seed,
                    b2_exceptions=(
                        json.loads(args.b2_exceptions.read_text()) if args.b2_exceptions else []
                    ),
                )
            )
        elif args.action == "preview":
            refresh_results(session, store)
            if args.approvals:
                print(
                    json.dumps(
                        [
                            asdict(move)
                            for move in approved_moves(
                                session, store, json.loads(args.approvals.read_text())
                            )
                        ],
                        indent=2,
                    )
                )
            else:
                print(json.dumps(store.rows(), indent=2))
        elif args.action == "apply":
            if not args.approvals:
                raise ValueError("--approvals is required")
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            moves = approved_moves(session, store, json.loads(args.approvals.read_text()))
            if moves:
                print("Minor backup:", create_backup(config, "curriculum-review", tier="minor"))
                for entry in store.get("settings")["catalogue"]:
                    if entry["level"] in {move.new_level for move in moves}:
                        existing = get_curriculum_level(session, entry["level"])
                        if existing and (
                            existing.name != entry["name"]
                            or existing.notes != catalogue_notes(entry)
                        ):
                            raise ValueError(f"Topic catalogue changed: {entry['level']}")
                        if existing is None:
                            if (
                                session.query(Lemma)
                                .filter(Lemma.difficulty_level == entry["level"])
                                .first()
                            ):
                                raise ValueError(f"Proposed number now occupied: {entry['level']}")
                            set_curriculum_level(
                                session,
                                entry["level"],
                                entry["name"],
                                cefr=entry.get("cefr"),
                                notes=catalogue_notes(entry),
                                source="curriculum-review",
                            )
                apply_moves(session, moves, source=f"curriculum-review/{args.review.name}")
                session.commit()
            print(f"Applied {len(moves)} moves")
        else:
            if not store.get("prepared"):
                raise ValueError("Finish preparing the complete inventory first")
            client = OpenAIBatchClient()
            active = store.get("active")
            if args.action == "attach" and store.get("jobs"):
                if not args.batch_id:
                    raise ValueError("--batch-id is required")
                status = client.get_batch_status(args.batch_id)
                jobs = store.get("jobs")
                matching = [
                    job
                    for job in jobs
                    if job.get("creating") and job.get("file_id") == status.get("input_file_id")
                ]
                if len(matching) != 1:
                    raise ValueError("No ambiguous job matches this input file")
                matching[0].update(batch_id=args.batch_id, status=status["status"], creating=False)
                store.put("jobs", jobs)
            elif args.action == "attach":
                if not args.batch_id or active or not store.get("submitting"):
                    raise ValueError("attach needs --batch-id and an ambiguous submission")
                status = client.get_batch_status(args.batch_id)
                if status.get("input_file_id") != store.get("uploaded"):
                    raise ValueError("Batch input file does not match this review")
                store.put("active", args.batch_id)
                store.put("submitting", False)
            else:
                if not active:
                    raise ValueError("No active batch")
                status = client.get_batch_status(active)
                print(status["status"])
                if status["status"] in ("completed", "failed", "expired", "cancelled"):
                    if status.get("output_file_id"):
                        collect(store, client.download_batch_results(status["output_file_id"]))
                    store.put("batch:" + active, status)
                    store.put("active", None)
                    store.put("uploaded", None)
                    store.put("submitting", False)
    finally:
        session.close()
        store.db.close()
        lock_handle.close()


if __name__ == "__main__":
    main()
