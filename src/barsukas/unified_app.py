#!/usr/bin/python3

"""
Unified launcher for Barsukas that runs both the Flask web server
and the task worker in the same Python process using threads.

This avoids SQLite concurrency issues by using a single process.
"""

import argparse
import logging
import os
import signal
import sys
import threading
import types
from pathlib import Path
from typing import Optional

from barsukas.config import Config
from barsukas.app import create_app
from barsukas.personas import get_persona, list_personas, PersonaConfig
from barsukas.workers.task_worker import run_worker, STOP_EVENT
from wordfreq.storage.backend.config import DataSourceConfig

logger = logging.getLogger(__name__)


def run_flask_server(
    host: str,
    port: int,
    debug: bool,
    readonly: bool,
    persona: Optional[PersonaConfig] = None,
) -> None:
    """Run the Flask server in the current thread."""
    app = create_app()

    if debug:
        app.config["DEBUG"] = True

    if readonly:
        app.config["READONLY"] = True

    # Apply persona-specific settings for UI visibility
    if persona:
        app.config["ALLOW_OUTBOUND_CALLS"] = persona.allow_outbound_calls
        app.config["ALLOW_API_KEYS"] = persona.allow_api_keys
        app.config["ENABLE_WORKER"] = persona.enable_worker
    else:
        # Defaults when no persona specified
        app.config["ALLOW_OUTBOUND_CALLS"] = True
        app.config["ALLOW_API_KEYS"] = True
        app.config["ENABLE_WORKER"] = True

    logger.info(f"Starting Barsukas Flask server on http://{host}:{port}")
    logger.info(f"Database: {app.config['DB_PATH']}")
    if readonly:
        logger.info("Running in READ-ONLY mode - no edits allowed")

    # Run Flask server (this blocks until server stops)
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)


def main() -> None:
    """Run both Flask server and task worker in the same process."""
    parser = argparse.ArgumentParser(
        description="Barsukas Unified Launcher - Flask server + Task worker"
    )
    parser.add_argument(
        "--host", type=str, default=Config.HOST, help=f"Host to bind to (default: {Config.HOST})"
    )
    parser.add_argument(
        "--port", type=int, default=Config.PORT, help=f"Port to run on (default: {Config.PORT})"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument(
        "--readonly", action="store_true", help="Run in read-only mode (no edits allowed)"
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Worker poll interval in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--no-worker", action="store_true", help="Don't start the background worker (Flask only)"
    )
    parser.add_argument(
        "--postgres",
        action="store_true",
        help="Use PostgreSQL backend (builds URL from constants + keys/postgres.key)",
    )
    parser.add_argument(
        "--persona",
        type=str,
        choices=["prod", "golden", "local"],
        help="Launch persona (prod, golden, local) - overrides other backend settings",
    )
    parser.add_argument(
        "--list-personas",
        action="store_true",
        help="List available personas and exit",
    )
    args = parser.parse_args()

    # Handle --list-personas
    if args.list_personas:
        print("Available personas:")
        for name, description in list_personas():
            print(f"  {name:8} - {description}")
        sys.exit(0)

    # Get persona config if specified (or from environment)
    persona: Optional[PersonaConfig] = None
    persona_name = args.persona or os.environ.get("BARSUKAS_PERSONA")
    if persona_name:
        try:
            persona = get_persona(persona_name)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

    # Apply persona overrides
    if persona:
        if persona.readonly:
            args.readonly = True
        if not persona.enable_worker:
            args.no_worker = True
        if persona.use_postgres:
            args.postgres = True

    # Set up logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        force=True,
    )

    # Determine backend type
    if args.postgres or os.environ.get("USE_POSTGRES_BACKEND") == "true":
        # PostgreSQL mode - build URL from template + key
        try:
            postgres_url = DataSourceConfig.build_postgres_url()
            os.environ["POSTGRES_URL"] = postgres_url
            os.environ["STORAGE_BACKEND"] = "postgres"
            logger.info("PostgreSQL mode: connecting to Supabase")
            db_display = "PostgreSQL (Supabase)"
        except Exception as e:
            logger.error(f"Failed to build PostgreSQL URL: {e}")
            sys.exit(1)
    elif persona and persona.use_jsonl:
        # JSONL mode from persona (e.g., GOLDEN)
        repo_root = Path(__file__).parent.parent.parent
        jsonl_dir = repo_root / (persona.jsonl_data_dir or "data/release")
        if not jsonl_dir.exists():
            logger.error(f"JSONL data directory not found at {jsonl_dir}")
            sys.exit(1)
        os.environ["STORAGE_BACKEND"] = "jsonl"
        os.environ["JSONL_DATA_DIR"] = str(jsonl_dir)
        db_display = f"JSONL ({jsonl_dir})"
    elif os.environ.get("STORAGE_BACKEND") == "jsonl":
        # JSONL mode from environment
        jsonl_dir_env = os.environ.get("JSONL_DATA_DIR", "data/release")
        db_display = f"JSONL ({jsonl_dir_env})"
    else:
        # SQLite mode - validate database exists
        if not Path(Config.DB_PATH).exists():
            logger.error(f"Database not found at {Config.DB_PATH}")
            sys.exit(1)
        db_display = Config.DB_PATH

    logger.info("=" * 80)
    logger.info("BARSUKAS UNIFIED LAUNCHER")
    logger.info("=" * 80)
    if persona:
        logger.info(f"Persona: {persona.name.value.upper()} - {persona.description}")
    logger.info(f"Database: {db_display}")
    logger.info(f"Flask server will run on http://{args.host}:{args.port}")
    if args.readonly:
        logger.info("Mode: READ-ONLY")
    if not args.no_worker:
        logger.info(f"Task worker will poll every {args.poll_interval}s")
    else:
        logger.info("Task worker DISABLED")
    if persona and not persona.allow_api_keys:
        logger.info("API keys: DISABLED (no local keys)")
    if persona and not persona.allow_outbound_calls:
        logger.info("Outbound calls: LLM only (no external APIs)")
    logger.info("=" * 80)

    # Set up signal handlers for graceful shutdown
    # NOTE: Signal handlers must avoid I/O (including logging) because they can
    # interrupt the main thread mid-write, causing "reentrant call" errors.
    def handle_shutdown(signum: int, frame: Optional[types.FrameType]) -> None:
        STOP_EVENT.set()
        # Raise KeyboardInterrupt to break out of Flask's serve_forever loop
        # This will be caught by the try/except below
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    # Start the worker thread if enabled
    worker_thread = None
    if not args.no_worker:
        logger.info("Starting task worker thread...")
        worker_thread = threading.Thread(
            target=run_worker,
            args=(args.poll_interval,),
            name="BarsukasWorker",
            daemon=True,  # Worker will shut down when main thread exits
        )
        worker_thread.start()
        logger.info("Task worker thread started")

    # Run Flask server in the main thread
    # This blocks until the server is stopped (Ctrl+C or signal)
    try:
        run_flask_server(args.host, args.port, args.debug, args.readonly, persona)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
    finally:
        # Signal worker to stop
        STOP_EVENT.set()

        # Wait for worker thread to finish if it exists
        if worker_thread and worker_thread.is_alive():
            logger.info("Waiting for worker thread to finish...")
            worker_thread.join(timeout=5.0)
            if worker_thread.is_alive():
                logger.warning("Worker thread did not stop cleanly")

        logger.info("Barsukas shutdown complete")


if __name__ == "__main__":
    main()
