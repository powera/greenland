#!/usr/bin/env python3
"""
Pradzia - Database Initialization Agent

This agent runs autonomously to initialize and maintain the wordfreq database,
including corpus configuration synchronization, data loading, and rank calculation.

"Pradzia" means "beginning" in Lithuanian - the starting point for all data!
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import constants
from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_output_args,
    get_data_source_config,
)
from wordfreq.frequency import analysis, corpus
from wordfreq.storage.backend import create_session as create_backend_session
from wordfreq.storage.backend.config import BackendType, DataSourceConfig
from wordfreq.storage.database import (
    create_database_session,
    ensure_tables_exist,
    initialize_corpora,
)
from wordfreq.storage.models.schema import Corpus  # Ensure Corpus model is imported
from wordfreq.trakaido import json_to_database

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class PradziaAgent:
    """Agent for database initialization and corpus management."""

    def __init__(self, config: DataSourceConfig):
        """
        Initialize the Pradzia agent.

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
        import os

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        data_dir = os.path.join(project_root, "src", "wordfreq", "data")

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
            from wordfreq.storage.models.schema import Corpus

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
                from wordfreq.storage.models.schema import Corpus

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
            import os

            project_root = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "..")
            )
            data_dir = os.path.join(project_root, "src", "wordfreq", "data")

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
                try:
                    logger.info(f"Loading corpus: {corpus_config.name}")
                    imported, total = corpus.load_corpus(corpus_config.name, config=self.config)
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

            result = {
                "dry_run": False,
                "results": results,
                "errors": errors,
                "total_corpora": len(configs_to_load),
                "successful_corpora": sum(1 for r in results.values() if r["success"]),
            }

        logger.info(f"Corpus loading complete")
        return result

    def calculate_ranks(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Calculate combined ranks for all words across corpora.

        Args:
            dry_run: If True, report what would be done without calculating

        Returns:
            Dictionary with calculation results
        """
        logger.info(f"Calculating combined ranks (dry_run={dry_run})...")

        if dry_run:
            # For dry run, just report what would happen
            session = self.get_session()
            try:
                from wordfreq.storage.models.schema import Corpus, WordFrequency, WordToken

                word_count = session.query(WordToken).count()
                freq_count = session.query(WordFrequency).count()
                corpus_count = session.query(Corpus).filter(Corpus.enabled == True).count()

                result = {
                    "dry_run": True,
                    "word_tokens": word_count,
                    "frequency_records": freq_count,
                    "enabled_corpora": corpus_count,
                    "would_calculate": True,
                }
            finally:
                session.close()
        else:
            # Actually calculate ranks
            try:
                logger.info("Calculating combined ranks using harmonic mean...")
                analysis.calculate_combined_ranks(config=self.config)

                result = {
                    "dry_run": False,
                    "success": True,
                    "message": "Combined ranks calculated successfully",
                }
                logger.info("Combined ranks calculation completed!")
            except Exception as e:
                error_msg = f"Failed to calculate combined ranks: {e}"
                logger.error(error_msg)
                result = {"dry_run": False, "success": False, "error": str(e)}

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
            from wordfreq.storage.models.schema import Lemma

            # Count lemmas with Lithuanian translations
            existing_lithuanian_count = (
                session.query(Lemma)
                .filter(Lemma.lithuanian_translation != None, Lemma.lithuanian_translation != "")
                .count()
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
            trakaido_data = json_to_database.load_trakaido_json(json_path)

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
                successful, total = json_to_database.migrate_json_data(
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

    def import_from_jsonl(self, jsonl_dir: str, dry_run: bool = False) -> Dict[str, Any]:
        """
        Import lemmas from JSONL files to SQLite database.

        Uses bulk operations to minimize round-trips for remote databases.

        Args:
            jsonl_dir: Path to JSONL data directory (e.g., data/release)
            dry_run: If True, only report what would be imported without writing

        Returns:
            Dictionary with import results
        """
        logger.info(f"Importing from JSONL directory: {jsonl_dir} (dry_run={dry_run})")
        start_time = datetime.now()

        from wordfreq.storage.backend import create_session as create_backend_session
        from wordfreq.storage.backend.config import BackendType, DataSourceConfig
        from wordfreq.storage.models.schema import Lemma as SQLLemma
        from wordfreq.storage.models.schema import LemmaTranslation

        result: Dict[str, Any] = {
            "dry_run": dry_run,
            "jsonl_dir": jsonl_dir,
            "sqlite_db": self.db_path,
        }

        # Create JSONL backend session (source)
        jsonl_config = DataSourceConfig(backend_type=BackendType.JSONL, jsonl_data_dir=jsonl_dir)
        jsonl_session = create_backend_session(jsonl_config)

        # Use existing SQLite session (destination)
        sqlite_session = self.get_session()

        try:
            # Stage 1: Read all lemmas from JSONL (in-memory, no DB round-trips)
            logger.info("Stage 1: Reading lemmas from JSONL files...")
            jsonl_lemmas = jsonl_session.query(SQLLemma).all()
            logger.info(f"Found {len(jsonl_lemmas)} lemmas in JSONL files")

            result["total_lemmas_found"] = len(jsonl_lemmas)

            if dry_run:
                result["message"] = f"Would import {len(jsonl_lemmas)} lemmas from JSONL"
                logger.info(f"DRY RUN: Would import {len(jsonl_lemmas)} lemmas")
                return result

            # Stage 2: Fetch existing GUIDs in one query
            logger.info("Stage 2: Fetching existing GUIDs from destination database...")
            existing_guids = set(
                guid for (guid,) in sqlite_session.query(SQLLemma.guid).all() if guid
            )
            logger.info(f"Found {len(existing_guids)} existing lemmas in destination")
            sqlite_session.commit()

            # Stage 3: Prepare lemmas for bulk insert (filter out existing)
            logger.info("Stage 3: Preparing lemmas for bulk insert...")
            lemmas_to_insert = []
            guid_to_jsonl_lemma = {}  # Map GUID to original lemma for translations

            for lemma in jsonl_lemmas:
                if lemma.guid and lemma.guid in existing_guids:
                    continue  # Skip existing

                guid_to_jsonl_lemma[lemma.guid] = lemma
                lemmas_to_insert.append(
                    {
                        "guid": lemma.guid,
                        "lemma_text": lemma.lemma_text,
                        "definition_text": lemma.definition_text,
                        "pos_type": lemma.pos_type,
                        "pos_subtype": lemma.pos_subtype,
                        "difficulty_level": lemma.difficulty_level,
                        "frequency_rank": lemma.frequency_rank,
                        "tags": lemma.tags,
                        "disambiguation": (
                            lemma.disambiguation if hasattr(lemma, "disambiguation") else None
                        ),
                        "confidence": lemma.confidence if hasattr(lemma, "confidence") else 0.0,
                        "verified": lemma.verified if hasattr(lemma, "verified") else False,
                        "notes": lemma.notes if hasattr(lemma, "notes") else None,
                    }
                )

            skipped_count = len(jsonl_lemmas) - len(lemmas_to_insert)
            logger.info(
                f"Prepared {len(lemmas_to_insert)} lemmas for insert, skipping {skipped_count} existing"
            )

            # Stage 4: Bulk insert lemmas
            if lemmas_to_insert:
                logger.info("Stage 4: Bulk inserting lemmas...")
                sqlite_session.bulk_insert_mappings(SQLLemma, lemmas_to_insert)
                sqlite_session.commit()
                logger.info(f"Inserted {len(lemmas_to_insert)} lemmas")

            # Stage 5: Fetch back the inserted lemma IDs by GUID
            logger.info("Stage 5: Fetching inserted lemma IDs...")
            inserted_guids = list(guid_to_jsonl_lemma.keys())
            guid_to_new_id = {}

            if inserted_guids:
                # Query in batches to avoid overly large IN clauses
                batch_size = 500
                for i in range(0, len(inserted_guids), batch_size):
                    batch_guids = inserted_guids[i : i + batch_size]
                    rows = (
                        sqlite_session.query(SQLLemma.guid, SQLLemma.id)
                        .filter(SQLLemma.guid.in_(batch_guids))
                        .all()
                    )
                    for guid, lemma_id in rows:
                        guid_to_new_id[guid] = lemma_id

            sqlite_session.commit()
            logger.info(f"Mapped {len(guid_to_new_id)} GUIDs to new IDs")

            # Stage 6: Prepare translations for bulk insert
            logger.info("Stage 6: Preparing translations for bulk insert...")
            translations_to_insert = []

            # Get all translations from JSONL in one query
            all_jsonl_translations = jsonl_session.query(LemmaTranslation).all()

            # Build a map from jsonl lemma_id to translations
            jsonl_lemma_id_to_translations: Dict[int, List[Any]] = {}
            for trans in all_jsonl_translations:
                if trans.lemma_id not in jsonl_lemma_id_to_translations:
                    jsonl_lemma_id_to_translations[trans.lemma_id] = []
                jsonl_lemma_id_to_translations[trans.lemma_id].append(trans)

            # Map translations to new lemma IDs
            for guid, jsonl_lemma in guid_to_jsonl_lemma.items():
                new_lemma_id = guid_to_new_id.get(guid)
                if not new_lemma_id:
                    continue

                jsonl_translations = jsonl_lemma_id_to_translations.get(jsonl_lemma.id, [])
                for trans in jsonl_translations:
                    translations_to_insert.append(
                        {
                            "lemma_id": new_lemma_id,
                            "language_code": trans.language_code,
                            "translation": trans.translation,
                            "verified": trans.verified if hasattr(trans, "verified") else False,
                        }
                    )

            logger.info(f"Prepared {len(translations_to_insert)} translations for insert")

            # Stage 7: Bulk insert translations
            if translations_to_insert:
                logger.info("Stage 7: Bulk inserting translations...")
                sqlite_session.bulk_insert_mappings(LemmaTranslation, translations_to_insert)
                sqlite_session.commit()
                logger.info(f"Inserted {len(translations_to_insert)} translations")

            result["lemmas_imported"] = len(lemmas_to_insert)
            result["lemmas_skipped"] = skipped_count
            result["translations_imported"] = len(translations_to_insert)
            result["success"] = True

            logger.info(
                f"Import complete: {len(lemmas_to_insert)} lemmas, "
                f"{len(translations_to_insert)} translations imported"
            )

        except Exception as e:
            logger.error(f"Error during import: {e}")
            sqlite_session.rollback()
            result["success"] = False
            result["error"] = str(e)
        finally:
            jsonl_session.close()
            sqlite_session.close()

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

        # Step 4: Calculate ranks
        logger.info("Step 4: Calculating combined ranks...")
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
        logger.info("PRADZIA AGENT REPORT - Configuration Check")
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


def get_argument_parser() -> argparse.ArgumentParser:
    """Return the argument parser for introspection.

    This function allows external tools to introspect the available
    command-line arguments without executing the main function.
    """
    parser = argparse.ArgumentParser(description="Pradzia - Database Initialization Agent")

    # Common arguments
    add_common_args(parser)
    add_backend_args(parser)
    add_output_args(parser)

    # Mode selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--check", action="store_true", help="Check configuration and database state (no changes)"
    )
    mode_group.add_argument(
        "--sync-config", action="store_true", help="Sync corpus configurations to database"
    )
    mode_group.add_argument(
        "--load",
        nargs="*",
        metavar="CORPUS",
        help="Load specified corpora (or all enabled if none specified)",
    )
    mode_group.add_argument("--calc-ranks", action="store_true", help="Calculate combined ranks")
    mode_group.add_argument(
        "--init-full", action="store_true", help="Full initialization (sync + load + calc ranks)"
    )
    mode_group.add_argument(
        "--bootstrap",
        metavar="JSON_PATH",
        help="Bootstrap database from trakaido JSON export (initial setup only)",
    )
    mode_group.add_argument(
        "--import-jsonl",
        metavar="JSONL_DIR",
        help="Import lemmas from JSONL files to SQLite database",
    )

    # Bootstrap-specific options
    parser.add_argument(
        "--no-update-difficulty",
        action="store_true",
        help="Do not update difficulty levels on existing lemmas (only with --bootstrap)",
    )

    return parser


def main() -> None:
    """Main entry point for the pradzia agent."""
    parser = get_argument_parser()
    args = parser.parse_args()

    # Create configuration from args (always returns a valid config with defaults)
    config = get_data_source_config(args)

    agent = PradziaAgent(config=config)

    if args.check:
        agent.run_check(output_file=args.output)

    elif args.sync_config:
        result = agent.sync_configurations(dry_run=args.dry_run)
        if args.output:
            import json

            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

        if not args.dry_run:
            print(
                f"\nSynced: {result['added_count']} added, "
                f"{result['updated_count']} updated, "
                f"{result['disabled_count']} disabled"
            )

    elif args.load is not None:
        corpus_names = args.load if args.load else None
        result = agent.load_corpora(corpus_names=corpus_names, dry_run=args.dry_run)

        if args.output:
            import json

            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

        if not args.dry_run:
            print(f"\nLoaded {result['successful_corpora']}/{result['total_corpora']} corpora")

    elif args.calc_ranks:
        result = agent.calculate_ranks(dry_run=args.dry_run)

        if args.output:
            import json

            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

        if not args.dry_run and result.get("success"):
            print("\nCombined ranks calculated successfully")

    elif args.init_full:
        result = agent.initialize_database(dry_run=args.dry_run)

        if args.output:
            import json

            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"\nInitialization complete in {result['duration_seconds']:.2f} seconds")

    elif args.bootstrap:
        update_difficulty = not args.no_update_difficulty
        result = agent.bootstrap_from_json(
            json_path=args.bootstrap, update_difficulty=update_difficulty, dry_run=args.dry_run
        )

        if args.output:
            import json

            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

        if result.get("aborted"):
            print(f"\n⚠️  Bootstrap aborted: {result['message']}")
        elif result.get("success"):
            if not args.dry_run:
                print(
                    f"\n✅ Bootstrap complete: {result['successful_migrations']}/{result['total_entries']} entries migrated"
                )
                print(f"   Duration: {result['duration_seconds']:.2f} seconds")
            else:
                print(f"\n✅ Dry run: Would migrate {result['would_migrate']} entries")
        else:
            error_msg = result.get("error", "Unknown error")
            print(f"\n❌ Bootstrap failed: {error_msg}")

    elif args.import_jsonl:
        result = agent.import_from_jsonl(jsonl_dir=args.import_jsonl, dry_run=args.dry_run)

        if args.output:
            import json

            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

        if result.get("success"):
            if not args.dry_run:
                print(
                    f"\n✅ Import complete: {result['lemmas_imported']} lemmas, "
                    f"{result['translations_imported']} translations imported"
                )
                print(f"   Skipped (already exist): {result['lemmas_skipped']}")
                print(f"   Duration: {result['duration_seconds']:.2f} seconds")
            else:
                print(f"\n✅ Dry run: Would import {result['total_lemmas_found']} lemmas")
        else:
            error_msg = result.get("error", "Unknown error")
            print(f"\n❌ Import failed: {error_msg}")

    else:
        # Default: run check
        agent.run_check(output_file=args.output)


if __name__ == "__main__":
    main()
