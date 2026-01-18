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

from config import Config
from app import create_app
from workers.task_worker import run_worker, STOP_EVENT
from wordfreq.storage.backend.config import DataSourceConfig

logger = logging.getLogger(__name__)


def run_flask_server(host: str, port: int, debug: bool, readonly: bool) -> None:
    """Run the Flask server in the current thread."""
    app = create_app()

    if debug:
        app.config["DEBUG"] = True

    if readonly:
        app.config["READONLY"] = True

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
    args = parser.parse_args()

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
    else:
        # SQLite mode - validate database exists
        if not Path(Config.DB_PATH).exists():
            logger.error(f"Database not found at {Config.DB_PATH}")
            sys.exit(1)
        db_display = Config.DB_PATH

    logger.info("=" * 80)
    logger.info("BARSUKAS UNIFIED LAUNCHER")
    logger.info("=" * 80)
    logger.info(f"Database: {db_display}")
    logger.info(f"Flask server will run on http://{args.host}:{args.port}")
    if not args.no_worker:
        logger.info(f"Task worker will poll every {args.poll_interval}s")
    else:
        logger.info("Task worker DISABLED")
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
        run_flask_server(args.host, args.port, args.debug, args.readonly)
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
