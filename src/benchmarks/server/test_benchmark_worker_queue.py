from datetime import datetime, timedelta, timezone

from benchmarks.server.benchmark_worker import BenchmarkRunWorker


def test_cancel_task_marks_queued_task_as_canceled():
    worker = BenchmarkRunWorker()
    worker.enqueue("0016_antonym", "model-a")

    assert worker.cancel_task(1) is True

    status = worker.status()
    assert status["queued"] == 0
    assert status["queued_tasks"] == []
    assert status["recent_tasks"][0]["state"] == "canceled"


def test_status_only_returns_recent_tasks_within_24h_window():
    worker = BenchmarkRunWorker()
    worker.enqueue("0016_antonym", "model-a")

    with worker._state_lock:
        task = worker._tasks[1]
        task.state = "completed"
        task.finished_at = datetime.now(timezone.utc)
        task.enqueued_at = datetime.now(timezone.utc) - timedelta(hours=30)

    status = worker.status()
    assert status["recent_tasks"] == []
