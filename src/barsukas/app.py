#!/usr/bin/python3

"""
Barsukas - Word Frequency Database Web Editor

A lightweight Flask web interface for manual edits to lemmas, translations,
and difficulty levels in the linguistics database.
"""

import sys
import argparse
from pathlib import Path

from flask import Flask, render_template, g

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
    rapid_review,
    settings,
)
from wordfreq.storage.backend import create_session, get_backend_type
from wordfreq.storage.backend.config import BackendConfig, BackendType
from pinyin_helper import generate_pinyin, generate_pinyin_ruby_html, is_chinese


def create_app(config_class=Config):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Set up storage backend
    backend_type = get_backend_type()
    print(f"Using storage backend: {backend_type.value}")

    if backend_type == BackendType.SQLITE:
        db_path = app.config["DB_PATH"]
        if not Path(db_path).exists():
            print(f"Error: Database not found at {db_path}", file=sys.stderr)
            sys.exit(1)
        backend_config = BackendConfig(backend_type=BackendType.SQLITE, sqlite_path=db_path)
    else:
        # JSONL backend
        backend_config = BackendConfig.from_env()

    # Store backend config in app
    app.backend_config = backend_config

    # Create a session factory function that returns new sessions
    def session_factory():
        return create_session(backend_config)

    app.db_session_factory = session_factory

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
    app.register_blueprint(rapid_review.bp)
    app.register_blueprint(settings.bp)

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
        from wordfreq.storage.backend.models import get_lemma_model, get_sentence_model

        Lemma = get_lemma_model()
        Sentence = get_sentence_model()

        # Get some basic stats
        total_lemmas = g.db.query(Lemma).count()
        verified_lemmas = g.db.query(Lemma).filter_by(verified=True).count()
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
