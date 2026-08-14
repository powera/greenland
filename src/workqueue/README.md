# workqueue

Background task queue used by Barsukas to defer expensive work (LLM calls,
audio synthesis, exports) so the web UI stays responsive. Tasks are stored in
the database and executed by a worker daemon.

## Layout

- `task_queue.py` — task status/type enums and queue operations (enqueue,
  claim, complete, fail)
- `registry.py` — maps task names (e.g., `words.translations`) to handler
  functions
- `pipeline_order.py` — dependency ordering so prerequisites run first
  (e.g., translations before pronunciations)
- `handlers/` — handler implementations grouped by capability (`words/`,
  `sentences/`, `audio/`, `wireword/`, conversations)
- `worker.py` — daemon that claims and executes tasks
- `tools.py` — shared handler utilities (config building, session management)

## Usage

```bash
PYTHONPATH=src python src/workqueue/worker.py --help
```

Tasks are enqueued from Barsukas and from animal-named discovery CLIs via
`enqueue_task()`. Canonical names describe the function being performed, not
the code that discovered it. Sentence examples include
`sentences.examples.generate`, `sentences.patterns.generate`,
`sentences.translate`, `conversations.generate`, and
`conversations.definitions.generate`.

Legacy agent-prefixed names remain registry aliases only so already-persisted
tasks can drain. New enqueue sites must use `TaskType` constants and canonical
names.

Word task payloads identify the target with `lemma_id`. Use `language_code` for
a single language and `languages` for a set. `lang_code` is accepted only as a
legacy payload alias. Deduplication keys begin with the canonical capability
name, never the animal-named discovery CLI.
