#!/usr/bin/python3

"""Prometheus metrics for Barsukas web interface.

This module provides metrics instrumentation for:
- Request counts (by endpoint, method, status code)
- Request latency
- Database query latency
- Resource usage (CPU, memory)
"""

import time
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Generator, TypeVar

try:
    from prometheus_client import Counter, Gauge, Histogram, generate_latest
    from prometheus_client.registry import CollectorRegistry

    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


class _NoOpMetric:
    """Stub metric that silently ignores all operations."""

    def labels(self, **kwargs: Any) -> "_NoOpMetric":
        return self

    def inc(self, amount: float = 1) -> None:
        pass

    def set(self, value: float) -> None:
        pass

    def observe(self, amount: float) -> None:
        pass


_NOOP = _NoOpMetric()

if HAS_PROMETHEUS:
    # Create a custom registry for Barsukas metrics
    REGISTRY = CollectorRegistry(auto_describe=True)

    # Request metrics
    REQUEST_COUNT = Counter(
        "barsukas_http_requests_total",
        "Total number of HTTP requests",
        ["method", "endpoint", "status_code"],
        registry=REGISTRY,
    )

    REQUEST_LATENCY = Histogram(
        "barsukas_http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method", "endpoint"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        registry=REGISTRY,
    )

    # Database metrics
    DB_QUERY_LATENCY = Histogram(
        "barsukas_db_query_duration_seconds",
        "Database query latency in seconds",
        ["operation"],
        buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
        registry=REGISTRY,
    )

    DB_QUERY_COUNT = Counter(
        "barsukas_db_queries_total",
        "Total number of database queries",
        ["operation"],
        registry=REGISTRY,
    )

    # LLM call metrics
    LLM_CALL_COUNT = Counter(
        "barsukas_llm_calls_total",
        "Total number of LLM API calls",
        ["backend", "model", "status"],
        registry=REGISTRY,
    )

    LLM_CALL_LATENCY = Histogram(
        "barsukas_llm_call_duration_seconds",
        "LLM API call latency in seconds",
        ["backend", "model"],
        buckets=(1.0, 2.0, 5.0, 10.0, 15.0, 20.0, 30.0, 45.0, 60.0, 90.0, 120.0),
        registry=REGISTRY,
    )

    LLM_TOKENS_TOTAL = Counter(
        "barsukas_llm_tokens_total",
        "Total number of tokens processed by LLM calls",
        ["backend", "model", "direction"],
        registry=REGISTRY,
    )

    # Resource usage metrics
    CPU_USAGE = Gauge(
        "barsukas_process_cpu_percent",
        "Current CPU usage percentage of the Barsukas process",
        registry=REGISTRY,
    )

    MEMORY_USAGE_BYTES = Gauge(
        "barsukas_process_memory_bytes",
        "Current memory usage in bytes of the Barsukas process",
        ["type"],
        registry=REGISTRY,
    )

    MEMORY_USAGE_PERCENT = Gauge(
        "barsukas_process_memory_percent",
        "Current memory usage percentage of the Barsukas process",
        registry=REGISTRY,
    )

    # Process info
    PROCESS_START_TIME = Gauge(
        "barsukas_process_start_time_seconds",
        "Start time of the Barsukas process (Unix timestamp)",
        registry=REGISTRY,
    )

    OPEN_FILE_DESCRIPTORS = Gauge(
        "barsukas_process_open_fds",
        "Number of open file descriptors",
        registry=REGISTRY,
    )
else:
    REGISTRY = None  # type: ignore[assignment]
    REQUEST_COUNT = _NOOP  # type: ignore[assignment]
    REQUEST_LATENCY = _NOOP  # type: ignore[assignment]
    DB_QUERY_LATENCY = _NOOP  # type: ignore[assignment]
    DB_QUERY_COUNT = _NOOP  # type: ignore[assignment]
    LLM_CALL_COUNT = _NOOP  # type: ignore[assignment]
    LLM_CALL_LATENCY = _NOOP  # type: ignore[assignment]
    LLM_TOKENS_TOTAL = _NOOP  # type: ignore[assignment]
    CPU_USAGE = _NOOP  # type: ignore[assignment]
    MEMORY_USAGE_BYTES = _NOOP  # type: ignore[assignment]
    MEMORY_USAGE_PERCENT = _NOOP  # type: ignore[assignment]
    PROCESS_START_TIME = _NOOP  # type: ignore[assignment]
    OPEN_FILE_DESCRIPTORS = _NOOP  # type: ignore[assignment]


def update_resource_metrics() -> None:
    """Update resource usage metrics.

    This should be called periodically or before generating metrics output.
    Requires psutil to be installed; silently does nothing if unavailable.
    """
    if not HAS_PSUTIL:
        return

    process = psutil.Process()

    # CPU usage (percent since last call)
    try:
        cpu_percent = process.cpu_percent(interval=None)
        CPU_USAGE.set(cpu_percent)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    # Memory usage
    try:
        mem_info = process.memory_info()
        MEMORY_USAGE_BYTES.labels(type="rss").set(mem_info.rss)
        MEMORY_USAGE_BYTES.labels(type="vms").set(mem_info.vms)
        MEMORY_USAGE_PERCENT.set(process.memory_percent())
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    # Process start time
    try:
        PROCESS_START_TIME.set(process.create_time())
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    # Open file descriptors (Unix only)
    try:
        OPEN_FILE_DESCRIPTORS.set(process.num_fds())
    except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
        # num_fds() not available on Windows
        pass


def get_metrics_output() -> bytes:
    """Generate Prometheus metrics output.

    Returns:
        Prometheus metrics in text format as bytes, or an empty response
        if prometheus_client is not installed.
    """
    if not HAS_PROMETHEUS:
        return b""
    update_resource_metrics()
    return generate_latest(REGISTRY)  # type: ignore[no-any-return]


@contextmanager
def track_db_latency(operation: str = "query") -> Generator[None, None, None]:
    """Context manager to track database query latency.

    Args:
        operation: The type of database operation (e.g., "query", "commit", "select").

    Usage:
        with track_db_latency("select"):
            result = session.execute(query)
    """
    start_time = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start_time
        DB_QUERY_LATENCY.labels(operation=operation).observe(duration)
        DB_QUERY_COUNT.labels(operation=operation).inc()


F = TypeVar("F", bound=Callable[..., Any])


def track_db_operation(operation: str = "query") -> Callable[[F], F]:
    """Decorator to track database operation latency.

    Args:
        operation: The type of database operation.

    Usage:
        @track_db_operation("select")
        def get_lemma(session, lemma_id):
            return session.get(Lemma, lemma_id)
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with track_db_latency(operation):
                return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


class RequestMetricsMiddleware:
    """Track request metrics for each HTTP request.

    This class provides methods to be used as Flask before_request
    and after_request handlers.
    """

    @staticmethod
    def before_request() -> None:
        """Store request start time."""
        from flask import g

        g.request_start_time = time.perf_counter()

    @staticmethod
    def after_request(response: Any) -> Any:
        """Record request metrics after response is generated.

        Args:
            response: The Flask response object.

        Returns:
            The unmodified response object.
        """
        from flask import g, request

        # Calculate request duration
        start_time = getattr(g, "request_start_time", None)
        if start_time is not None:
            duration = time.perf_counter() - start_time

            # Get endpoint name (use rule or path)
            endpoint = request.endpoint or request.path

            # Record latency
            REQUEST_LATENCY.labels(method=request.method, endpoint=endpoint).observe(duration)

            # Record request count (exclude noisy 404 scans/probes)
            if response.status_code != 404:
                REQUEST_COUNT.labels(
                    method=request.method, endpoint=endpoint, status_code=response.status_code
                ).inc()

        return response


@contextmanager
def track_llm_call(backend: str, model: str) -> Generator[None, None, None]:
    """Context manager to track LLM API call latency and count.

    Args:
        backend: The LLM backend (e.g., "openai", "anthropic", "gemini", "ollama").
        model: The model name being used.

    Usage:
        with track_llm_call("openai", "gpt-4o"):
            response = client.generate_chat(prompt)
    """
    start_time = time.perf_counter()
    status = "success"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        duration = time.perf_counter() - start_time
        LLM_CALL_LATENCY.labels(backend=backend, model=model).observe(duration)
        LLM_CALL_COUNT.labels(backend=backend, model=model, status=status).inc()


def record_llm_call(
    backend: str,
    model: str,
    duration_seconds: float,
    status: str = "success",
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> None:
    """Record metrics for an LLM API call.

    This function is useful when you need to record metrics after the fact,
    rather than using the context manager.

    Args:
        backend: The LLM backend (e.g., "openai", "anthropic", "gemini", "ollama").
        model: The model name being used.
        duration_seconds: How long the call took in seconds.
        status: "success" or "error".
        tokens_in: Number of input tokens (optional).
        tokens_out: Number of output tokens (optional).
    """
    LLM_CALL_LATENCY.labels(backend=backend, model=model).observe(duration_seconds)
    LLM_CALL_COUNT.labels(backend=backend, model=model, status=status).inc()

    if tokens_in > 0:
        LLM_TOKENS_TOTAL.labels(backend=backend, model=model, direction="input").inc(tokens_in)
    if tokens_out > 0:
        LLM_TOKENS_TOTAL.labels(backend=backend, model=model, direction="output").inc(tokens_out)
