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

import psutil
from prometheus_client import Counter, Gauge, Histogram, generate_latest
from prometheus_client.registry import CollectorRegistry

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


def update_resource_metrics() -> None:
    """Update resource usage metrics.

    This should be called periodically or before generating metrics output.
    """
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
        Prometheus metrics in text format as bytes.
    """
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

            # Record request count
            REQUEST_COUNT.labels(
                method=request.method, endpoint=endpoint, status_code=response.status_code
            ).inc()

        return response
