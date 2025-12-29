#!/usr/bin/env python3
"""
VORAS Release Workflow - Process data/release with VORAS agent

This script orchestrates the full workflow:
1. Import data/release/lemmas JSONL files into a temporary SQLite database
2. Run VORAS agent to check and populate missing translations
3. Export the updated data back to data/release/lemmas with separate language files
4. Optionally commit changes to git

This allows VORAS to work on curated release data while keeping the release
format clean and organized.
"""

import sys
from pathlib import Path

# Add src directory to path
if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import tempfile
import shutil
import logging
from typing import Optional, List

import constants
from agents.dramblys.jsonl_import import JSONLImporter
from agents.voras.agent import VorasAgent
from wordfreq.storage.database import create_database_session
from wordfreq.storage.migrate import export_sqlite_to_release

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class VorasReleaseWorkflow:
    """Orchestrates VORAS processing on data/release format."""

    def __init__(
        self,
        release_dir: str = "data/release/lemmas",
        dry_run: bool = False,
        model: str = "gpt-5-mini",
        debug: bool = False,
    ):
        """
        Initialize the workflow.

        Args:
            release_dir: Path to data/release/lemmas directory
            dry_run: If True, don't make LLM calls or write files
            model: LLM model to use for VORAS
            debug: Enable debug logging
        """
        self.release_dir = Path(release_dir)
        self.dry_run = dry_run
        self.model = model
        self.debug = debug

        if debug:
            logger.setLevel(logging.DEBUG)

        # We'll use a temporary database
        self.temp_db = None
        self.temp_db_path = None

    def run(
        self,
        languages: Optional[List[str]] = None,
        limit: Optional[int] = None,
        mode: str = "populate",
    ):
        """
        Run the full workflow.

        Args:
            languages: Specific languages to process (None = all)
            limit: Limit number of words to process
            mode: Operation mode - "populate" (add missing), "check" (validate only), "both"

        Returns:
            Dictionary with workflow results
        """
        results = {
            "import": None,
            "voras": None,
            "export": None,
            "success": False,
        }

        try:
            # Step 1: Import release data to temp SQLite
            logger.info("=" * 80)
            logger.info("STEP 1: Importing data/release to temporary SQLite database")
            logger.info("=" * 80)
            results["import"] = self._import_release_to_sqlite()

            if results["import"]["errors"] > 0:
                logger.error(f"Import completed with {results['import']['errors']} errors")
                if results["import"]["guid_collisions"] > 0:
                    logger.error(f"Found {results['import']['guid_collisions']} GUID collisions - aborting")
                    return results

            # Step 2: Run VORAS
            logger.info("\n" + "=" * 80)
            logger.info("STEP 2: Running VORAS agent")
            logger.info("=" * 80)
            results["voras"] = self._run_voras(languages, limit, mode)

            # Step 3: Export back to release format
            logger.info("\n" + "=" * 80)
            logger.info("STEP 3: Exporting updated data to data/release")
            logger.info("=" * 80)
            results["export"] = self._export_sqlite_to_release()

            results["success"] = True
            logger.info("\n" + "=" * 80)
            logger.info("WORKFLOW COMPLETE")
            logger.info("=" * 80)

            return results

        except Exception as e:
            logger.error(f"Workflow failed: {e}", exc_info=True)
            results["error"] = str(e)
            return results

        finally:
            self._cleanup()

    def _import_release_to_sqlite(self):
        """Import data/release JSONL files to temporary SQLite database."""
        # Create temporary database
        temp_dir = tempfile.mkdtemp(prefix="voras_release_")
        self.temp_db_path = str(Path(temp_dir) / "temp.db")
        logger.info(f"Created temporary database: {self.temp_db_path}")

        # Create database session
        session = create_database_session(self.temp_db_path)

        try:
            # Create importer
            importer = JSONLImporter(
                session=session,
                migration_config=None,  # No migration needed for release data
                dry_run=self.dry_run,
            )

            # Import all base.jsonl files from release directory
            stats = importer.import_directory(
                directory=self.release_dir,
                pattern="**/base.jsonl"
            )

            logger.info(importer.get_summary())

            return stats

        finally:
            session.close()

    def _run_voras(
        self,
        languages: Optional[List[str]],
        limit: Optional[int],
        mode: str,
    ):
        """Run VORAS agent on the temporary database."""
        # Create VORAS agent pointing to temp database
        agent = VorasAgent(
            db_path=self.temp_db_path,
            debug=self.debug,
            model=self.model,
        )

        if mode == "check":
            # Validation only
            if languages and len(languages) == 1:
                return agent.validate_translations(
                    languages[0],
                    limit=limit,
                    sample_rate=1.0,
                    confidence_threshold=0.7,
                )
            else:
                return agent.validate_all_translations(
                    limit=limit,
                    sample_rate=1.0,
                    confidence_threshold=0.7,
                )

        elif mode == "populate":
            # Fix missing translations
            return agent.fix_missing_translations(
                language_code=languages,
                limit=limit,
                dry_run=self.dry_run,
            )

        elif mode == "both":
            # First check, then populate
            if languages and len(languages) == 1:
                check_results = agent.validate_translations(
                    languages[0],
                    limit=limit,
                    sample_rate=1.0,
                    confidence_threshold=0.7,
                )
            else:
                check_results = agent.validate_all_translations(
                    limit=limit,
                    sample_rate=1.0,
                    confidence_threshold=0.7,
                )

            populate_results = agent.fix_missing_translations(
                language_code=languages,
                limit=limit,
                dry_run=self.dry_run,
            )

            return {
                "check": check_results,
                "populate": populate_results,
            }

    def _export_sqlite_to_release(self):
        """Export temporary SQLite database back to data/release format."""
        if self.dry_run:
            logger.info("[DRY RUN] Would export to data/release/lemmas")
            return {"dry_run": True}

        # Export using the migrate module
        export_sqlite_to_release(self.temp_db_path, str(self.release_dir))

        return {"success": True}

    def _cleanup(self):
        """Clean up temporary database."""
        if self.temp_db_path:
            temp_dir = Path(self.temp_db_path).parent
            if temp_dir.exists():
                logger.info(f"Cleaning up temporary database: {temp_dir}")
                shutil.rmtree(temp_dir)


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
        print(f"Mode: {args.mode}")
        print(f"Languages: {', '.join(args.languages) if args.languages else 'all'}")
        print(f"Model: {args.model}")
        if args.limit:
            print(f"Limit: {args.limit} words")
        print("\nThis will:")
        print("  1. Import data/release → temporary SQLite database")
        print("  2. Run VORAS to check/populate translations")
        print("  3. Export updated data → data/release (WILL OVERWRITE FILES)")
        print("\nThis may incur LLM API costs.")
        response = input("\nDo you want to proceed? [y/N]: ").strip().lower()

        if response not in ["y", "yes"]:
            print("Aborted.")
            sys.exit(0)

        print()

    # Run workflow
    workflow = VorasReleaseWorkflow(
        release_dir=args.release_dir,
        dry_run=args.dry_run,
        model=args.model,
        debug=args.debug,
    )

    results = workflow.run(
        languages=args.languages,
        limit=args.limit,
        mode=args.mode,
    )

    # Print summary
    if results["success"]:
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)

        # Import summary
        if results["import"]:
            import_stats = results["import"]
            print(f"\nImport:")
            print(f"  Records imported: {import_stats['records_imported']}")
            print(f"  Records skipped: {import_stats['records_skipped']}")
            print(f"  Errors: {import_stats['errors']}")

        # VORAS summary
        if results["voras"]:
            voras_results = results["voras"]
            print(f"\nVORAS ({args.mode}):")

            if args.mode == "both":
                # Combined results
                if "check" in voras_results:
                    check = voras_results["check"]
                    if "total_issues_all_languages" in check:
                        print(f"  Validation issues found: {check['total_issues_all_languages']}")

                if "populate" in voras_results:
                    populate = voras_results["populate"]
                    print(f"  Translations populated: {populate.get('total_fixed', 0)}")
                    print(f"  Failed: {populate.get('total_failed', 0)}")
            else:
                # Single mode results
                if "total_fixed" in voras_results:
                    print(f"  Translations populated: {voras_results['total_fixed']}")
                    print(f"  Failed: {voras_results['total_failed']}")
                elif "total_issues_all_languages" in voras_results:
                    print(f"  Issues found: {voras_results['total_issues_all_languages']}")

        # Export summary
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
