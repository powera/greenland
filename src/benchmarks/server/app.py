#!/usr/bin/python3

"""
Benchmark Server - Web interface for LLM benchmark management and visualization

A Flask web application for running benchmarks, viewing results, and comparing
model performance across various tasks.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

# Add src to path if not already present
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from benchmarks.server.config import Config
from flask import Flask, g, redirect, render_template, url_for

from benchmarks.config import BenchmarkConfig
from benchmarks.datastore.common import create_database_and_session, create_postgres_session
from benchmarks.server.benchmark_worker import BenchmarkRunWorker


def create_app(config_class=Config, postgres_url: Optional[str] = None):
    """Create and configure the Flask application.

    Args:
        config_class: Configuration class to use
        postgres_url: Optional PostgreSQL URL; when provided, uses the Supabase
            backend instead of the local SQLite file.
    """
    logging.basicConfig(
        level=logging.DEBUG if config_class.DEBUG else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(filename)s:%(lineno)d - %(message)s",
        force=True,
    )

    app = Flask(__name__)
    app.config.from_object(config_class)
    app.json.ensure_ascii = False

    # Resolve postgres URL: prefer explicit arg, then env-based config class setting.
    resolved_postgres_url: Optional[str] = postgres_url
    if not resolved_postgres_url and config_class.STORAGE_BACKEND == "postgres":
        resolved_postgres_url = config_class.POSTGRES_URL or None
        if not resolved_postgres_url:
            try:
                resolved_postgres_url = BenchmarkConfig.build_postgres_url()
            except Exception as exc:
                print(f"Error building PostgreSQL URL: {exc}", file=sys.stderr)
                sys.exit(1)

    if resolved_postgres_url:
        print("Using storage backend: postgres (Supabase)")
        app.config["DB_PATH"] = "PostgreSQL (Supabase)"
        app.config["USING_POSTGRES"] = True

        def session_factory():
            return create_postgres_session(resolved_postgres_url)  # type: ignore[arg-type]

    else:
        # SQLite backend — verify the database file exists.
        db_path = app.config["DB_PATH"]
        if not Path(db_path).exists():
            print(f"Error: Database not found at {db_path}", file=sys.stderr)
            sys.exit(1)

        print(f"Using storage backend: sqlite ({db_path})")
        app.config["USING_POSTGRES"] = False

        def session_factory():
            return create_database_and_session(str(app.config["DB_PATH"]))

    app.db_session_factory = session_factory
    app.extensions["benchmark_run_worker"] = BenchmarkRunWorker()

    @app.context_processor
    def inject_worker_status():
        """Expose benchmark worker status globally (navbar indicators, etc.)."""
        worker = app.extensions.get("benchmark_run_worker")
        return {"navbar_worker_status": worker.status() if worker else None}

    # Request handling
    @app.before_request
    def before_request():
        """Set up database session before each request."""
        g.db = app.db_session_factory()

    @app.teardown_appcontext
    def teardown_db(exception=None):
        """Close database session after each request."""
        db = g.pop("db", None)
        if db is not None:
            db.close()

    # Register blueprints
    from benchmarks.server.routes import benchmarks, dashboard, models, runs, verbalator

    app.register_blueprint(dashboard.bp)
    app.register_blueprint(benchmarks.bp)
    app.register_blueprint(models.bp)
    app.register_blueprint(runs.bp)
    app.register_blueprint(verbalator.bp)

    # Register Jinja2 filters
    import json

    app.jinja_env.filters["fromjson"] = json.loads

    # Root redirect
    @app.route("/")
    def index():
        """Redirect root to dashboard."""
        return redirect(url_for("dashboard.index"))

    return app


def main():
    """Run the Flask development server."""
    parser = argparse.ArgumentParser(description="Benchmark Server - LLM Benchmark Management")
    parser.add_argument("--host", default=Config.HOST, help="Host to bind to")
    parser.add_argument("--port", type=int, default=Config.PORT, help="Port to bind to")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--db-path", help="Path to benchmarks SQLite database")
    parser.add_argument(
        "--postgres",
        action="store_true",
        help="Use PostgreSQL (Supabase) backend; reads keys/postgres.key",
    )
    parser.add_argument(
        "--db-url",
        help="Full PostgreSQL connection URL (overrides --postgres key-file lookup)",
    )

    args = parser.parse_args()

    # Update config based on args
    if args.db_path:
        Config.DB_PATH = args.db_path
    if args.debug:
        Config.DEBUG = True

    # Determine postgres URL from CLI args
    cli_postgres_url: Optional[str] = None
    if args.db_url and args.db_url.startswith("postgresql://"):
        cli_postgres_url = args.db_url
    elif args.postgres:
        Config.STORAGE_BACKEND = "postgres"

    # Create app
    app = create_app(Config, postgres_url=cli_postgres_url)

    # Run server
    db_display = app.config["DB_PATH"]
    print(f"Starting Benchmark Server on {args.host}:{args.port}")
    print(f"Using database: {db_display}")
    print(f"Visit http://{args.host}:{args.port} in your browser")

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
