# Agents → Work Discovery Refactor Plan

> Status note (August 2026): the sentence-related Buivolas, Žvirblis, and
> Šarka entry points now follow the target split. Their implementations live in
> `src/sentences`, their CLIs enqueue canonical tasks by default, and inline
> execution requires `--execute-inline`. Legacy task/import aliases remain for
> persisted work and external callers.
>
> The lemma finders now emit capability-named deduplication keys and standardized
> `lemma_id` / `language_code` / `languages` payloads. They recognize active
> animal-named deduplication keys during migration, and workers retain
> `lang_code` only as a persisted-task compatibility alias.

## Why this refactor is needed

The current codebase mixes two models:

1. **Animal-named agents that both discover and execute work**, and
2. **Barsukas workqueue handlers that execute queued jobs**.

As the framework shifts toward queue-first execution, this creates duplicated logic, naming drift, and operator confusion.

## Current-state review (key findings)

- Agent docs and style guidance still frame agents as autonomous executors, not discovery-only schedulers.
- Several agents now support `--use-workqueue`, but enqueue task types are still tied to agent names (for example `sernas_generate_synonyms`, `papuga_generate_pronunciation`, `voras_populate_translations`).
- Workqueue already has shared capability handlers (`workqueue/handlers/*.py`) with generic task types such as `generate_synonyms`, `generate_pronunciations`, `add_missing_translations`.
- Registry currently accepts both generic and agent-prefixed task types, increasing compatibility burden.
- Pipeline ordering already exists and is task-type-based, which is a good foundation for capability-centric execution.
- Barsukas UI and launcher remain largely agent-centric, reinforcing the old mental model.

## Target architecture

### Core principle

- **Agents become discovery/planning entry points only.**
- **Execution belongs to capability handlers in `workqueue/handlers/`, independent of agent names.**

### Conceptual split

- **Work Finders (agent side):** determine *what* needs to be done.
- **Work Queue + Handlers (execution side):** perform *how* the work is done.

### Naming model

- Queue task types use **capability names**, not agent names.
- Keep animal names for human-facing finder CLIs only (optional long-term).

## Proposed task taxonomy (canonical)

Use generic canonical task types like:

- `translations.generate_missing`
- `translations.regenerate`
- `forms.generate`
- `pronunciations.generate`
- `synonyms.generate`
- `grammar_facts.generate`
- `conversations.generate`
- `definitions.generate`
- `sentences.translate`
- `audio.generate.lemma`
- `audio.generate.sentence`

Notes:

- Keep current snake_case names temporarily as aliases during migration.
- Add explicit versioning in payloads (`"schema_version": 1`) for forward compatibility.

## Module boundaries after refactor

### `src/agents/`

- Keep CLI UX, selection filters, batching, confirmation, and dry-run previews.
- Rename internal classes from `*Agent` to `*Finder` over time (with compatibility aliases).
- Remove direct LLM execution paths from finder workflows once queue parity is complete.

### `src/workqueue/`

- `task_queue.py`: enqueue/claim/dedup/pipeline semantics.
- `handlers/`: the only place that executes LLM/data mutation logic.
- `registry.py`: canonical routing table with deprecated aliases and deprecation logging.

### `src/barsukas/`

- Move UX language from “run agent” to “queue operation” and “run discovery”.
- Pipeline UI should display capability stages, with optional “discovered by” metadata.

## Migration plan

### Phase 0 — Inventory and contracts (short)

1. Define canonical task-type constants in one place (for example `workqueue/task_types.py`).
2. Define payload schemas per task in one place (typed dictionaries/dataclasses).
3. Add a compatibility map from legacy names (`sernas_generate_synonyms`) to canonical names.
4. Add structured deprecation warnings when legacy names are enqueued.

### Phase 1 — Dual-write / dual-read compatibility

1. Update all enqueue paths in agent CLIs to emit canonical task names.
2. Keep registry aliases so old tasks can still run.
3. Standardize dedup keys around `(task_type, target_type, target_id, normalized payload subset)`.
4. Ensure pipeline ordering keys use canonical task names.

### Phase 2 — Extract execution from agents

1. For each agent that still executes directly, extract execution logic into a handler or reusable execution module under `workqueue/handlers`.
2. Keep agents responsible for:
   - target discovery,
   - queue submission,
   - reporting counts/preview output.
3. Add “inline execution” only as explicit debug mode (`--execute-inline`) and disable by default.

### Phase 3 — UX and terminology shift

1. Update `agents_launcher` terminology to “Discovery Jobs” and “Queued Operations”.
2. Show queue status by canonical capability stage.
3. Keep agent animal labels as secondary metadata for continuity during transition.

### Phase 4 — Removal of legacy coupling

1. Remove agent-prefixed task types from enqueue call sites.
2. Remove registry aliases after one release cycle.
3. Remove direct execution paths from agent CLIs where not needed.
4. Update docs (`src/agents/README.md`, `src/agents/STYLE.md`) to codify discovery-only responsibilities.

## Suggested interface contract (lightweight)

Define a shared protocol for finders:

```python
class WorkFinder(Protocol):
    def discover(self, session: Session, args: argparse.Namespace) -> list[WorkItem]: ...
    def enqueue(self, session: Session, items: list[WorkItem], dry_run: bool) -> EnqueueSummary: ...
```

And for handlers:

```python
Handler = Callable[[Session, dict[str, Any]], str]
```

Benefits:

- Uniform CLI flow across all finders.
- Easy instrumentation (discover count vs enqueued vs completed).
- Reduced code duplication in enqueue/report scaffolding.

## Observability and safety requirements

- Add `source_component` metadata in task payloads (e.g., `"source_component": "agents.sernas"`).
- Log canonical `task_type` plus `legacy_task_type` when aliases are used.
- Add metrics counters:
  - `tasks_enqueued_total{task_type}`
  - `tasks_completed_total{task_type}`
  - `tasks_failed_total{task_type}`
  - `tasks_legacy_alias_total{legacy_task_type}`
- Keep dedup behavior stable throughout migration to avoid task floods.

## Rollout order (recommended)

1. **voras + vilkas + papuga + sernas** (already closest to queue model).
2. **lape + sarka + zvirblis + vieversys**.
3. Any remaining agents still primarily inline.

This order minimizes risk because the first group already has queue pathways and handlers.

## Definition of done

- All production enqueue call sites use canonical capability task names.
- Worker executes capability handlers only; no business logic forks based on agent naming.
- Agent CLIs primarily discover and enqueue (execution removed or explicitly debug-only).
- Barsukas UI and docs describe capability pipeline and queue operations first.
- Legacy task-name aliases removed after migration window.

## Immediate next actions (this sprint)

1. Introduce canonical task constants + alias map.
2. Convert enqueue call sites in `voras`, `vilkas`, `papuga`, and `sernas`.
3. Add deprecation logging + simple metrics for alias use.
4. Update `src/agents/README.md` and `src/agents/STYLE.md` language to discovery-first architecture.
