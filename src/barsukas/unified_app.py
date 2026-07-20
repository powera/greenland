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
from dataclasses import replace
from pathlib import Path
from typing import Any, Optional

from barsukas.config import Config
from barsukas.app import create_app
from barsukas.personas import (
    list_personas,
    PersonaConfig,
    PersonaName,
    resolve_persona,
)
from workqueue.worker import run_worker, STOP_EVENT
from barsukas.batch_poller import start_poller_thread as start_batch_poller_thread
from storage.backend.config import DataSourceConfig

logger = logging.getLogger(__name__)


def _load_wordfreq_in_background() -> None:
    """Populate the JSONL backend's in-memory DB with wordfreq data.

    Sleeps briefly so Flask can finish binding to its port before we start
    contending for the in-memory SQLite engine, then runs the loader. Any
    exception is logged but never propagated — the server stays up either
    way; golden mode just lacks frequency data until restart.
    """
    import time as _time

    try:
        _time.sleep(2.0)
        from storage.backend import create_session as _create_session
        from storage.backend.config import DataSourceConfig
        from storage.backend.factory import _jsonl_storage_cache
        from wordfreq.golden_loader import load_wordfreq_into_storage

        # Trigger storage cache population if it hasn't happened yet so we can
        # find the JSONLStorage instance to pass to the loader.
        _create_session(DataSourceConfig()).close()

        if not _jsonl_storage_cache:
            logger.warning("Golden loader: no JSONL storage instance found; skipping")
            return

        # The cache is keyed by data_dir; in golden mode there is exactly one.
        storage = next(iter(_jsonl_storage_cache.values()))
        logger.info("Golden loader: starting wordfreq load in background thread")
        load_wordfreq_into_storage(storage)
    except Exception:
        logger.exception("Golden loader: background wordfreq load failed")


def run_flask_server(
    host: str,
    port: int,
    debug: bool,
    readonly: bool,
    persona: PersonaConfig,
    db_url: Optional[str] = None,
    use_word2vec: bool = False,
) -> None:
    """Run the Flask server in the current thread.

    All persona-derived configuration is applied inside create_app(), which is
    the only code that knows whether the databases it asked for are actually
    reachable.
    """
    app = create_app(db_url=db_url, use_word2vec=use_word2vec, persona=persona)

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
        "--db-url",
        type=str,
        default=None,
        help=(
            "Main database URL (postgresql://user:pass@host:5432/db). Overrides the "
            "persona's main database. Does not affect the concepts database, which "
            "is always the global PostgreSQL."
        ),
    )
    parser.add_argument(
        "--use-word2vec",
        "--use_word2vec",
        dest="use_word2vec",
        action="store_true",
        help="Enable pgvector embedding read/write operations (opt-in)",
    )
    parser.add_argument(
        "--persona",
        type=str,
        choices=[p.value for p in PersonaName],
        help="Launch persona (default: local; or set BARSUKAS_PERSONA)",
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
            print(f"  {name:12} - {description}")
        sys.exit(0)

    # Resolve the persona. A launch with nothing selected is the LOCAL persona --
    # there is no unpersona'd path, so every setting has one definition.
    try:
        persona = resolve_persona(args.persona)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Apply persona overrides
    if persona.readonly:
        args.readonly = True
    if not persona.enable_worker:
        args.no_worker = True

    # Safety rule: read-only mode never starts the background worker.
    if args.readonly and not args.no_worker:
        logger.info("Read-only mode enabled: disabling task worker")
        args.no_worker = True

    # Set up logging. create_app() re-runs basicConfig(force=True) off
    # Config.DEBUG, which reads BARSUKAS_DEBUG from the environment -- so the
    # env var has to be set here or that call resets the level back to INFO
    # and --debug logs never emit.
    if args.debug:
        os.environ["BARSUKAS_DEBUG"] = "true"
        Config.DEBUG = True

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(name)s - %(filename)s:%(lineno)d - %(message)s",
        force=True,
    )

    if args.use_word2vec:
        os.environ["USE_WORD2VEC"] = "true"

    # Resolve the main database. create_app() and run_worker() take the persona
    # object itself; nothing is exported to the environment.
    repo_root = Path(__file__).parent.parent.parent

    main_postgres_url: Optional[str] = args.db_url
    if main_postgres_url:
        logger.info("Main database overridden by --db-url")
    elif persona.use_postgres:
        try:
            main_postgres_url = DataSourceConfig.build_postgres_url()
            logger.info("PostgreSQL mode: connecting to Supabase")
        except Exception as e:
            logger.warning(f"PostgreSQL credentials not available ({e}), falling back to SQLite")
            # Fall back to a SQLite main DB by pretending the persona asked for it.
            persona = replace(persona, use_postgres=False)

    if persona.use_jsonl:
        jsonl_dir = repo_root / (persona.jsonl_data_dir or "data/release")
        if not jsonl_dir.exists():
            logger.error(f"JSONL data directory not found at {jsonl_dir}")
            sys.exit(1)
        db_display = f"JSONL ({jsonl_dir})"
    elif main_postgres_url:
        db_display = "PostgreSQL (Supabase)"
    else:
        # SQLite mode - validate database exists
        if not Path(Config.DB_PATH).exists():
            logger.error(f"Database not found at {Config.DB_PATH}")
            sys.exit(1)
        db_display = Config.DB_PATH

    logger.info("=" * 80)
    logger.info("BARSUKAS UNIFIED LAUNCHER")
    logger.info("=" * 80)
    logger.info(f"Persona: {persona.name.value.upper()} - {persona.description}")
    # Name both databases: which concepts you are looking at is exactly the
    # question this banner needs to answer.
    logger.info(f"Main database:     {db_display}")
    if persona.use_postgres_concepts:
        access = "read-only" if persona.postgres_concepts_readonly else "writable"
        logger.info(f"Concepts database: PostgreSQL ({access})")
    else:
        logger.info(f"Concepts database: same as main ({db_display})")
    logger.info(f"Flask server will run on http://{args.host}:{args.port}")
    if args.readonly:
        logger.info("Mode: READ-ONLY")
    if not args.no_worker:
        logger.info(f"Task worker will poll every {args.poll_interval}s")
    else:
        logger.info("Task worker DISABLED")
    if not persona.allow_api_keys:
        logger.info("API keys: DISABLED (no local keys)")
    if not persona.allow_outbound_calls:
        logger.info("Outbound calls: LLM only (no external APIs)")
    logger.info("Word2Vec/pgvector: %s", "ENABLED" if args.use_word2vec else "DISABLED")
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

    # In golden/hosted mode (JSONL backend), populate the in-memory wordfreq
    # tables in a background thread so Flask can start serving immediately.
    if persona.use_jsonl:
        threading.Thread(
            target=_load_wordfreq_in_background,
            name="GoldenWordfreqLoader",
            daemon=True,
        ).start()

    # Start the worker thread if enabled
    worker_thread = None
    batch_poller_thread = None
    if not args.no_worker:
        logger.info("Starting task worker thread...")
        worker_thread = threading.Thread(
            target=run_worker,
            args=(args.poll_interval, persona),
            name="BarsukasWorker",
            daemon=True,  # Worker will shut down when main thread exits
        )
        worker_thread.start()
        logger.info("Task worker thread started")

        # Periodic poller for OpenAI Batch jobs submitted by Barsukas
        # (sentence decomposition). Checks every 5 minutes and applies any
        # completed batches to the main DB.
        from storage.backend import create_session as _create_main_session
        from storage.backend.config import BackendType as _BackendType
        from storage.backend.config import DataSourceConfig as _DataSourceConfig

        # Build the poller's config from the resolved persona directly; the
        # environment is not consulted.
        if main_postgres_url:
            _poller_config = _DataSourceConfig(
                backend_type=_BackendType.POSTGRES, postgres_url=main_postgres_url
            )
        elif persona.use_jsonl:
            _poller_config = _DataSourceConfig(
                backend_type=_BackendType.JSONL,
                jsonl_data_dir=str(repo_root / (persona.jsonl_data_dir or "data/release")),
            )
        else:
            _poller_config = _DataSourceConfig(
                backend_type=_BackendType.SQLITE, sqlite_path=Config.DB_PATH
            )

        def _main_session_factory() -> Any:
            return _create_main_session(_poller_config)

        logger.info("Starting batch poller thread (5-minute interval)...")
        batch_poller_thread = start_batch_poller_thread(_main_session_factory, STOP_EVENT)
        logger.info("Batch poller thread started")

    # Run Flask server in the main thread
    # This blocks until the server is stopped (Ctrl+C or signal)
    try:
        run_flask_server(
            args.host,
            args.port,
            args.debug,
            args.readonly,
            persona,
            db_url=args.db_url,
            use_word2vec=args.use_word2vec,
        )
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

        # Wait for batch poller thread to finish if it exists
        if batch_poller_thread and batch_poller_thread.is_alive():
            logger.info("Waiting for batch poller thread to finish...")
            batch_poller_thread.join(timeout=5.0)
            if batch_poller_thread.is_alive():
                logger.warning("Batch poller thread did not stop cleanly")

        logger.info("Barsukas shutdown complete")


if __name__ == "__main__":
    main()
