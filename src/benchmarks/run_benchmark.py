#!/usr/bin/python3

"""Main interface for running benchmarks."""

import argparse
import json
import logging
import sys
import traceback
from typing import Any, Dict, List, Optional, Set, Tuple

import benchmarks.datastore.benchmarks as datastore_benchmarks
import benchmarks.datastore.common as datastore_common
from benchmarks.config import BenchmarkConfig
from benchmarks.lib.utils.factory import (
    get_all_benchmark_codes,
    get_benchmark_metadata,
    get_generator,
    get_runner,
)
from benchmarks.scripts.delete_benchmark import delete_benchmark_completely

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_all_model_codenames() -> List[str]:
    """Get a list of all model codenames from the database."""
    session = datastore_common.create_dev_session()
    models = datastore_common.list_all_models(session)
    return [model["codename"] for model in models]


def get_all_benchmarks() -> List[str]:
    """Get a list of all registered benchmark codes."""
    return get_all_benchmark_codes()


def run_benchmark(benchmark_code: str, model: str) -> Optional[int]:
    """Run a specific benchmark for a model."""
    logger.info("Running benchmark %s for model %s", benchmark_code, model)

    try:
        runner = get_runner(benchmark_code, model)
        if not runner:
            logger.error("Failed to create runner for benchmark %s", benchmark_code)
            return None

        run_id = runner.run()

        logger.info(
            "Benchmark %s completed for model %s (run_id=%s)", benchmark_code, model, run_id
        )
        return run_id

    except Exception as e:
        logger.error("Error running benchmark %s for model %s: %s", benchmark_code, model, str(e))
        logger.error(traceback.format_exc())
        return None


def _extract_model_response(debug_json: Any) -> Optional[Any]:
    if not isinstance(debug_json, dict):
        return None
    for key in ("model_answer", "response", "model_response", "response_payload"):
        if key in debug_json:
            return debug_json[key]
    return None


def _extract_question_data(question_info_json: Any, debug_json: Any) -> Optional[Dict[str, Any]]:
    if isinstance(question_info_json, dict) and "correct_answer" in question_info_json:
        return question_info_json

    if not isinstance(debug_json, dict):
        return None

    expected = debug_json.get("expected_answer") or debug_json.get("expected")
    if isinstance(expected, dict):
        return {"correct_answer": expected}

    question_snapshot = debug_json.get("question_snapshot")
    if isinstance(question_snapshot, dict) and "correct_answer" in question_snapshot:
        return question_snapshot

    return None


def rescore_benchmark_runs(
    benchmark_code: str,
    model: Optional[str] = None,
    session=None,
    dry_run: bool = False,
) -> Dict[str, int]:
    """Rescore historical run_detail rows for a benchmark using current runner scoring logic."""
    if not session:
        session = datastore_common.create_dev_session()

    run_query = session.query(datastore_benchmarks.Run).filter(
        datastore_benchmarks.Run.benchmark_name == benchmark_code
    )
    if model:
        run_query = run_query.filter(datastore_benchmarks.Run.model_name == model)

    runs = run_query.order_by(datastore_benchmarks.Run.run_id.asc()).all()

    summary = {
        "runs_considered": len(runs),
        "runs_updated": 0,
        "details_rescored": 0,
        "details_skipped": 0,
    }

    for run in runs:
        runner = get_runner(benchmark_code, run.model_name)
        if not runner or not hasattr(runner, "score_response"):
            logger.warning(
                "Skipping run_id=%s because runner for %s/%s has no score_response",
                run.run_id,
                benchmark_code,
                run.model_name,
            )
            summary["details_skipped"] += (
                session.query(datastore_benchmarks.RunDetail)
                .filter(datastore_benchmarks.RunDetail.run_id == run.run_id)
                .count()
            )
            continue

        rows = (
            session.query(datastore_benchmarks.RunDetail, datastore_benchmarks.Question)
            .join(
                datastore_benchmarks.Question,
                datastore_benchmarks.RunDetail.question_id
                == datastore_benchmarks.Question.question_id,
            )
            .filter(datastore_benchmarks.RunDetail.run_id == run.run_id)
            .all()
        )

        rescored_values: List[int] = []
        run_changed = False

        for detail, question in rows:
            debug_json = datastore_common.decode_json(detail.debug_json)
            question_info = datastore_common.decode_json(question.question_info_json)
            model_response = _extract_model_response(debug_json)
            question_data = _extract_question_data(question_info, debug_json)

            if model_response is None or not isinstance(question_data, dict):
                summary["details_skipped"] += 1
                continue

            try:
                rescored = int(runner.score_response(question_data, model_response))
            except Exception as error:
                logger.warning(
                    "Failed to rescore run_id=%s question_id=%s: %s",
                    run.run_id,
                    detail.question_id,
                    error,
                )
                summary["details_skipped"] += 1
                continue

            rescored_values.append(rescored)
            summary["details_rescored"] += 1

            if detail.score != rescored:
                run_changed = True

            if not dry_run:
                detail.score = rescored
                if isinstance(debug_json, dict):
                    debug_json.setdefault("response_payload", model_response)
                    debug_json.setdefault("question_snapshot", question_data)
                    debug_json.setdefault("scoring_runner", runner.__class__.__name__)
                    detail.debug_json = json.dumps(debug_json)

        if not rescored_values:
            continue

        new_run_score = int(round(sum(rescored_values) / len(rescored_values)))
        if run.normed_score != new_run_score:
            run_changed = True

        if not dry_run:
            run.normed_score = new_run_score

        if run_changed:
            summary["runs_updated"] += 1

    if not dry_run:
        session.commit()

    return summary


def run_all_benchmarks_for_model(
    model: str, blacklist_benchmarks: Optional[Set[str]] = None
) -> List[Tuple[str, Optional[int]]]:
    """Run all available benchmarks for a specific model."""
    logger.info("Running all benchmarks for model %s", model)

    blacklist_benchmarks = blacklist_benchmarks or set()
    benchmarks = [b for b in get_all_benchmarks() if b not in blacklist_benchmarks]

    results = []
    for benchmark_code in benchmarks:
        logger.info("Running benchmark %s for model %s", benchmark_code, model)
        try:
            run_id = run_benchmark(benchmark_code, model)
            results.append((benchmark_code, run_id))

            if run_id:
                logger.info(
                    "Benchmark %s completed successfully (run_id=%s)", benchmark_code, run_id
                )
            else:
                logger.warning("Benchmark %s failed for model %s", benchmark_code, model)

        except Exception as e:
            logger.error(
                "Error running benchmark %s for model %s: %s", benchmark_code, model, str(e)
            )
            logger.error(traceback.format_exc())
            results.append((benchmark_code, None))

    successful = sum(1 for _, run_id in results if run_id is not None)
    logger.info("Completed %d/%d benchmarks for model %s", successful, len(results), model)

    return results


def run_missing_benchmarks(
    blacklist_models: Optional[Set[str]] = None,
    blacklist_benchmarks: Optional[Set[str]] = None,
    session=None,
    only_model: Optional[str] = None,
) -> List[Tuple[str, str]]:
    """Run all benchmarks that don't have results yet."""
    if not session:
        session = datastore_common.create_dev_session()

    blacklist_models = blacklist_models or set()
    blacklist_benchmarks = blacklist_benchmarks or set()

    if only_model:
        models = [only_model]
    else:
        models = [m for m in get_all_model_codenames() if m not in blacklist_models]
    benchmarks = [b for b in get_all_benchmarks() if b not in blacklist_benchmarks]

    scores = datastore_benchmarks.get_highest_benchmark_scores(session)

    missing = []
    for benchmark in benchmarks:
        for model in models:
            if (benchmark, model) not in scores:
                missing.append((model, benchmark))

    run_pairs = []
    for model_name, benchmark in missing:
        logger.info("Running missing benchmark: %s for %s", benchmark, model_name)
        try:
            run_id = run_benchmark(benchmark, model_name)
            if run_id:
                run_pairs.append((model_name, benchmark))
        except Exception as e:
            logger.error("Failed to run %s for %s: %s", benchmark, model_name, str(e))
            logger.error(traceback.format_exc())

    return run_pairs


def generate_benchmark_questions(
    benchmark_code: str,
    num_questions: Optional[int] = None,
    session=None,
    require_llm_confirmation: bool = False,
    llm_confirmation_granted: bool = False,
) -> bool:
    """Generate questions for a benchmark and load them into the database."""
    logger.info("Generating questions for benchmark %s", benchmark_code)

    try:
        generator = get_generator(benchmark_code, session)
        if not generator:
            logger.error("Failed to create generator for benchmark %s", benchmark_code)
            return False

        if require_llm_confirmation and getattr(generator, "can_generate_with_llm", False):
            if not llm_confirmation_granted:
                print(
                    f"Benchmark {benchmark_code} may use an LLM ({generator.__class__.__name__}). "
                    "Continue? [y/N]: ",
                    end="",
                    flush=True,
                )
                try:
                    response = input().strip().lower()
                except EOFError:
                    response = ""

                if response not in {"y", "yes"}:
                    logger.info(
                        "Cancelled generation for %s because LLM usage was not confirmed.",
                        benchmark_code,
                    )
                    return False

        if num_questions is None:
            metadata = get_benchmark_metadata(benchmark_code)
            num_questions = metadata.default_num_questions if metadata else 40

        generator.load_to_database(num_questions=num_questions)

        logger.info("Successfully generated questions for benchmark %s", benchmark_code)
        return True

    except Exception as e:
        logger.error("Error generating questions for benchmark %s: %s", benchmark_code, str(e))
        logger.error(traceback.format_exc())
        return False


def regenerate_benchmark_questions(
    benchmark_code: str,
    num_questions: Optional[int] = None,
    session=None,
    require_llm_confirmation: bool = False,
    llm_confirmation_granted: bool = False,
) -> bool:
    """Delete existing questions for a benchmark and regenerate from scratch."""
    logger.info("Regenerating questions for benchmark %s", benchmark_code)

    if not session:
        session = datastore_common.create_dev_session()

    try:
        delete_benchmark_completely(session, benchmark_code)
    except Exception as e:
        logger.error("Error deleting benchmark %s: %s", benchmark_code, str(e))
        logger.error(traceback.format_exc())
        return False

    return generate_benchmark_questions(
        benchmark_code,
        num_questions=num_questions,
        session=session,
        require_llm_confirmation=require_llm_confirmation,
        llm_confirmation_granted=llm_confirmation_granted,
    )


def get_benchmark_info() -> List[Dict]:
    """Get information about all registered benchmarks."""
    result = []
    for code in get_all_benchmark_codes():
        metadata = get_benchmark_metadata(code)
        if metadata:
            result.append(
                {
                    "code": metadata.code,
                    "name": metadata.name,
                    "description": metadata.description,
                    "version": metadata.version,
                }
            )
    return result


def sync_benchmarks_to_db(session=None) -> Dict[str, int]:
    """Ensure every code-registered benchmark has a row in the database.

    This does *not* generate questions.  It only inserts the benchmark
    metadata (codename, displayname, description) so that the web server
    can show all benchmarks and allow runs to be queued.

    Returns a summary dict with keys ``added`` and ``already_present``.
    """
    if not session:
        session = datastore_common.create_dev_session()

    summary = {"added": 0, "already_present": 0}

    for code in get_all_benchmark_codes():
        metadata = get_benchmark_metadata(code)
        if not metadata:
            continue

        success, msg = datastore_benchmarks.insert_benchmark(
            session,
            codename=metadata.code,
            displayname=metadata.name,
            description=metadata.description,
            category=metadata.category,
        )
        if success:
            summary["added"] += 1
            logger.info("Synced benchmark to DB: %s", code)
        else:
            summary["already_present"] += 1
            # Update category for existing benchmarks.
            # Note: insert_benchmark does a rollback on IntegrityError,
            # so we must commit category updates individually.
            existing = (
                session.query(datastore_benchmarks.Benchmark)
                .filter(datastore_benchmarks.Benchmark.codename == code)
                .first()
            )
            if existing and existing.category != metadata.category:
                existing.category = metadata.category
                session.commit()
                summary["updated"] = summary.get("updated", 0) + 1

    return summary


def init_all_benchmarks(
    skip_existing: bool = True,
    num_questions: Optional[int] = None,
    session=None,
    require_llm_confirmation: bool = False,
    llm_confirmation_granted: bool = False,
) -> Dict[str, Any]:
    """Sync all registered benchmarks to the DB and generate questions for empty ones.

    Args:
        skip_existing: When True (default), skip benchmarks that already have
            questions.  Set to False to regenerate questions even for benchmarks
            that already have them.
        num_questions: Override the per-benchmark default question count.
        session: Optional database session.

    Returns:
        Summary dict with keys ``synced``, ``generated``, ``skipped``,
        ``failed``.
    """
    if not session:
        session = datastore_common.create_dev_session()

    sync_summary = sync_benchmarks_to_db(session)

    summary: Dict[str, Any] = {
        "synced": sync_summary,
        "generated": [],
        "skipped": [],
        "failed": [],
    }

    all_codes = sorted(get_all_benchmark_codes())

    for code in all_codes:
        if skip_existing:
            question_count = (
                session.query(datastore_benchmarks.Question)
                .filter(datastore_benchmarks.Question.benchmark_name == code)
                .count()
            )
            if question_count > 0:
                logger.info("Skipping %s – already has %d questions", code, question_count)
                summary["skipped"].append(code)
                continue

        logger.info("Generating questions for %s", code)
        success = generate_benchmark_questions(
            code,
            num_questions=num_questions,
            session=session,
            require_llm_confirmation=require_llm_confirmation,
            llm_confirmation_granted=llm_confirmation_granted,
        )
        if success:
            summary["generated"].append(code)
        else:
            summary["failed"].append(code)

    return summary


def _resolve_postgres_url(args: argparse.Namespace) -> Optional[str]:
    """Determine the PostgreSQL URL from CLI flags, if any."""
    if getattr(args, "db_url", None) and args.db_url.startswith("postgresql://"):
        return BenchmarkConfig.normalize_postgres_url(args.db_url)
    if getattr(args, "postgres", False):
        try:
            return BenchmarkConfig.build_postgres_url()
        except Exception as exc:
            print(f"Error building PostgreSQL URL: {exc}", file=sys.stderr)
            sys.exit(1)
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run benchmarks for language models")
    parser.add_argument(
        "--postgres",
        action="store_true",
        help="Use PostgreSQL (Supabase) backend; reads keys/postgres.key",
    )
    parser.add_argument(
        "--db-url",
        help="Full PostgreSQL connection URL (overrides --postgres key-file lookup)",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    run_parser = subparsers.add_parser("run", help="Run a benchmark")
    run_parser.add_argument("benchmark", help="Benchmark code")
    run_parser.add_argument("model", help="Model codename")

    gen_parser = subparsers.add_parser("generate", help="Generate benchmark questions")
    gen_parser.add_argument("benchmark", help="Benchmark code")
    gen_parser.add_argument(
        "--num-questions",
        type=int,
        default=None,
        help="Number of questions to generate (default: per-benchmark setting)",
    )
    gen_parser.add_argument(
        "--yes-llm",
        action="store_true",
        help="Skip LLM usage confirmation prompt when a generator can call an LLM",
    )

    regen_parser = subparsers.add_parser(
        "regenerate", help="Delete existing questions and regenerate from scratch"
    )
    regen_parser.add_argument("benchmark", help="Benchmark code")
    regen_parser.add_argument(
        "--num-questions",
        type=int,
        default=None,
        help="Number of questions to generate (default: per-benchmark setting)",
    )
    regen_parser.add_argument(
        "--yes-llm",
        action="store_true",
        help="Skip LLM usage confirmation prompt when a generator can call an LLM",
    )

    subparsers.add_parser("list", help="List available benchmarks")
    subparsers.add_parser("models", help="List available models")

    missing_parser = subparsers.add_parser("missing", help="Run missing benchmarks")
    missing_parser.add_argument("--model", help="Only run missing benchmarks for this model")
    missing_parser.add_argument("--blacklist-models", nargs="+", help="Models to exclude")
    missing_parser.add_argument("--blacklist-benchmarks", nargs="+", help="Benchmarks to exclude")

    subparsers.add_parser(
        "sync-benchmarks",
        help="Ensure all code-registered benchmarks have a DB row (no question generation)",
    )

    init_all_parser = subparsers.add_parser(
        "init-all",
        help="Sync benchmarks to DB and generate questions for those that have none",
    )
    init_all_parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate questions even for benchmarks that already have questions",
    )
    init_all_parser.add_argument(
        "--num-questions",
        type=int,
        default=None,
        help="Override the per-benchmark default question count",
    )
    init_all_parser.add_argument(
        "--yes-llm",
        action="store_true",
        help="Skip LLM usage confirmation prompt when generators can call an LLM",
    )

    rescore_parser = subparsers.add_parser(
        "rescore",
        help="Rescore existing run results for a benchmark using current scoring logic",
    )
    rescore_parser.add_argument(
        "benchmark", help="Benchmark code, e.g. 0062_sentence_decomposition"
    )
    rescore_parser.add_argument("--model", help="Optional model codename filter")
    rescore_parser.add_argument(
        "--dry-run", action="store_true", help="Preview without updating DB"
    )

    args = parser.parse_args()

    # When a postgres backend is requested, monkey-patch create_dev_session so
    # that all internal code (runners, generators, etc.) that calls it will
    # transparently use the PostgreSQL connection instead of SQLite.
    postgres_url = _resolve_postgres_url(args)
    if postgres_url:
        print("Using storage backend: postgres (Supabase)")
        _original_create_dev_session = datastore_common.create_dev_session

        def _postgres_dev_session():
            return datastore_common.create_postgres_session(postgres_url)

        datastore_common.create_dev_session = _postgres_dev_session
        # Also patch the reference used by datastore_benchmarks, since it may
        # have imported create_dev_session at module load time.
        if hasattr(datastore_benchmarks, "create_dev_session"):
            datastore_benchmarks.create_dev_session = _postgres_dev_session

    if args.command == "run":
        run_id = run_benchmark(args.benchmark, args.model)
        if run_id:
            print(f"Benchmark completed successfully. Run ID: {run_id}")
        else:
            print("Benchmark failed.")

    elif args.command == "generate":
        success = generate_benchmark_questions(
            args.benchmark,
            num_questions=args.num_questions,
            require_llm_confirmation=True,
            llm_confirmation_granted=args.yes_llm,
        )
        if success:
            print(f"Successfully generated questions for {args.benchmark}")

    elif args.command == "regenerate":
        success = regenerate_benchmark_questions(
            args.benchmark,
            num_questions=args.num_questions,
            require_llm_confirmation=True,
            llm_confirmation_granted=args.yes_llm,
        )
        if success:
            print(f"Successfully regenerated questions for {args.benchmark}")
        else:
            print(f"Failed to regenerate questions for {args.benchmark}")

    elif args.command == "list":
        benchmarks = get_benchmark_info()
        print("Available benchmarks:")
        for benchmark in benchmarks:
            print(f"  {benchmark['code']}: {benchmark['name']}")
            if benchmark["description"]:
                print(f"    {benchmark['description']}")

    elif args.command == "models":
        models = get_all_model_codenames()
        print("Available models:")
        for model in models:
            print(f"  {model}")

    elif args.command == "missing":
        blacklist_models = set(args.blacklist_models) if args.blacklist_models else set()
        blacklist_benchmarks = (
            set(args.blacklist_benchmarks) if args.blacklist_benchmarks else set()
        )

        run_pairs = run_missing_benchmarks(
            blacklist_models, blacklist_benchmarks, only_model=getattr(args, "model", None)
        )

        if run_pairs:
            print("Successfully ran the following benchmarks:")
            for run_model, run_benchmark_code in run_pairs:
                print(f"  {run_benchmark_code} for {run_model}")
        else:
            print("No missing benchmarks found or all runs failed.")

    elif args.command == "rescore":
        summary = rescore_benchmark_runs(
            benchmark_code=args.benchmark,
            model=args.model,
            dry_run=args.dry_run,
        )
        mode = "DRY RUN" if args.dry_run else "UPDATED"
        print(
            f"[{mode}] runs_considered={summary['runs_considered']} runs_updated={summary['runs_updated']} "
            f"details_rescored={summary['details_rescored']} details_skipped={summary['details_skipped']}"
        )

    elif args.command == "sync-benchmarks":
        sync_summary = sync_benchmarks_to_db()
        updated = sync_summary.get("updated", 0)
        msg = (
            f"Sync complete: {sync_summary['added']} added, "
            f"{sync_summary['already_present']} already present"
        )
        if updated:
            msg += f", {updated} category update(s)"
        print(msg + ".")

    elif args.command == "init-all":
        init_summary = init_all_benchmarks(
            skip_existing=not args.force,
            num_questions=args.num_questions,
            require_llm_confirmation=True,
            llm_confirmation_granted=args.yes_llm,
        )
        sync = init_summary["synced"]
        print(f"Sync: {sync['added']} added, {sync['already_present']} already present.")
        if init_summary["generated"]:
            print(f"Generated questions for: {', '.join(init_summary['generated'])}")
        if init_summary["skipped"]:
            print(f"Skipped (already had questions): {', '.join(init_summary['skipped'])}")
        if init_summary["failed"]:
            print(f"FAILED: {', '.join(init_summary['failed'])}")


if __name__ == "__main__":
    main()
