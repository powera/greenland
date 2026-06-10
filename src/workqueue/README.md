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

Tasks are normally enqueued from Barsukas via `enqueue_task()`.
