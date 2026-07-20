#!/usr/bin/python3

"""
Barsukas - Word Frequency Database Web Editor

A lightweight Flask web interface for manual edits to lemmas, translations,
and difficulty levels in the linguistics database.

This module is the application factory. To run Barsukas, use
src/barsukas/launch.sh (or src/barsukas/unified_app.py directly), which starts
the Flask server and the task worker in one process.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional, cast

from barsukas.config import Config
from barsukas.personas import PersonaConfig
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
    set_build_info_metrics,
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
    concepts,
    conversations,
    exports,
    lemmas,
    llm_api,
    operation_logs,
    overrides,
    pattern_sentences,
    peleda,
    pending_imports,
    phrases,
    pradzia,
    quality,
    rhymes,
    sentence_stats,
    sentences,
    settings,
    strings_export,
    texts,
    trakaido,
    trakaido_activities,
    translations,
    wireword,
)
from barsukas.routes.review import rapid_review, rapid_review_hub, sentence_rapid_review
from barsukas.routes.sync import (
    sync_derivative_release,
    sync_hub,
    sync_phrase_release,
    sync_relation_release,
    sync_release,
    sync_sentence_release,
    sync_synonym_release,
)
from storage.backend import configure_backend, create_session
from storage.backend.config import BackendType, DataSourceConfig

logger = logging.getLogger(__name__)


class BarsukasFlask(Flask):
    """Custom Flask subclass with typed custom attributes."""

    backend_config: DataSourceConfig
    db_session_factory: Callable[[], Session]
    bench_db_session_factory: Optional[Callable[[], Session]]
    concepts_db_session_factory: Optional[Callable[[], Session]]


def _warn_degraded(what: str, reason: str, consequence: str, fix: str) -> str:
    """Log a hard-to-miss banner about running in a degraded configuration.

    Silently serving a different database than the persona asked for is the
    failure this exists to prevent, so the banner names what was wanted, why it
    is unavailable, and what the process is doing instead.

    Returns:
        A one-line summary, for display on the settings page.
    """
    summary = f"{what} unavailable: {reason}"
    logger.warning("=" * 78)
    logger.warning("WARNING: %s", what)
    logger.warning("  Reason:      %s", reason)
    logger.warning("  Consequence: %s", consequence)
    logger.warning("  Fix:         %s", fix)
    logger.warning("=" * 78)
    return summary


def create_app(
    config_class: type[Config] = Config,
    db_url: Optional[str] = None,
    use_word2vec: bool = False,
    persona: Optional[PersonaConfig] = None,
) -> BarsukasFlask:
    """Create and configure the Flask application.

    Barsukas uses two databases and they are configured independently:

    - main: lemmas/words. SQLite, JSONL, or PostgreSQL per the persona, or an
      explicit ``db_url`` override.
    - concepts: always the hardcoded global PostgreSQL, or the main database
      when the persona does not ask for PostgreSQL concepts.

    Args:
        config_class: Configuration class to use
        db_url: Optional main-database URL (postgresql://user:pass@host:5432/db).
            Overrides the persona's main backend. Never affects concepts.
        use_word2vec: Enable pgvector embedding operations
        persona: The resolved persona. When omitted, the main database is
            SQLite at config DB_PATH, which is what the test fixtures rely on.
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

    # Degraded-mode notices, surfaced on the settings page as well as the log.
    degraded: list[str] = []

    # --- main database -------------------------------------------------------
    # An explicit db_url wins over the persona; a persona's postgres main DB
    # builds the URL from the key file. The environment is never consulted:
    # with no persona and no db_url (test fixtures, directly-constructed apps)
    # the main database is SQLite at config DB_PATH.
    postgres_url = db_url if db_url and db_url.startswith("postgresql://") else None
    if postgres_url and persona:
        logger.info("--db-url overrides persona '%s' main database", persona.name.value)

    wants_postgres_main = bool(postgres_url) or bool(persona and persona.use_postgres)

    if wants_postgres_main and not postgres_url:
        try:
            postgres_url = DataSourceConfig.build_postgres_url()
        except Exception as e:
            degraded.append(
                _warn_degraded(
                    what="PostgreSQL main database",
                    reason=str(e),
                    consequence="Falling back to the local SQLite database.",
                    fix="Add credentials at keys/postgres.key",
                )
            )

    if postgres_url:
        print("Using storage backend: postgres")
        backend_config = DataSourceConfig(
            backend_type=BackendType.POSTGRES,
            postgres_url=postgres_url,
            use_word2vec=use_word2vec,
        )
        app.config["DB_PATH"] = "PostgreSQL (Supabase)"  # For display
        app.config["USING_POSTGRES"] = True
    elif persona and persona.use_jsonl:
        print("Using storage backend: jsonl")
        repo_root = Path(__file__).parent.parent.parent
        jsonl_dir = repo_root / (persona.jsonl_data_dir or "data/release")
        backend_config = DataSourceConfig(
            backend_type=BackendType.JSONL,
            jsonl_data_dir=str(jsonl_dir),
            use_word2vec=use_word2vec,
        )
        app.config["USING_POSTGRES"] = False
    else:
        print("Using storage backend: sqlite")
        db_path = app.config["DB_PATH"]
        if not Path(db_path).exists():
            print(f"Error: Database not found at {db_path}", file=sys.stderr)
            sys.exit(1)
        backend_config = DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=db_path)
        app.config["USING_POSTGRES"] = False

    # Store backend config in app, and declare it as the process's main
    # database so no-arg storage.backend helpers and the S3 staging prefix
    # see the same backend.
    app.backend_config = backend_config
    configure_backend(backend_config)
    app.config["SERVER_MODE"] = "readwrite"

    set_server_mode_metrics(
        server_mode=app.config["SERVER_MODE"],
        backend=backend_config.backend_type.value,
        readonly=bool(app.config.get("READONLY", False)),
        debug=bool(app.config.get("DEBUG", False)),
    )

    # Record deployed git revision/branch/version (resolved once, then cached).
    set_build_info_metrics()

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
    app.concepts_db_session_factory = None

    # --- concepts database ---------------------------------------------------
    # Concepts live in the hardcoded global PostgreSQL; there is no custom URL
    # for them. Personas that don't ask for PostgreSQL concepts (local-sqlite,
    # prod) read concepts out of the main database instead.
    #
    # This block is the sole authority on CONCEPTS_WRITABLE: it is the only code
    # that knows whether the connection was actually established. Deriving it
    # from persona flags elsewhere would advertise writable concepts while
    # serving the fallback backend.
    wants_postgres_concepts = bool(persona and persona.use_postgres_concepts)

    if wants_postgres_concepts:
        try:
            concepts_postgres_url: Optional[str] = DataSourceConfig.build_postgres_url()
        except Exception as concepts_exc:
            persona_label = f" '{persona.name.value}'" if persona else ""
            degraded.append(
                _warn_degraded(
                    what="PostgreSQL concepts database",
                    reason=str(concepts_exc),
                    consequence=(
                        f"Persona{persona_label} expects PostgreSQL concepts. Concepts are "
                        f"DISABLED for this session and cannot be edited."
                    ),
                    fix="Add credentials at keys/postgres.key, or use --persona local-sqlite",
                )
            )
            concepts_postgres_url = None

        if concepts_postgres_url:
            concepts_backend_config = DataSourceConfig(
                backend_type=BackendType.POSTGRES,
                postgres_url=concepts_postgres_url,
                use_word2vec=use_word2vec,
            )

            # golden/hosted connect read-only: writes/DDL are rejected at the server,
            # not merely gated by CONCEPTS_WRITABLE route checks.
            concepts_readonly = bool(persona and persona.postgres_concepts_readonly)

            def concepts_session_factory() -> Session:
                return cast(
                    Session,
                    create_session(concepts_backend_config, readonly=concepts_readonly),
                )

            app.concepts_db_session_factory = concepts_session_factory
            app.config["CONCEPTS_BACKEND"] = "postgres"
            app.config["CONCEPTS_WRITABLE"] = not concepts_readonly
        else:
            app.config["CONCEPTS_BACKEND"] = backend_config.backend_type.value
            app.config["CONCEPTS_WRITABLE"] = False
    else:
        app.config["CONCEPTS_BACKEND"] = backend_config.backend_type.value
        app.config["CONCEPTS_WRITABLE"] = False

    app.config["DEGRADED_NOTICES"] = degraded

    # --- persona-derived UI/access settings ----------------------------------
    # Owned here so one function holds every persona-derived config value.
    if persona:
        app.config["PERSONA"] = persona.name.value
        app.config["ALLOW_OUTBOUND_CALLS"] = persona.allow_outbound_calls
        app.config["ALLOW_API_KEYS"] = persona.allow_api_keys
        app.config["ENABLE_WORKER"] = persona.enable_worker
        app.config["ALLOW_RESTART"] = persona.allow_restart
        app.config["ALLOW_EXPORTS"] = persona.allow_exports
        if persona.readonly:
            app.config["READONLY"] = True
    try:
        from sqlalchemy.engine import Engine

        probe_session = app.db_session_factory()
        engine = probe_session.get_bind()
        # The JSONL backend's session returns a JSONLStorage object (not a real
        # SQLAlchemy Engine) from get_bind(); skip instrumentation there rather
        # than logging a misleading "No such event" warning.
        if isinstance(engine, Engine):
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
    app.register_blueprint(quality.bp)
    app.register_blueprint(concepts.bp)
    app.register_blueprint(texts.bp)
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
    app.register_blueprint(trakaido_activities.bp)
    app.register_blueprint(pattern_sentences.bp)
    app.register_blueprint(peleda.bp)
    app.register_blueprint(phrases.bp)
    app.register_blueprint(rhymes.bp)
    app.register_blueprint(pradzia.bp)
    app.register_blueprint(sync_hub.bp)
    app.register_blueprint(sync_release.bp)
    app.register_blueprint(sync_relation_release.bp)
    app.register_blueprint(sync_sentence_release.bp)
    app.register_blueprint(sync_phrase_release.bp)
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
        """Set up request context and start timing for metrics."""
        g.ui_lang = resolve_ui_language(request)
        endpoint_name = request.endpoint or "common"
        g.strings_default_module = endpoint_name.split(".", 1)[0]
        RequestMetricsMiddleware.before_request()

        if endpoint_name == "healthz":
            return

        g.db = app.db_session_factory()
        if (
            endpoint_name.startswith(("concepts.", "texts."))
            and app.concepts_db_session_factory is not None
        ):
            g.concepts_db = app.concepts_db_session_factory()

    @app.teardown_appcontext
    def shutdown_session(exception: Optional[BaseException]) -> None:
        """Clean up database session after request."""
        concepts_db = g.pop("concepts_db", None)
        if concepts_db is not None:
            if exception:
                concepts_db.rollback()
            else:
                concepts_db.commit()
            concepts_db.close()

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

    @app.get("/healthz")
    def healthz() -> Response:
        """Return a lightweight health check for process supervisors."""
        return Response("ok\n", mimetype="text/plain; charset=utf-8")

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
