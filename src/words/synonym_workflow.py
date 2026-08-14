"""Orchestration for generating synonyms and alternative forms in bulk.

The per-lemma generation pipeline (prompt, LLM call, normalization, storage)
lives in :mod:`words.synonyms`; coverage discovery lives in
:mod:`words.synonym_coverage`. This module is the layer between them: it walks a
selection of lemmas, generates what is missing, and reports the totals. The
Šernas CLI supplies the selection, the confirmation prompts, and the rendering.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, cast

from storage.backend import create_session as create_backend_session
from storage.backend.config import DataSourceConfig
from storage.crud.grammar_fact import delete_grammar_fact
from storage.crud.operation_log import delete_synonym_scan_records
from storage.models.schema import Lemma
from words.lemma_selection import find_lemma_by_guid
from words.synonym_coverage import MissingSynonymLemma, MissingSynonymReport, find_missing_synonyms
from words.synonyms import generate_synonyms_for_lemma as _generate_synonyms_for_lemma

logger = logging.getLogger(__name__)

__all__ = [
    "SynonymFixResults",
    "SynonymWorkflow",
    "clear_synonym_records",
]

# Grammar facts derived from a synonym scan, cleared when regenerating.
_SCAN_DERIVED_GRAMMAR_FACTS = ("has_abbreviations", "has_expanded_forms")

# Lemmas listed individually in a dry-run preview before it is truncated.
DRY_RUN_PREVIEW_LIMIT: int = 10


@dataclass
class SynonymFixResults:
    """Totals from one :meth:`SynonymWorkflow.fix_missing_synonyms` run."""

    language_code: str
    total_needing_fix: int = 0
    processed: int = 0
    successful: int = 0
    failed: int = 0
    dry_run: bool = False
    # Populated on dry runs only: the first lemmas that would be processed.
    sample: List[MissingSynonymLemma] = field(default_factory=list)
    # Set when coverage discovery failed; nothing was generated.
    error: Optional[str] = None


def clear_synonym_records(session: Any, lemmas: Sequence[Lemma], language_code: str) -> None:
    """Forget that these lemmas were ever scanned, so they are generated again.

    Removes the scan records and the grammar facts derived from them, then
    commits. The stored synonyms themselves are left alone: regeneration
    overwrites them through the usual storage path.
    """
    for lemma in lemmas:
        for fact_name in _SCAN_DERIVED_GRAMMAR_FACTS:
            delete_grammar_fact(session, lemma.id, language_code, fact_name)
        delete_synonym_scan_records(session, lemma.id, language_code)
    session.commit()


class SynonymWorkflow:
    """Generates synonyms and alternative forms across multiple languages.

    ⚠️  IMPORTANT: Barsukas queues this work through
        ``/agents/generate-synonyms/<lemma_id>``; keep the task payload
        contract in sync when the public interface changes.
    """

    def __init__(self, config: DataSourceConfig):
        """Initialize the workflow.

        Args:
            config: DataSourceConfig with model, debug, and backend settings.
        """
        self.config = config
        self.debug = config.debug

        if self.debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self) -> Any:
        """Get database session using backend abstraction."""
        return create_backend_session(self.config)

    def check_missing_synonyms(
        self,
        lemmas: Optional[Sequence[Lemma]] = None,
        language_code: Optional[str] = None,
        form_type: Optional[str] = None,
    ) -> MissingSynonymReport:
        """Report which lemmas still need synonyms/alternative forms.

        Args:
            lemmas: Lemmas to check. If None, checks all curated lemmas.
            language_code: Language to check. If None, checks all languages.
            form_type: Form type to report as checked, or None for all types.

        Returns:
            The coverage report (see :mod:`words.synonym_coverage`).
        """
        session = self.get_session()
        try:
            return find_missing_synonyms(
                session,
                lemmas=lemmas,
                language_code=language_code,
                form_type=form_type,
            )
        finally:
            session.close()

    def generate_synonyms_for_lemma(
        self,
        lemma_id: int,
        language_code: str,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Generate synonyms and alternative forms for one lemma and language.

        Delegates to :func:`words.synonyms.generate_synonyms_for_lemma` and
        commits the session on success.

        Args:
            lemma_id: The lemma to generate for.
            language_code: The language to generate in.
            dry_run: If True, generate nothing and report what would happen.

        Returns:
            The generation result dict, or ``{"error": ...}`` on failure.
        """
        session = self.get_session()
        try:
            lemma = session.query(Lemma).get(lemma_id)
            if not lemma:
                return {"error": f"Lemma ID {lemma_id} not found"}

            result = _generate_synonyms_for_lemma(
                session=session,
                lemma=lemma,
                language_code=language_code,
                config=self.config,
                dry_run=dry_run,
            )

            if result.get("success"):
                session.commit()
            elif "error" in result:
                session.rollback()

            return cast(Dict[str, Any], result)

        except Exception as e:
            session.rollback()
            logger.exception(f"Error generating synonyms for lemma {lemma_id}: {e}")
            return {"error": str(e), "lemma_id": lemma_id, "language_code": language_code}
        finally:
            session.close()

    def fix_missing_synonyms(
        self,
        lemmas: Optional[Sequence[Lemma]] = None,
        language_code: Optional[str] = None,
        form_type: Optional[str] = None,
        limit: Optional[int] = None,
        throttle: float = 1.0,
        dry_run: bool = False,
    ) -> SynonymFixResults:
        """Generate the missing synonyms and alternative forms for lemmas.

        Args:
            lemmas: Lemmas to process. If None, processes all curated lemmas.
            language_code: Language to fix. Defaults to English.
            form_type: Form type to generate, or None for all types.
            limit: Maximum number of lemmas to process.
            throttle: Seconds to wait between LLM calls.
            dry_run: If True, report what would be generated and write nothing.

        Returns:
            A :class:`SynonymFixResults` with the run's totals.
        """
        if not language_code:
            language_code = "en"
            logger.info("No language specified, defaulting to English")

        report = self.check_missing_synonyms(
            lemmas=lemmas, language_code=language_code, form_type=form_type
        )
        if report.error:
            return SynonymFixResults(
                language_code=language_code, dry_run=dry_run, error=report.error
            )

        lemmas_missing = report.for_language(language_code)
        total_needs_fix = len(lemmas_missing)

        if total_needs_fix == 0:
            logger.info(f"No lemmas need synonyms/alternatives for {language_code}!")
            return SynonymFixResults(language_code=language_code, dry_run=dry_run)

        logger.info(
            f"Found {total_needs_fix} lemmas needing synonyms/alternatives for {language_code}"
        )

        lemmas_to_process = lemmas_missing[:limit] if limit else lemmas_missing
        if limit:
            logger.info(f"Processing limited to {limit} lemmas")

        if dry_run:
            logger.info(f"DRY RUN: Would process {len(lemmas_to_process)} lemmas:")
            for lemma_info in lemmas_to_process[:DRY_RUN_PREVIEW_LIMIT]:
                logger.info(
                    f"  - {lemma_info.english} -> {lemma_info.translation} "
                    f"(level {lemma_info.difficulty_level})"
                )
            if len(lemmas_to_process) > DRY_RUN_PREVIEW_LIMIT:
                logger.info(f"  ... and {len(lemmas_to_process) - DRY_RUN_PREVIEW_LIMIT} more")
            return SynonymFixResults(
                language_code=language_code,
                total_needing_fix=total_needs_fix,
                processed=len(lemmas_to_process),
                dry_run=True,
                sample=list(lemmas_to_process[:DRY_RUN_PREVIEW_LIMIT]),
            )

        results = SynonymFixResults(
            language_code=language_code,
            total_needing_fix=total_needs_fix,
            processed=len(lemmas_to_process),
        )
        session = self.get_session()
        try:
            for index, lemma_info in enumerate(lemmas_to_process, 1):
                logger.info(
                    f"\n[{index}/{len(lemmas_to_process)}] Processing: "
                    f"{lemma_info.english} -> {lemma_info.translation}"
                )

                lemma = find_lemma_by_guid(session, lemma_info.guid, error_on_missing=False)
                if not lemma:
                    logger.error(f"Could not find lemma with GUID {lemma_info.guid}")
                    results.failed += 1
                    continue

                result = self.generate_synonyms_for_lemma(
                    lemma_id=lemma.id, language_code=language_code, dry_run=False
                )

                if result.get("success"):
                    results.successful += 1
                    stored_synonyms = result.get("stored_synonyms", 0)
                    stored_alternatives = result.get("stored_abbreviations", 0) + result.get(
                        "stored_expanded_forms", 0
                    )
                    logger.info(
                        f"Successfully generated {stored_synonyms} synonyms "
                        f"and {stored_alternatives} alternatives"
                    )
                else:
                    results.failed += 1
                    logger.error(f"Failed: {result.get('error', 'Unknown error')}")

                if index < len(lemmas_to_process):
                    time.sleep(throttle)
        finally:
            session.close()

        logger.info(f"\n{'='*60}")
        logger.info("Fix complete:")
        logger.info(f"  Total needing fix: {results.total_needing_fix}")
        logger.info(f"  Processed: {results.processed}")
        logger.info(f"  Successful: {results.successful}")
        logger.info(f"  Failed: {results.failed}")
        logger.info(f"{'='*60}")

        return results
