#!/usr/bin/env python3
"""
VORAS Release Workflow - Process data/release with VORAS agent

This orchestrates the workflow:
1. Import data/release/lemmas → main SQLite database (using DRAMBLYS)
2. Run VORAS agent to check and populate missing translations
3. Export updated data → data/release/lemmas with separate language files

Usage:
    PYTHONPATH=src python -m agents.voras.release --mode populate --language lt zh
"""

import sys
from pathlib import Path

# Add src directory to path
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import argparse
import logging
from typing import Optional, List

import constants
from agents.dramblys.agent import DramblysAgent
from agents.voras.agent import VorasAgent
from wordfreq.storage.migrate import export_sqlite_to_release

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def run_voras_release_workflow(
    release_dir: str = "data/release/lemmas",
    db_path: str = None,
    languages: Optional[List[str]] = None,
    limit: Optional[int] = None,
    mode: str = "populate",
    model: str = "gpt-5-mini",
    dry_run: bool = False,
    skip_import: bool = False,
    skip_export: bool = False,
    debug: bool = False,
):
    """
    Run complete VORAS workflow on data/release.

    Args:
        release_dir: Path to data/release/lemmas directory
        db_path: Path to SQLite database (uses default if None)
        languages: Specific languages to process (None = all)
        limit: Limit number of words to process
        mode: Operation mode - "populate" (add missing), "check" (validate only), "both"
        model: LLM model to use
        dry_run: If True, don't make LLM calls or write files
        skip_import: Skip import step (data already in database)
        skip_export: Skip export step (leave results in database)
        debug: Enable debug logging

    Returns:
        Dictionary with results
    """
    if debug:
        logger.setLevel(logging.DEBUG)

    db_path = db_path or constants.WORDFREQ_DB_PATH
    results = {
        "import": None,
        "voras": None,
        "export": None,
        "success": False,
    }

    try:
        # Step 1: Import release data
        if not skip_import:
            logger.info("=" * 80)
            logger.info("STEP 1: Importing data/release to main database")
            logger.info("=" * 80)

            dramblys = DramblysAgent(db_path=db_path, debug=debug)
            results["import"] = dramblys.import_jsonl(
                source_path=release_dir,
                migration_config_path=None,
                dry_run=dry_run,
            )

            if results["import"]["errors"] > 0:
                logger.error(f"Import completed with {results['import']['errors']} errors")
                if results["import"]["guid_collisions"] > 0:
                    logger.error(f"Found {results['import']['guid_collisions']} GUID collisions")
                    return results

        # Step 2: Run VORAS
        logger.info("\n" + "=" * 80)
        logger.info("STEP 2: Running VORAS agent")
        logger.info("=" * 80)

        voras = VorasAgent(db_path=db_path, debug=debug, model=model)

        if mode == "check":
            if languages and len(languages) == 1:
                results["voras"] = voras.validate_translations(
                    languages[0], limit=limit, sample_rate=1.0, confidence_threshold=0.7
                )
            else:
                results["voras"] = voras.validate_all_translations(
                    limit=limit, sample_rate=1.0, confidence_threshold=0.7
                )
        elif mode == "populate":
            results["voras"] = voras.fix_missing_translations(
                language_code=languages, limit=limit, dry_run=dry_run
            )
        elif mode == "both":
            check_results = voras.validate_all_translations(
                limit=limit, sample_rate=1.0, confidence_threshold=0.7
            )
            populate_results = voras.fix_missing_translations(
                language_code=languages, limit=limit, dry_run=dry_run
            )
            results["voras"] = {"check": check_results, "populate": populate_results}

        # Step 3: Export back to release format
        if not skip_export:
            logger.info("\n" + "=" * 80)
            logger.info("STEP 3: Exporting updated data to data/release")
            logger.info("=" * 80)

            if dry_run:
                logger.info("[DRY RUN] Would export to data/release/lemmas")
                results["export"] = {"dry_run": True}
            else:
                export_sqlite_to_release(db_path, release_dir)
                results["export"] = {"success": True}

        results["success"] = True
        logger.info("\n" + "=" * 80)
        logger.info("WORKFLOW COMPLETE")
        logger.info("=" * 80)

        return results

    except Exception as e:
        logger.error(f"Workflow failed: {e}", exc_info=True)
        results["error"] = str(e)
        return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="VORAS Release Workflow - Process data/release with VORAS agent"
    )

    # Input/output
    parser.add_argument(
        "--release-dir",
        default="data/release/lemmas",
        help="Path to data/release/lemmas directory (default: data/release/lemmas)",
    )
    parser.add_argument(
        "--db-path",
        help="Path to SQLite database (default: from constants.WORDFREQ_DB_PATH)",
    )

    # Mode selection
    parser.add_argument(
        "--mode",
        choices=["check", "populate", "both"],
        default="populate",
        help="Operation mode: check (validate only), populate (add missing), both (default: populate)",
    )

    # Language selection
    parser.add_argument(
        "--language",
        "--languages",
        nargs="+",
        dest="languages",
        help="Specific language(s) to process (e.g., lt zh ko). If not specified, processes all languages.",
    )

    # Processing options
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of words to process",
    )

    # Workflow options
    parser.add_argument(
        "--skip-import",
        action="store_true",
        help="Skip import step (data already in database)",
    )
    parser.add_argument(
        "--skip-export",
        action="store_true",
        help="Skip export step (leave results in database)",
    )

    # LLM options
    parser.add_argument(
        "--model",
        default="gpt-5-mini",
        help="LLM model to use (default: gpt-5-mini)",
    )

    # Execution options
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't make LLM calls or write changes (report only)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompt",
    )

    args = parser.parse_args()

    # Confirmation prompt (unless --yes or --dry-run)
    if not args.yes and not args.dry_run:
        print("\nVORAS Release Workflow")
        print("=" * 80)
        print(f"Release directory: {args.release_dir}")
        print(f"Database: {args.db_path or constants.WORDFREQ_DB_PATH}")
        print(f"Mode: {args.mode}")
        print(f"Languages: {', '.join(args.languages) if args.languages else 'all'}")
        print(f"Model: {args.model}")
        if args.limit:
            print(f"Limit: {args.limit} words")
        print("\nThis will:")
        if not args.skip_import:
            print("  1. Import data/release → SQLite database")
        print("  2. Run VORAS to check/populate translations")
        if not args.skip_export:
            print("  3. Export updated data → data/release (WILL OVERWRITE FILES)")
        print("\nThis may incur LLM API costs.")
        response = input("\nDo you want to proceed? [y/N]: ").strip().lower()

        if response not in ["y", "yes"]:
            print("Aborted.")
            sys.exit(0)
        print()

    # Run workflow
    results = run_voras_release_workflow(
        release_dir=args.release_dir,
        db_path=args.db_path,
        languages=args.languages,
        limit=args.limit,
        mode=args.mode,
        model=args.model,
        dry_run=args.dry_run,
        skip_import=args.skip_import,
        skip_export=args.skip_export,
        debug=args.debug,
    )

    # Print summary
    if results["success"]:
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)

        if results["import"]:
            imp = results["import"]
            print(f"\nImport:")
            print(f"  Records imported: {imp['records_imported']}")
            print(f"  Records skipped: {imp['records_skipped']}")
            print(f"  Errors: {imp['errors']}")

        if results["voras"]:
            voras_res = results["voras"]
            print(f"\nVORAS ({args.mode}):")

            if args.mode == "both":
                if "populate" in voras_res:
                    pop = voras_res["populate"]
                    print(f"  Translations populated: {pop.get('total_fixed', 0)}")
                    print(f"  Failed: {pop.get('total_failed', 0)}")
            elif "total_fixed" in voras_res:
                print(f"  Translations populated: {voras_res['total_fixed']}")
                print(f"  Failed: {voras_res['total_failed']}")

        if results["export"]:
            print(f"\nExport: Success")

        print("=" * 80)
        sys.exit(0)
    else:
        print("\n" + "=" * 80)
        print("WORKFLOW FAILED")
        print("=" * 80)
        if "error" in results:
            print(f"Error: {results['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
