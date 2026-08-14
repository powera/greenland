#!/usr/bin/env python3
"""Administrative database initialization and maintenance services."""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

import constants
from wordfreq.frequency import combined_rank, corpus
from wordfreq.tiers.basic_english import BasicEnglishImporter
from wordfreq.tiers.cambridge_yle import CambridgeYleImporter
from wordfreq.tiers.cefr import CefrImporter
from wordfreq.tiers.base import TierImporter
from wordfreq.tiers.runner import run_import as run_tier_import
from storage.backend import create_session as create_backend_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.database import ensure_tables_exist, initialize_corpora
from storage.models.schema import Corpus  # Ensure Corpus model is imported
from storage.translation_helpers import has_translation_clause
import storage.admin.legacy_json_import as legacy_json_import

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class DatabaseAdminService:
    """Initialize and maintain a configured linguistic database."""

    def __init__(self, config: DataSourceConfig):
        """
        Initialize the administrative service.

        Args:
            config: DataSourceConfig with backend settings (required)
        """
        self.config = config
        self.debug = config.debug

        # Keep db_path for backward compatibility
        if config.backend_type == BackendType.SQLITE:
            self.db_path = config.sqlite_path
        else:
            self.db_path = None

        if self.debug:
            logger.setLevel(logging.DEBUG)

        # Log the database path being used (convert to absolute for clarity)
        if self.db_path:
            import os

            abs_path = os.path.abspath(self.db_path)
            logger.info(f"Using SQLite database: {abs_path}")

    def get_session(self) -> Session:
        """Get database session using backend abstraction."""
        return create_backend_session(self.config)

    def check_configuration(self) -> Dict[str, Any]:
        """
        Validate corpus configurations without making changes.

        Returns:
            Dictionary with validation results
        """
        logger.info("Checking corpus configurations...")

        # Validate configurations
        validation_errors = corpus.validate_corpus_configs()

        # Get configured corpora
        all_configs = corpus.get_all_corpus_configs()
        enabled_configs = corpus.get_enabled_corpus_configs()

        # Check which data files exist
        data_dir = constants.WORDFREQ_DATA_DIR

        file_status = []
        for config in all_configs:
            full_path = os.path.join(data_dir, config.file_path)
            exists = os.path.exists(full_path)
            file_status.append(
                {
                    "corpus_name": config.name,
                    "file_path": config.file_path,
                    "full_path": full_path,
                    "exists": exists,
                    "enabled": config.enabled,
                }
            )

        # Check database state
        session = self.get_session()
        try:
            from storage.models.schema import Corpus

            db_corpora = session.query(Corpus).all()
            db_corpus_info = [
                {
                    "name": c.name,
                    "description": c.description,
                    "enabled": c.enabled,
                    "corpus_weight": c.corpus_weight,
                    "max_unknown_rank": c.max_unknown_rank,
                }
                for c in db_corpora
            ]
        except Exception as e:
            logger.warning(f"Could not query database corpora: {e}")
            db_corpus_info = []
        finally:
            session.close()

        result = {
            "validation_errors": validation_errors,
            "is_valid": len(validation_errors) == 0,
            "total_configs": len(all_configs),
            "enabled_configs": len(enabled_configs),
            "config_details": [
                {
                    "name": c.name,
                    "description": c.description,
                    "enabled": c.enabled,
                    "corpus_weight": c.corpus_weight,
                    "max_words": c.max_words,
                    "file_path": c.file_path,
                }
                for c in all_configs
            ],
            "file_status": file_status,
            "database_corpora": db_corpus_info,
        }

        logger.info(f"Configuration check complete: {len(validation_errors)} errors found")
        return result

    def sync_configurations(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Synchronize corpus configurations from config file to database.

        Args:
            dry_run: If True, report what would be done without making changes

        Returns:
            Dictionary with sync results
        """
        logger.info(f"Synchronizing corpus configurations (dry_run={dry_run})...")

        if dry_run:
            # For dry run, just check what would change
            session = self.get_session()
            try:
                from storage.models.schema import Corpus

                # Get existing corpora
                existing_corpora = {c.name: c for c in session.query(Corpus).all()}
                config_names = {c.name for c in corpus.CORPUS_CONFIGS}

                would_add = []
                would_update = []
                would_disable = []

                # Check what would be added or updated
                for config in corpus.CORPUS_CONFIGS:
                    if config.name in existing_corpora:
                        db_corpus = existing_corpora[config.name]
                        changes = []

                        if db_corpus.description != config.description:
                            changes.append(
                                f"description: '{db_corpus.description}' -> '{config.description}'"
                            )
                        if db_corpus.corpus_weight != config.corpus_weight:
                            changes.append(
                                f"corpus_weight: {db_corpus.corpus_weight} -> {config.corpus_weight}"
                            )
                        if db_corpus.max_unknown_rank != config.max_unknown_rank:
                            changes.append(
                                f"max_unknown_rank: {db_corpus.max_unknown_rank} -> {config.max_unknown_rank}"
                            )
                        if db_corpus.enabled != config.enabled:
                            changes.append(f"enabled: {db_corpus.enabled} -> {config.enabled}")

                        if changes:
                            would_update.append({"name": config.name, "changes": changes})
                    else:
                        would_add.append(
                            {
                                "name": config.name,
                                "description": config.description,
                                "enabled": config.enabled,
                            }
                        )

                # Check what would be disabled
                for corpus_name, db_corpus in existing_corpora.items():
                    if corpus_name not in config_names and db_corpus.enabled:
                        would_disable.append(
                            {"name": corpus_name, "description": db_corpus.description}
                        )

                result = {
                    "dry_run": True,
                    "would_add": would_add,
                    "would_update": would_update,
                    "would_disable": would_disable,
                    "added_count": len(would_add),
                    "updated_count": len(would_update),
                    "disabled_count": len(would_disable),
                }

            finally:
                session.close()
        else:
            # Actually perform the sync
            session = self.get_session()
            try:
                result = corpus.sync_corpus_configs_to_db(session)
                result["dry_run"] = False
            finally:
                session.close()

        logger.info(
            f"Sync complete: {result.get('added_count', 0)} added, "
            f"{result.get('updated_count', 0)} updated, "
            f"{result.get('disabled_count', 0)} disabled"
        )
        return result

    def load_corpora(
        self, corpus_names: Optional[List[str]] = None, dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Load corpus data into the database.

        Args:
            corpus_names: Optional list of specific corpus names to load (loads all enabled if None)
            dry_run: If True, report what would be loaded without loading

        Returns:
            Dictionary with load results
        """
        logger.info(f"Loading corpora (dry_run={dry_run})...")

        # Get corpora to load
        configs_to_load: List[Any]  # Actually CorpusConfig, but avoiding import
        if corpus_names:
            maybe_configs = [corpus.get_corpus_config(name) for name in corpus_names]
            configs_to_load = [c for c in maybe_configs if c is not None]
            if len(configs_to_load) != len(corpus_names):
                missing = set(corpus_names) - {c.name for c in configs_to_load}
                logger.warning(f"Some corpus names not found in config: {missing}")
        else:
            configs_to_load = corpus.get_enabled_corpus_configs()

        if dry_run:
            data_dir = constants.WORDFREQ_DATA_DIR

            plan = []
            for config in configs_to_load:
                full_path = os.path.join(data_dir, config.file_path)
                exists = os.path.exists(full_path)

                plan.append(
                    {
                        "corpus_name": config.name,
                        "file_path": full_path,
                        "file_exists": exists,
                        "max_words": config.max_words,
                        "enabled": config.enabled,
                        "ready": exists and config.enabled,
                    }
                )

            result = {
                "dry_run": True,
                "corpora_to_load": plan,
                "total_count": len(plan),
                "ready_count": sum(1 for p in plan if p["ready"]),
            }
        else:
            # Actually load the corpora
            results: Dict[str, Dict[str, Any]] = {}
            errors: List[str] = []

            for corpus_config in configs_to_load:
                session = self.get_session()
                try:
                    logger.info(f"Loading corpus: {corpus_config.name}")
                    imported, total = corpus.load_corpus(session, corpus_config.name)
                    results[corpus_config.name] = {
                        "imported": imported,
                        "total": total,
                        "success": True,
                    }
                    logger.info(
                        f"Successfully loaded {corpus_config.name}: {imported}/{total} words"
                    )
                except Exception as e:
                    error_msg = f"Failed to load corpus {corpus_config.name}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    results[corpus_config.name] = {
                        "imported": 0,
                        "total": 0,
                        "success": False,
                        "error": str(e),
                    }
                finally:
                    session.close()

            result = {
                "dry_run": False,
                "results": results,
                "errors": errors,
                "total_corpora": len(configs_to_load),
                "successful_corpora": sum(1 for r in results.values() if r["success"]),
            }

        logger.info(f"Corpus loading complete")
        return result

    def import_tiers(self, dry_run: bool = False) -> Dict[str, Any]:
        """Run every English tier importer (YLE, CEFR, Basic English).

        Each importer reads its default data file under ``data/`` and writes
        ``ExternalLexemeAnnotation`` + ``LemmaTier`` rows. ``run_import``
        bootstraps any missing TierDefinition rows for its source.
        """
        logger.info(f"Importing tier annotations (dry_run={dry_run})...")
        importers: List[TierImporter] = [
            CambridgeYleImporter(),
            CefrImporter(),
            BasicEnglishImporter(),
        ]
        per_source: Dict[str, Dict[str, Any]] = {}
        for importer in importers:
            session = self.get_session()
            try:
                report = run_tier_import(session, importer, dry_run=dry_run)
                per_source[importer.source] = {
                    "total": report.total,
                    "annotations_inserted": report.annotations_inserted,
                    "annotations_updated": report.annotations_updated,
                    "lemma_links_inserted": report.lemma_links_inserted,
                    "lemma_tiers_inserted": report.lemma_tiers_inserted,
                    "lemma_tiers_updated": report.lemma_tiers_updated,
                    "unattached": report.unattached,
                    "unknown_tier_names": report.unknown_tier_names,
                }
            except Exception as e:
                logger.error(f"Tier import failed for {importer.source}: {e}")
                per_source[importer.source] = {"success": False, "error": str(e)}
            finally:
                session.close()
        return {"dry_run": dry_run, "success": True, "sources": per_source}

    def calculate_ranks(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Calculate combined ranks for all words across corpora.

        Args:
            dry_run: If True, report what would be done without calculating

        Returns:
            Dictionary with calculation results
        """
        logger.info(f"Calculating combined ranks (dry_run={dry_run})...")

        result: Dict[str, Any]
        if dry_run:
            session = self.get_session()
            try:
                from storage.models.schema import (
                    ExternalLexemeAnnotation,
                    Lemma,
                    LemmaTier,
                )

                lemma_count = session.query(Lemma).count()
                annotation_count = session.query(ExternalLexemeAnnotation).count()
                tier_count = session.query(LemmaTier).count()

                result = {
                    "dry_run": True,
                    "lemmas": lemma_count,
                    "external_lexeme_annotations": annotation_count,
                    "lemma_tiers": tier_count,
                    "would_calculate": True,
                }
            finally:
                session.close()
        else:
            session = self.get_session()
            try:
                logger.info("Calculating lemma combined ranks (lexeme + tier sources)...")
                rank_result = combined_rank.calculate_lemma_combined_ranks(session)
                result = {
                    "dry_run": False,
                    "success": rank_result.get("success", False),
                    "lemmas_updated": rank_result.get("lemmas_updated", 0),
                    "lemmas_scored": rank_result.get("lemmas_scored", 0),
                    "lemmas_skipped": rank_result.get("lemmas_skipped", 0),
                    "sources_used": rank_result.get("sources_used", []),
                    "message": "Combined ranks calculated successfully",
                }
                logger.info("Combined ranks calculation completed!")
            except Exception as e:
                error_msg = f"Failed to calculate combined ranks: {e}"
                logger.error(error_msg)
                result = {"dry_run": False, "success": False, "error": str(e)}
            finally:
                session.close()

        return result

    def bootstrap_from_json(
        self, json_path: str, update_difficulty: bool = True, dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Bootstrap the database with trakaido data from JSON export.

        This operation is intended for initial database setup only. If words with Lithuanian
        translations already exist in the database, the operation will be aborted to prevent
        accidental modifications to existing data.

        Args:
            json_path: Path to JSON file containing trakaido data
            update_difficulty: Whether to update difficulty level on existing lemmas (default: True)
            dry_run: If True, report what would be done without making changes

        Returns:
            Dictionary with bootstrap results
        """
        logger.info(f"Bootstrap from JSON (dry_run={dry_run})...")
        start_time = datetime.now()

        # Step 1: Check if database already has Lithuanian translations
        session = self.get_session()
        try:
            from storage.models.schema import Lemma

            # Count lemmas with Lithuanian translations
            existing_lithuanian_count = (
                session.query(Lemma).filter(has_translation_clause("lt")).count()
            )

            if existing_lithuanian_count > 0:
                logger.warning(
                    f"Database already contains {existing_lithuanian_count} lemmas with Lithuanian translations"
                )
                logger.warning(
                    "Bootstrap operation aborted to prevent accidental data modification"
                )
                return {
                    "success": False,
                    "aborted": True,
                    "reason": "database_already_populated",
                    "existing_lithuanian_count": existing_lithuanian_count,
                    "message": f"Database already contains {existing_lithuanian_count} lemmas with Lithuanian translations. Bootstrap is only for initial setup.",
                }

            logger.info("No existing Lithuanian translations found - proceeding with bootstrap")

        finally:
            session.close()

        # Step 2: Load and validate JSON data
        try:
            logger.info(f"Loading trakaido data from: {json_path}")
            trakaido_data = legacy_json_import.load_trakaido_json(json_path)

            result = {
                "dry_run": dry_run,
                "json_path": json_path,
                "json_entries_loaded": len(trakaido_data),
                "timestamp": start_time.isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to load JSON data: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to load JSON data from {json_path}",
            }

        if dry_run:
            # For dry run, just report what would happen
            result["would_migrate"] = len(trakaido_data)
            result["update_difficulty"] = update_difficulty
            result["message"] = f"Would migrate {len(trakaido_data)} entries from JSON"
        else:
            # Actually perform the migration
            session = self.get_session()
            try:
                logger.info(f"Migrating {len(trakaido_data)} entries to database...")
                successful, total = legacy_json_import.migrate_json_data(
                    session=session,
                    trakaido_data=trakaido_data,
                    update_difficulty=update_difficulty,
                    verbose=False,  # Use logging instead of print statements
                )

                # Commit the changes
                session.commit()

                result["successful_migrations"] = successful
                result["total_entries"] = total
                result["failed_migrations"] = total - successful
                result["success"] = successful > 0

                logger.info(f"Bootstrap complete: {successful}/{total} entries migrated")

            except Exception as e:
                logger.error(f"Bootstrap failed: {e}")
                session.rollback()
                result["success"] = False
                result["error"] = str(e)
            finally:
                session.close()

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        result["duration_seconds"] = duration

        return result

    def initialize_database(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Perform complete database initialization.

        This includes:
        1. Ensuring database tables exist
        2. Syncing corpus configurations
        3. Loading all enabled corpora
        4. Calculating combined ranks

        Args:
            dry_run: If True, report what would be done without making changes

        Returns:
            Dictionary with initialization results
        """
        logger.info(f"Starting full database initialization (dry_run={dry_run})...")
        start_time = datetime.now()

        results: Dict[str, Any] = {
            "timestamp": start_time.isoformat(),
            "database_path": self.db_path,
            "dry_run": dry_run,
        }

        # Step 1: Ensure tables exist (only if not dry run)
        if not dry_run:
            logger.info("Step 1: Ensuring database tables exist...")
            session = self.get_session()
            try:
                ensure_tables_exist(session)
                initialize_corpora(session)
                results["tables_initialized"] = True
            except Exception as e:
                logger.error(f"Failed to initialize tables: {e}")
                results["tables_initialized"] = False
                results["error"] = str(e)
                return results
            finally:
                session.close()
        else:
            results["tables_initialized"] = "skipped (dry_run)"

        # Step 2: Sync corpus configurations
        logger.info("Step 2: Syncing corpus configurations...")
        results["config_sync"] = self.sync_configurations(dry_run=dry_run)

        # Step 3: Load corpora
        logger.info("Step 3: Loading enabled corpora...")
        results["corpus_load"] = self.load_corpora(dry_run=dry_run)

        # Step 4: Import tier annotations (YLE / CEFR / Basic English)
        logger.info("Step 4: Importing tier annotations...")
        results["tier_import"] = self.import_tiers(dry_run=dry_run)

        # Step 5: Calculate ranks
        logger.info("Step 5: Calculating combined ranks...")
        results["rank_calculation"] = self.calculate_ranks(dry_run=dry_run)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        results["duration_seconds"] = duration

        logger.info(f"Database initialization complete in {duration:.2f} seconds")
        return results

    def run_check(self, output_file: Optional[str] = None) -> Dict[str, Any]:
        """
        Run configuration check and generate report.

        Args:
            output_file: Optional path to write JSON report

        Returns:
            Dictionary with check results
        """
        logger.info("Running configuration check...")
        start_time = datetime.now()

        results: Dict[str, Any] = {
            "timestamp": start_time.isoformat(),
            "database_path": self.db_path,
            "check": self.check_configuration(),
        }

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        results["duration_seconds"] = duration

        # Print summary
        self._print_check_summary(results)

        # Write to output file if requested
        if output_file:
            import json

            try:
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)
                logger.info(f"Report written to: {output_file}")
            except Exception as e:
                logger.error(f"Failed to write output file: {e}")

        return results

    def _print_check_summary(self, results: Dict[str, Any]) -> None:
        """Print a summary of the check results."""
        check = results["check"]

        logger.info("=" * 80)
        logger.info("DATABASE ADMINISTRATION REPORT - Configuration Check")
        logger.info("=" * 80)
        logger.info(f"Timestamp: {results['timestamp']}")
        logger.info("")

        # Validation status
        if check["is_valid"]:
            logger.info("CONFIGURATION: VALID")
        else:
            logger.info("CONFIGURATION: INVALID")
            logger.info("Validation errors:")
            for error in check["validation_errors"]:
                logger.info(f"  - {error}")
        logger.info("")

        # Corpus summary
        logger.info(
            f"CONFIGURED CORPORA: {check['total_configs']} total, {check['enabled_configs']} enabled"
        )
        logger.info("")

        # File status
        logger.info("DATA FILES:")
        for file_info in check["file_status"]:
            status = "EXISTS" if file_info["exists"] else "MISSING"
            enabled = "enabled" if file_info["enabled"] else "disabled"
            logger.info(
                f"  [{status}] {file_info['corpus_name']} ({enabled}): {file_info['file_path']}"
            )
        logger.info("")

        # Database status
        logger.info(f"DATABASE CORPORA: {len(check['database_corpora'])} entries")
        for db_corpus in check["database_corpora"]:
            enabled = "enabled" if db_corpus["enabled"] else "disabled"
            logger.info(f"  - {db_corpus['name']} ({enabled}): {db_corpus['description']}")

        logger.info("=" * 80)
