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

# Add src to path if not already present
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from benchmarks.server.config import Config
from flask import Flask, g, redirect, render_template, url_for

from benchmarks.datastore.common import create_database_and_session
from benchmarks.server.benchmark_worker import BenchmarkRunWorker


def create_app(config_class=Config):
    """Create and configure the Flask application."""
    logging.basicConfig(
        level=logging.DEBUG if config_class.DEBUG else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(filename)s:%(lineno)d - %(message)s",
        force=True,
    )

    app = Flask(__name__)
    app.config.from_object(config_class)
    app.json.ensure_ascii = False

    # Verify database exists
    db_path = app.config["DB_PATH"]
    if not Path(db_path).exists():
        print(f"Error: Database not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    # Store database path in app config
    app.db_path = db_path

    # Create a session factory function that returns new sessions
    def session_factory():
        return create_database_and_session(str(app.db_path))

    app.db_session_factory = session_factory
    app.extensions["benchmark_run_worker"] = BenchmarkRunWorker()

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
    parser.add_argument("--db-path", help="Path to benchmarks database")

    args = parser.parse_args()

    # Update config based on args
    if args.db_path:
        Config.DB_PATH = args.db_path
    if args.debug:
        Config.DEBUG = True

    # Create app
    app = create_app(Config)

    # Run server
    print(f"Starting Benchmark Server on {args.host}:{args.port}")
    print(f"Using database: {app.db_path}")
    print(f"Visit http://{args.host}:{args.port} in your browser")

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
