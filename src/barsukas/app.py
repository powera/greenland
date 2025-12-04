#!/usr/bin/python3

"""
Barsukas - Word Frequency Database Web Editor

A lightweight Flask web interface for manual edits to lemmas, translations,
and difficulty levels in the linguistics database.
"""

import sys
import argparse
import logging
from pathlib import Path

from flask import Flask, render_template, g
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

logger = logging.getLogger(__name__)

from config import Config
from routes import (
    lemmas,
    translations,
    overrides,
    agents,
    operation_logs,
    wireword,
    api,
    agents_launcher,
    exports,
    sentences,
    audio,
)
from wordfreq.storage.utils.session import ensure_tables_exist
from wordfreq.storage.utils.database_url import get_database_url, get_engine_options, is_sqlite
from pinyin_helper import generate_pinyin, generate_pinyin_ruby_html, is_chinese


def create_app(config_class=Config):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Set up database - support both DATABASE_URL and DB_PATH
    # DATABASE_URL takes precedence for cloud databases
    if app.config.get("DATABASE_URL"):
        db_url = app.config["DATABASE_URL"]
        logger.info(f"Using DATABASE_URL for cloud database connection")
    else:
        # Fall back to SQLite file path
        db_path = app.config["DB_PATH"]
        if not Path(db_path).exists():
            print(f"Error: Database not found at {db_path}", file=sys.stderr)
            sys.exit(1)
        db_url = get_database_url(db_path)
        logger.info(f"Using SQLite database at {db_path}")

    # Get database-specific engine options
    url, connect_args = get_engine_options(db_url, echo=app.config["DEBUG"])

    # Create engine and session factory
    engine = create_engine(url, echo=app.config["DEBUG"], connect_args=connect_args)
    app.db_session_factory = scoped_session(sessionmaker(bind=engine))

    # Ensure all tables exist (creates missing tables and columns)
    with app.db_session_factory() as session:
        ensure_tables_exist(session)

    # Register blueprints
    app.register_blueprint(lemmas.bp)
    app.register_blueprint(sentences.bp)
    app.register_blueprint(translations.bp)
    app.register_blueprint(overrides.bp)
    app.register_blueprint(agents.bp)
    app.register_blueprint(agents_launcher.bp)
    app.register_blueprint(operation_logs.bp)
    app.register_blueprint(wireword.bp)
    app.register_blueprint(exports.bp)
    app.register_blueprint(api.bp)
    app.register_blueprint(audio.bp)

    # Register Jinja2 filters for Pinyin
    app.jinja_env.filters["pinyin"] = generate_pinyin
    app.jinja_env.filters["pinyin_ruby"] = generate_pinyin_ruby_html
    app.jinja_env.filters["is_chinese"] = is_chinese

    # Register JSON filter for parsing JSON strings in templates
    import json

    app.jinja_env.filters["fromjson"] = json.loads

    @app.before_request
    def before_request():
        """Set up database session for each request."""
        g.db = app.db_session_factory()

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        """Clean up database session after request."""
        db = g.pop("db", None)
        if db is not None:
            if exception:
                db.rollback()
            else:
                db.commit()
            db.close()

    @app.route("/")
    def index():
        """Home page with search and quick stats."""
        from wordfreq.storage.models.schema import Lemma, Sentence

        # Get some basic stats
        total_lemmas = g.db.query(Lemma).count()
        verified_lemmas = g.db.query(Lemma).filter(Lemma.verified == True).count()
        with_difficulty = g.db.query(Lemma).filter(Lemma.difficulty_level != None).count()
        total_sentences = g.db.query(Sentence).count()

        return render_template(
            "index.html",
            total_lemmas=total_lemmas,
            verified_lemmas=verified_lemmas,
            with_difficulty=with_difficulty,
            total_sentences=total_sentences,
        )

    @app.context_processor
    def utility_processor():
        """Add utility functions to Jinja templates."""
        return {"config": app.config}

    return app


def main():
    """Run the Flask development server."""
    parser = argparse.ArgumentParser(description="Barsukas Web Interface")
    parser.add_argument(
        "--port", type=int, default=Config.PORT, help=f"Port to run on (default: {Config.PORT})"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument(
        "--readonly", action="store_true", help="Run in read-only mode (no edits allowed)"
    )
    args = parser.parse_args()

    app = create_app()

    if args.debug:
        app.config["DEBUG"] = True

    if args.readonly:
        app.config["READONLY"] = True

    print(f"Starting Barsukas on http://{Config.HOST}:{args.port}")
    print(f"Database: {app.config['DB_PATH']}")
    if args.readonly:
        print("Running in READ-ONLY mode - no edits allowed")
    print(f"Press Ctrl+C to stop")

    app.run(host=Config.HOST, port=args.port, debug=app.config["DEBUG"])


if __name__ == "__main__":
    main()
