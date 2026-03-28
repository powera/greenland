# Barsukas Prometheus Metrics

This document describes Prometheus metrics exposed by Barsukas at `GET /metrics`.

## Endpoint

- Path: `/metrics`
- Content type: `text/plain; charset=utf-8`
- Source: `barsukas.metrics.get_metrics_output()` with Barsukas' custom collector registry.

## HTTP request metrics

### `barsukas_http_requests_total`
Counter of completed HTTP requests (non-404 only).

Labels:
- `method` (HTTP method)
- `endpoint` (Flask endpoint name when available, otherwise route path)
- `status_code` (HTTP status code)

### `barsukas_http_request_duration_seconds`
Histogram of HTTP request latency.

Labels:
- `method`
- `endpoint`

## Database metrics

### `barsukas_db_query_duration_seconds`
Histogram for database operation timing.

Barsukas now auto-instruments SQLAlchemy cursor execution for the app's engine, so this metric is emitted for most DB queries without manual wrappers.

Labels:
- `operation` (for example `query`, `select`, `commit`)

### `barsukas_db_queries_total`
Counter paired with `barsukas_db_query_duration_seconds`.

Labels:
- `operation`

## LLM metrics

### `barsukas_llm_calls_total`
Counter of LLM calls recorded via Barsukas' callback into `clients.unified_client`.

Labels:
- `backend` (provider family)
- `model` (model name)
- `status` (`success`, `error`)

### `barsukas_llm_call_duration_seconds`
Histogram of LLM call duration.

Labels:
- `backend`
- `model`

### `barsukas_llm_tokens_total`
Counter of LLM token usage.

Labels:
- `backend`
- `model`
- `direction` (`input`, `output`)

## Server mode and runtime flags

### `barsukas_server_mode_info`
Gauge set to `1` with labels representing the active mode/configuration.

Labels:
- `server_mode` (`readwrite` or `readonly`)
- `backend` (`sqlite`, `postgres`, `jsonl`)
- `readonly` (`true`/`false`)
- `debug` (`true`/`false`)

### `barsukas_server_read_only`
Boolean gauge (`1` when read-only mode is enabled, otherwise `0`).

### `barsukas_server_debug`
Boolean gauge (`1` when Flask debug mode is enabled, otherwise `0`).

## Process/resource metrics

These are updated at scrape time when `psutil` is installed.

### `barsukas_process_cpu_percent`
Gauge of process CPU usage percent.

### `barsukas_process_memory_bytes`
Gauge of process memory usage in bytes.

Labels:
- `type` (`rss`, `vms`)

### `barsukas_process_memory_percent`
Gauge of process memory usage percent.

### `barsukas_process_start_time_seconds`
Gauge containing process start time as Unix timestamp.

### `barsukas_process_open_fds`
Gauge for open file descriptor count (Unix only).

## Gaps and recommended next steps

1. **Query instrumentation coverage should stay comprehensive.**
   - Core SQL query timing is now auto-instrumented via SQLAlchemy engine events.
   - If any non-SQLAlchemy access paths are introduced in future, they should be wrapped with helper timing so this histogram remains representative.

2. **No explicit up/down health metric yet.**
   - A dedicated gauge such as `barsukas_db_up` (0/1) could simplify alerts.

3. **Per-blueprint/feature metrics could help operational triage.**
   - For example: long-running release-sync operations, worker queue depths, and audio generation success/failure counts.
