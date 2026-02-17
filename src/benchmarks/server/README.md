# Benchmark Server

A Flask web application for managing and visualizing LLM benchmark results.

## Overview

Benchmark Server provides a web interface for:
- Viewing benchmark results in an interactive dashboard
- Comparing model performance across different benchmarks
- Exploring detailed run results
- Managing models and benchmarks

This application uses the same benchmark database (`benchmarks.db`) as the CLI tools but provides a more user-friendly way to explore results.

## Quick Start

### Running the Server

```bash
# From the project root
src/benchmarks/launch_server.sh
```

Or with custom options:

```bash
src/benchmarks/launch_server.sh --port 5556 --debug
```

Or run directly:

```bash
PYTHONPATH=src python src/benchmarks/server/app.py --port 5556 --debug
```

The server will be available at http://127.0.0.1:5556

### Command Line Options

- `--host HOST`: Host to bind to (default: 127.0.0.1)
- `--port PORT`: Port to bind to (default: 5556)
- `--debug`: Enable debug mode
- `--db-path PATH`: Path to benchmarks database (default: src/benchmarks/schema/benchmarks.db)

### Environment Variables

- `BENCH_SERVER_PORT`: Server port (default: 5556)
- `BENCH_SERVER_SECRET_KEY`: Flask secret key (default: dev key)
- `BENCH_SERVER_DEBUG`: Enable debug mode (true/false)
- `BENCH_SERVER_DB_PATH`: Path to database
- `BENCH_SERVER_RUNNER_ENABLED`: Enable/disable benchmark runs from UI (default: true)
- `BENCH_SERVER_RUNNER_ALLOWED_CIDRS`: Comma-separated CIDRs allowed to start runs (default includes loopback, RFC1918, and TailScale `100.64.0.0/10`)
- `BENCH_SERVER_RUNNER_BLOCK_PROXIED_REQUESTS`: Reject requests carrying proxy headers like `X-Forwarded-For` (default: true)

## Features

### Dashboard
- Matrix view of all benchmarks vs. models
- Color-coded scores (green=excellent, red=poor)
- Filter by model type (local/remote)
- Search functionality
- Quick links to detailed results

### Benchmarks
- List all available benchmarks
- View benchmark details and leaderboards
- See question counts and statistics
- Run benchmarks from UI via a single-threaded worker queue

### Models
- List all registered models
- View model performance across benchmarks
- See run history and statistics

### Run Details
- Detailed breakdown of each benchmark run
- View all correct and incorrect answers
- See thought processes (if available)
- Response times per question
- Side-by-side comparison of multiple runs

## Architecture

```
src/benchmarks/
├── launch_server.sh       # Launch script
└── server/                # Flask application
    ├── app.py             # Main Flask application
    ├── config.py          # Configuration settings
    ├── routes/            # Blueprint modules
    │   ├── dashboard.py   # Main scoreboard
    │   ├── benchmarks.py  # Benchmark management
    │   ├── models.py      # Model listing/viewing
    │   └── runs.py        # Run details and comparison
    ├── templates/         # Jinja2 templates
    │   ├── base.html      # Base template
    │   ├── dashboard/
    │   ├── benchmarks/
    │   ├── models/
    │   └── runs/
    └── static/            # Static assets (CSS, JS)
```

## Database

The application uses the same SQLAlchemy models defined in:
- `src/benchmarks/datastore/benchmarks.py` - Run, RunDetail, Question, Benchmark
- `src/benchmarks/datastore/common.py` - Model

## Relationship to CLI Tools

This web interface complements the existing CLI tools:
- Use CLI tools (`run_benchmark.py`) to execute benchmarks
- Use this web interface to view and explore results
- Both share the same database

## Future Enhancements

- [ ] Real-time benchmark run progress updates
- [ ] Trend charts showing performance over time
- [ ] Export results to CSV/JSON
- [ ] Annotations/notes on runs
- [ ] Compare runs side-by-side (enhanced)
- [ ] API endpoints for programmatic access
- [ ] Real-time progress updates during runs

## Development

The application follows Flask best practices:
- Blueprints for modular routes
- Jinja2 templates with inheritance
- Bootstrap 5 for UI
- Form submissions (no AJAX) per project guidelines
- SQLAlchemy for database access

## Port Selection

Default port is 5556 to avoid conflicts:
- Barsukas uses 5555
- Benchmark Server uses 5556

## Notes

- The server runs on localhost (127.0.0.1) only for security
- Benchmark runs are queued and executed one-at-a-time by a background worker
- Run-triggering requests are gated to local/private CIDRs and reject proxied headers by default
- Read-only mode can be enabled via config
- The application is designed to eventually merge with Barsukas
- Currently maintains separate database (benchmarks.db vs linguistics.sqlite)
