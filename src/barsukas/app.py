#!/usr/bin/python3

"""
Barsukas - Word Frequency Database Web Editor

A lightweight Flask web interface for manual edits to lemmas, translations,
and difficulty levels in the linguistics database.
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from config import Config
from flask import Flask, g, render_template
from pinyin_helper import generate_pinyin, generate_pinyin_ruby_html, is_chinese
from routes import (
    agents,
    agents_launcher,
    api,
    audio,
    exports,
    lemmas,
    operation_logs,
    overrides,
    pattern_sentences,
    rapid_review,
    sentences,
    settings,
    translations,
    wireword,
)

from wordfreq.storage.backend import create_session, get_backend_type
from wordfreq.storage.backend.config import BackendType, DataSourceConfig


def create_app(config_class: type[Config] = Config) -> Flask:
    """Create and configure the Flask application."""
    logging.basicConfig(
        level=logging.DEBUG if config_class.DEBUG else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(filename)s:%(lineno)d - %(message)s",
        force=True,
    )

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
        backend_config = DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=db_path)
    else:
        # JSONL backend
        backend_config = DataSourceConfig.from_env()

    # Store backend config in app
    app.backend_config = backend_config

    # Create a session factory function that returns new sessions
    def session_factory() -> Any:
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
    app.register_blueprint(pattern_sentences.bp)

    # Register Jinja2 filters for Pinyin
    app.jinja_env.filters["pinyin"] = generate_pinyin
    app.jinja_env.filters["pinyin_ruby"] = generate_pinyin_ruby_html
    app.jinja_env.filters["is_chinese"] = is_chinese

    # Register JSON filter for parsing JSON strings in templates
    app.jinja_env.filters["fromjson"] = json.loads

    # Register filter to extract grammatical case from grammatical_form
    def extract_case(grammatical_form: Optional[str]) -> Optional[str]:
        """Extract case from grammatical_form string.

        For Lithuanian/German, grammatical_form includes case like:
        'noun/lt_nominative_singular' -> 'nominative'
        'noun/de_accusative_plural' -> 'accusative'

        Returns None if no case found.
        """
        if not grammatical_form or "/" not in grammatical_form:
            return None

        # Split to get the details part (e.g., "lt_nominative_singular")
        parts = grammatical_form.split("/")
        if len(parts) < 2:
            return None

        details = parts[1]  # e.g., "lt_nominative_singular"

        # Known grammatical cases
        cases = [
            "nominative",
            "accusative",
            "genitive",
            "dative",
            "instrumental",
            "locative",
            "vocative",
        ]

        for case in cases:
            if case in details:
                return case

        return None

    app.jinja_env.filters["extract_case"] = extract_case

    @app.before_request
    def before_request() -> None:
        """Set up database session for each request."""
        g.db = app.db_session_factory()

    @app.teardown_appcontext
    def shutdown_session(exception: Optional[Exception] = None) -> None:
        """Clean up database session after request."""
        db = g.pop("db", None)
        if db is not None:
            if exception:
                db.rollback()
            else:
                db.commit()
            db.close()

    @app.route("/")
    def index() -> Any:
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
    def utility_processor() -> Dict[str, Any]:
        """Add utility functions to Jinja templates."""
        return {"config": app.config}

    return app


def main() -> None:
    """Run the Flask development server."""
    parser = argparse.ArgumentParser(description="Barsukas Web Interface")
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
    args = parser.parse_args()

    app = create_app()

    if args.debug:
        app.config["DEBUG"] = True

    if args.readonly:
        app.config["READONLY"] = True

    print(f"Starting Barsukas on http://{args.host}:{args.port}")
    print(f"Database: {app.config['DB_PATH']}")
    if args.readonly:
        print("Running in READ-ONLY mode - no edits allowed")
    print(f"Press Ctrl+C to stop")

    app.run(host=args.host, port=args.port, debug=app.config["DEBUG"])


if __name__ == "__main__":
    main()
