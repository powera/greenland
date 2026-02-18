from benchmarks.server.benchmark_worker import BenchmarkRunWorker


def test_touch_interactive_local_job_allows_refresh_for_same_model():
    worker = BenchmarkRunWorker()

    assert worker.touch_interactive_local_job("llama3", owner="verbalator") is True
    assert worker.touch_interactive_local_job("llama3", owner="verbalator") is True


def test_touch_interactive_local_job_blocks_other_models_until_expired():
    worker = BenchmarkRunWorker()
    worker._interactive_local_ttl_seconds = 0.01

    assert worker.touch_interactive_local_job("llama3", owner="verbalator") is True
    assert worker.touch_interactive_local_job("gemma", owner="verbalator") is False

    import time

    time.sleep(0.03)
    assert worker.touch_interactive_local_job("gemma", owner="verbalator") is True
