#!/usr/bin/python3

"""
Barsukas - Word Frequency Database Web Editor

A lightweight Flask web interface for manual edits to lemmas, translations,
and difficulty levels in the linguistics database.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional, cast

from barsukas.config import Config
from barsukas.helpers.strings import (
    SUPPORTED_UI_LANGS,
    create_cstr_accessor,
    create_lstr_accessor,
    create_sstr_accessor,
    load_all_barsukas_cstr_strings,
    load_all_barsukas_strings,
)
from barsukas.helpers.ui_language import (
    UI_LANGUAGE_COOKIE,
    normalize_ui_language,
    resolve_ui_language,
)
from flask import Flask, Response, g, redirect, render_template, request, url_for
from barsukas.metrics import (
    RequestMetricsMiddleware,
    get_metrics_output,
    instrument_sqlalchemy_engine,
    record_llm_call,
    set_server_mode_metrics,
)
from sqlalchemy.orm import Session

from langtools.ja.romaji_helper import (
    generate_romaji,
    generate_romaji_ruby_html,
    is_japanese,
)
from langtools.zh.pinyin_helper import (
    generate_pinyin,
    generate_pinyin_ruby_html,
    is_chinese,
)
from barsukas.routes import (
    admin,
    agents,
    agents_launcher,
    api,
    api_client,
    audio,
    barsukas_tasks,
    batch_operations,
    bebras,
    categories,
    completeness,
    conversations,
    exports,
    lemmas,
    llm_api,
    operation_logs,
    overrides,
    pattern_sentences,
    peleda,
    pending_imports,
    pradzia,
    rhymes,
    sentence_stats,
    sentences,
    settings,
    strings_export,
    trakaido,
    translations,
    wireword,
)
from barsukas.routes.review import rapid_review, rapid_review_hub, sentence_rapid_review
from barsukas.routes.sync import (
    sync_derivative_release,
    sync_hub,
    sync_relation_release,
    sync_release,
    sync_sentence_release,
    sync_synonym_release,
)
from storage.backend import create_session, get_backend_type
from storage.backend.config import BackendType, DataSourceConfig


class BarsukasFlask(Flask):
    """Custom Flask subclass with typed custom attributes."""

    backend_config: DataSourceConfig
    db_session_factory: Callable[[], Session]
    bench_db_session_factory: Optional[Callable[[], Session]]


def create_app(
    config_class: type[Config] = Config,
    db_url: Optional[str] = None,
    use_word2vec: bool = False,
) -> BarsukasFlask:
    """Create and configure the Flask application.

    Args:
        config_class: Configuration class to use
        db_url: Optional database URL (for PostgreSQL: postgresql://user:pass@host:5432/db)
    """
    logging.basicConfig(
        level=logging.DEBUG if config_class.DEBUG else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(filename)s:%(lineno)d - %(message)s",
        force=True,
    )

    app = BarsukasFlask(__name__)
    app.config.from_object(config_class)
    if use_word2vec:
        os.environ["USE_WORD2VEC"] = "true"

    # Set up storage backend
    postgres_url = db_url if db_url and db_url.startswith("postgresql://") else None

    # Check for env-based postgres configuration
    if not postgres_url and os.environ.get("STORAGE_BACKEND") == "postgres":
        postgres_url = os.environ.get("POSTGRES_URL")
        if not postgres_url:
            # Build from template + key
            try:
                postgres_url = DataSourceConfig.build_postgres_url()
            except Exception as e:
                print(f"Error building PostgreSQL URL: {e}", file=sys.stderr)
                sys.exit(1)

    if postgres_url:
        # PostgreSQL backend
        print("Using storage backend: postgres")
        backend_config = DataSourceConfig(
            backend_type=BackendType.POSTGRES,
            postgres_url=postgres_url,
            use_word2vec=use_word2vec,
        )
        app.config["DB_PATH"] = "PostgreSQL (Supabase)"  # For display
        app.config["USING_POSTGRES"] = True
    else:
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

        app.config["USING_POSTGRES"] = False

    # Store backend config in app
    app.backend_config = backend_config
    app.config["SERVER_MODE"] = "readwrite"

    set_server_mode_metrics(
        server_mode=app.config["SERVER_MODE"],
        backend=backend_config.backend_type.value,
        readonly=bool(app.config.get("READONLY", False)),
        debug=bool(app.config.get("DEBUG", False)),
    )

    # Register LLM metrics callback so unified_client reports metrics
    try:
        from clients.unified_client import set_llm_metrics_callback

        set_llm_metrics_callback(record_llm_call)
    except ImportError:
        # clients module may not be available in all configurations
        pass

    # Create a session factory function that returns new sessions
    def session_factory() -> Session:
        return cast(Session, create_session(backend_config))

    app.db_session_factory = session_factory
    try:
        probe_session = app.db_session_factory()
        engine = probe_session.get_bind()
        if engine is not None:
            instrument_sqlalchemy_engine(engine)
    except Exception as setup_error:
        logging.getLogger(__name__).warning(
            "Failed to enable SQLAlchemy metrics auto-instrumentation: %s",
            setup_error,
        )
    finally:
        if "probe_session" in locals():
            probe_session.close()

    # Register blueprints
    app.register_blueprint(lemmas.bp)
    app.register_blueprint(sentences.bp)
    app.register_blueprint(sentence_rapid_review.bp)
    app.register_blueprint(sentence_stats.bp)
    app.register_blueprint(conversations.bp)
    app.register_blueprint(categories.bp)
    app.register_blueprint(completeness.bp)
    app.register_blueprint(translations.bp)
    app.register_blueprint(overrides.bp)
    app.register_blueprint(agents.bp)
    app.register_blueprint(agents_launcher.bp)
    app.register_blueprint(operation_logs.bp)
    app.register_blueprint(pending_imports.bp)
    app.register_blueprint(batch_operations.bp)
    app.register_blueprint(barsukas_tasks.bp)
    app.register_blueprint(bebras.bp)
    app.register_blueprint(wireword.bp)
    app.register_blueprint(exports.bp)
    app.register_blueprint(api.bp)
    app.register_blueprint(llm_api.bp)
    app.register_blueprint(api_client.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(audio.bp)
    app.register_blueprint(rapid_review.bp)
    app.register_blueprint(rapid_review_hub.bp)
    app.register_blueprint(settings.bp)
    app.register_blueprint(strings_export.bp)
    app.register_blueprint(trakaido.bp)
    app.register_blueprint(pattern_sentences.bp)
    app.register_blueprint(peleda.bp)
    app.register_blueprint(rhymes.bp)
    app.register_blueprint(pradzia.bp)
    app.register_blueprint(sync_hub.bp)
    app.register_blueprint(sync_release.bp)
    app.register_blueprint(sync_relation_release.bp)
    app.register_blueprint(sync_sentence_release.bp)
    app.register_blueprint(sync_derivative_release.bp)
    app.register_blueprint(sync_synonym_release.bp)

    # --- Benchmarks integration ---
    # Barsukas always uses PostgreSQL to access the benchmarks schema.
    # The benchmarks section is only enabled when the postgres URL can be built.
    bench_postgres_url: Optional[str] = None
    try:
        from benchmarks.config import BenchmarkConfig

        bench_postgres_url = BenchmarkConfig.build_postgres_url()
    except Exception as bench_exc:
        print(f"Benchmarks DB not available, section disabled: {bench_exc}", file=sys.stderr)

    if bench_postgres_url:
        from benchmarks.datastore.common import create_postgres_session
        from benchmarks.server.benchmark_worker import BenchmarkRunWorker
        from benchmarks.server.config import Config as BenchmarkServerConfig
        from benchmarks.server.routes import benchmarks as bench_benchmarks
        from benchmarks.server.routes import dashboard as bench_dashboard
        from benchmarks.server.routes import models as bench_models
        from benchmarks.server.routes import runs as bench_runs

        # Capture url in closure
        _bench_postgres_url: str = bench_postgres_url

        def bench_session_factory() -> Session:
            return cast(Session, create_postgres_session(_bench_postgres_url))

        app.bench_db_session_factory = bench_session_factory
        app.extensions["benchmark_run_worker"] = BenchmarkRunWorker()
        app.config["BENCHMARKS_ENABLED"] = True

        # Copy runner access-control config from the benchmarks server Config so
        # _is_authorized_run_request() works correctly in Barsukas.  Without these
        # keys, BENCHMARK_RUNNER_ALLOWED_CIDRS defaults to () and the run/sync/
        # cancel endpoints are always blocked even in non-readonly personas.
        app.config["BENCHMARK_RUNNER_ENABLED"] = BenchmarkServerConfig.BENCHMARK_RUNNER_ENABLED
        app.config["BENCHMARK_RUNNER_ALLOWED_CIDRS"] = (
            BenchmarkServerConfig.BENCHMARK_RUNNER_ALLOWED_CIDRS
        )
        app.config["BENCHMARK_RUNNER_BLOCK_PROXIED_REQUESTS"] = (
            BenchmarkServerConfig.BENCHMARK_RUNNER_BLOCK_PROXIED_REQUESTS
        )

        # Benchmarks blueprints, all nested under /benchmarks/
        # bench_benchmarks.bp already has url_prefix="/benchmarks"
        app.register_blueprint(bench_benchmarks.bp)
        app.register_blueprint(bench_dashboard.bp, url_prefix="/benchmarks/dashboard")
        app.register_blueprint(bench_models.bp, url_prefix="/benchmarks/models")
        app.register_blueprint(bench_runs.bp, url_prefix="/benchmarks/runs")

        @app.before_request
        def before_bench_request() -> None:
            """Set up benchmarks database session."""
            g.bench_db = bench_session_factory()

        @app.teardown_appcontext
        def shutdown_bench_session(exception: Optional[BaseException]) -> None:
            """Clean up benchmarks database session."""
            bench_db = g.pop("bench_db", None)
            if bench_db is not None:
                bench_db.close()

        @app.context_processor
        def inject_bench_worker_status() -> Dict[str, Any]:
            """Expose benchmark worker status to templates (navbar queue indicator)."""
            worker = app.extensions.get("benchmark_run_worker")
            return {"navbar_worker_status": worker.status() if worker else None}

    else:
        app.config["BENCHMARKS_ENABLED"] = False

    # Register Jinja2 filters for Pinyin (Chinese) and Romaji (Japanese)
    app.jinja_env.filters["pinyin"] = generate_pinyin
    app.jinja_env.filters["pinyin_ruby"] = generate_pinyin_ruby_html
    app.jinja_env.filters["is_chinese"] = is_chinese
    app.jinja_env.filters["romaji"] = generate_romaji
    app.jinja_env.filters["romaji_ruby"] = generate_romaji_ruby_html
    app.jinja_env.filters["is_japanese"] = is_japanese

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
        """Set up database session and start request timing for metrics."""
        g.db = app.db_session_factory()
        g.ui_lang = resolve_ui_language(request)
        endpoint_name = request.endpoint or "common"
        g.strings_default_module = endpoint_name.split(".", 1)[0]
        RequestMetricsMiddleware.before_request()

    @app.teardown_appcontext
    def shutdown_session(exception: Optional[BaseException]) -> None:
        """Clean up database session after request."""
        db = g.pop("db", None)
        if db is not None:
            if exception:
                db.rollback()
            else:
                db.commit()
            db.close()

    @app.after_request
    def after_request(response: Response) -> Response:
        """Record request metrics after response is generated."""
        selected_ui_lang = getattr(g, "set_ui_lang_cookie", None)
        if selected_ui_lang:
            response.set_cookie(
                UI_LANGUAGE_COOKIE,
                selected_ui_lang,
                max_age=60 * 60 * 24 * 365,
                samesite="Lax",
            )
        return cast(Response, RequestMetricsMiddleware.after_request(response))

    @app.post("/ui-language")
    def set_ui_language() -> Any:
        """Persist UI language selection in a cookie, then return to the target page."""
        selected_ui_lang = normalize_ui_language(request.form.get("ui_lang")) or "en"
        g.set_ui_lang_cookie = selected_ui_lang
        next_url = request.form.get("next_url", "").strip()
        if not next_url.startswith("/"):
            next_url = url_for("index")
        return redirect(next_url)

    @app.route("/metrics")
    def metrics() -> Response:
        """Expose Prometheus metrics endpoint."""
        backend_type = app.backend_config.backend_type.value
        readonly = bool(app.config.get("READONLY", False))
        debug = bool(app.config.get("DEBUG", False))
        server_mode = "readonly" if readonly else "readwrite"

        set_server_mode_metrics(
            server_mode=server_mode,
            backend=backend_type,
            readonly=readonly,
            debug=debug,
        )

        return Response(get_metrics_output(), mimetype="text/plain; charset=utf-8")

    @app.route("/")
    def index() -> Any:
        """Home page with search and quick stats."""
        from barsukas.helpers.db_optimization import get_home_page_stats

        # Get stats in a single optimized query (replaces 4 separate COUNT queries)
        stats = get_home_page_stats(g.db)

        return render_template(
            "index.html",
            total_lemmas=stats["total_lemmas"],
            verified_lemmas=stats["verified_lemmas"],
            with_difficulty=stats["with_difficulty"],
            total_sentences=stats["total_sentences"],
        )

    @app.route("/ipa-reference")
    def ipa_reference() -> Any:
        """Static IPA reference page for pronunciation symbols."""
        return render_template("ipa_reference.html")

    @app.context_processor
    def utility_processor() -> Dict[str, Any]:
        """Add utility values to Jinja templates."""
        ui_lang = getattr(g, "ui_lang", "en")
        strings_by_namespace = load_all_barsukas_strings(ui_lang)
        cstr_by_namespace = load_all_barsukas_cstr_strings(ui_lang)
        default_module = getattr(g, "strings_default_module", "common")
        lstr = create_lstr_accessor(strings_by_namespace, default_module=default_module)
        sstr = create_sstr_accessor(strings_by_namespace, default_module=default_module)
        cstr = create_cstr_accessor(cstr_by_namespace, default_module=default_module)

        return {
            "config": app.config,
            "UI_LANG": ui_lang,
            "SUPPORTED_UI_LANGS": sorted(SUPPORTED_UI_LANGS),
            "STRINGS": strings_by_namespace,
            "LSTR": lstr,
            "SSTR": sstr,
            "CSTR": cstr,
        }

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
    parser.add_argument(
        "--db-url",
        type=str,
        help="PostgreSQL connection URL (e.g., postgresql://user:pass@host:5432/dbname)",
    )
    parser.add_argument(
        "--use-word2vec",
        "--use_word2vec",
        dest="use_word2vec",
        action="store_true",
        help="Enable pgvector embedding read/write operations (opt-in)",
    )
    args = parser.parse_args()

    app = create_app(db_url=args.db_url, use_word2vec=args.use_word2vec)

    if args.debug:
        app.config["DEBUG"] = True

    if args.readonly:
        app.config["READONLY"] = True

    print(f"Starting Barsukas on http://{args.host}:{args.port}")
    print(f"Database: {app.config['DB_PATH']}")
    print(f"Word2Vec/pgvector: {'ENABLED' if args.use_word2vec else 'DISABLED'}")
    if args.readonly:
        print("Running in READ-ONLY mode - no edits allowed")
    print(f"Press Ctrl+C to stop")

    app.run(host=args.host, port=args.port, debug=app.config["DEBUG"])


if __name__ == "__main__":
    main()
