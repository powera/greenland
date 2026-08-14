"""
Šernas - Synonym and Alternative Form Generator Agent

⚠️  IMPORTANT: This agent has a custom Barsukas API in src/barsukas/routes/agents.py
    If you modify the public interface of this agent, you MUST update:
    - /agents/generate-synonyms/<lemma_id> endpoint
    Keep the API contract in sync to prevent runtime errors!

This agent generates synonyms and alternative forms for lemmas across all supported
languages. The actual generation pipeline lives in :mod:`words.synonyms`; this
module owns batch orchestration (find-missing, throttled fix loops, CLI glue).

"Šernas" means "boar" in Lithuanian - persistent in finding similar things.
"""

import logging
import time
from typing import Any, Dict, List, Optional, cast

from words.lemma_selection import LemmaQueryBuilder, find_lemma_by_guid
from storage.backend import create_session as create_backend_session
from storage.backend.config import DataSourceConfig
from storage.crud.operation_log import has_synonym_scan_record
from storage.models.schema import Lemma
from storage.translation_helpers import get_supported_languages, get_translation
from words.synonyms import generate_synonyms_for_lemma as _generate_synonyms_for_lemma

logger = logging.getLogger(__name__)


class SernasAgent:
    """Agent for generating synonyms and alternative forms across multiple languages."""

    def __init__(self, config: DataSourceConfig):
        """
        Initialize the Šernas agent.

        Args:
            config: DataSourceConfig with model, debug, and backend settings (required)
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
        lemmas: Optional[List[Lemma]] = None,
        language_code: Optional[str] = None,
        form_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Check for lemmas missing synonyms or alternative forms.

        Args:
            lemmas: List of Lemma objects to check. If None, checks all curated lemmas.
            language_code: Language to check (e.g., 'en', 'lt'). If None, check all.
            form_type: Type to check (e.g., 'synonym', 'abbreviation', 'expanded_form').
                      If None, checks all types.

        Returns:
            Dictionary with check results
        """
        logger.info("Checking for lemmas missing synonyms/alternative forms...")

        session = self.get_session()
        try:
            if lemmas is None:
                query = LemmaQueryBuilder(session).curated_only().order_by_id().build()
                lemmas = query.all()
            logger.info(f"Checking {len(lemmas)} lemmas")

            if language_code:
                lang_codes = [language_code]
            else:
                lang_codes = ["en"] + list(get_supported_languages().keys())

            if form_type:
                form_types = [form_type]
            else:
                form_types = [
                    "synonym",
                    "abbreviation",
                    "expanded_form",
                ]

            missing_by_language: Dict[str, List[Dict[str, Any]]] = {lang: [] for lang in lang_codes}

            for lemma in lemmas:
                for lang in lang_codes:
                    if lang == "en":
                        translation: Optional[str] = lemma.lemma_text
                    else:
                        translation = get_translation(session, lemma, lang)

                    if not translation or not translation.strip():
                        continue

                    # We consider a lemma/language "processed" once ŠERNAS ran at least once.
                    if not has_synonym_scan_record(session, lemma.id, lang):
                        missing_by_language[lang].append(
                            {
                                "guid": lemma.guid,
                                "english": lemma.lemma_text,
                                "translation": translation,
                                "pos_type": lemma.pos_type,
                                "pos_subtype": lemma.pos_subtype,
                                "difficulty_level": lemma.difficulty_level,
                            }
                        )

            total_missing = sum(len(items) for items in missing_by_language.values())

            logger.info(
                f"Found {total_missing} lemmas missing synonyms/alternatives across all languages"
            )

            return {
                "total_missing": total_missing,
                "missing_by_language": missing_by_language,
                "checked_languages": lang_codes,
                "checked_form_types": form_types,
            }

        except Exception as e:
            logger.error(f"Error checking missing synonyms: {e}")
            return {"error": str(e), "total_missing": 0, "missing_by_language": {}}
        finally:
            session.close()

    def generate_synonyms_for_lemma(
        self,
        lemma_id: int,
        language_code: str,
        model: str = "gpt-5.4-mini",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate synonyms and alternative forms for a specific lemma and language.

        Delegates to :func:`words.synonyms.generate_synonyms_for_lemma` and
        commits the session on success.
        """
        _ = model  # model selection lives on DataSourceConfig now
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
        lemmas: Optional[List[Lemma]] = None,
        language_code: Optional[str] = None,
        form_type: Optional[str] = None,
        limit: Optional[int] = None,
        model: str = "gpt-5.4-mini",
        throttle: float = 1.0,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate missing synonyms and alternative forms for lemmas.

        Args:
            lemmas: List of Lemma objects to process. If None, processes all curated lemmas.
            language_code: Language to fix (e.g., 'en', 'lt'). If None, defaults to English.
            form_type: Type to generate ('synonym', 'abbreviation', or 'expanded_form').
            limit: Maximum number of lemmas to process
            model: LLM model to use
            throttle: Seconds to wait between API calls
            dry_run: If True, show what would be fixed without making changes

        Returns:
            Dictionary with fix results
        """
        if not language_code:
            language_code = "en"
            logger.info("No language specified, defaulting to English")

        check_results = self.check_missing_synonyms(
            lemmas=lemmas, language_code=language_code, form_type=form_type
        )

        if "error" in check_results:
            return check_results

        lemmas_missing = check_results["missing_by_language"].get(language_code, [])
        total_needs_fix = len(lemmas_missing)

        if total_needs_fix == 0:
            logger.info(f"No lemmas need synonyms/alternatives for {language_code}!")
            return {
                "total_needing_fix": 0,
                "processed": 0,
                "successful": 0,
                "failed": 0,
                "dry_run": dry_run,
            }

        logger.info(
            f"Found {total_needs_fix} lemmas needing synonyms/alternatives for {language_code}"
        )

        if limit:
            lemmas_to_process = lemmas_missing[:limit]
            logger.info(f"Processing limited to {limit} lemmas")
        else:
            lemmas_to_process = lemmas_missing

        if dry_run:
            logger.info(f"DRY RUN: Would process {len(lemmas_to_process)} lemmas:")
            for lemma_info in lemmas_to_process[:10]:
                logger.info(
                    f"  - {lemma_info['english']} -> {lemma_info['translation']} (level {lemma_info['difficulty_level']})"
                )
            if len(lemmas_to_process) > 10:
                logger.info(f"  ... and {len(lemmas_to_process) - 10} more")
            return {
                "total_needing_fix": total_needs_fix,
                "would_process": len(lemmas_to_process),
                "dry_run": True,
                "sample": lemmas_to_process[:10],
            }

        successful = 0
        failed = 0
        session = self.get_session()

        try:
            for i, lemma_info in enumerate(lemmas_to_process, 1):
                logger.info(
                    f"\n[{i}/{len(lemmas_to_process)}] Processing: {lemma_info['english']} -> {lemma_info['translation']}"
                )

                lemma = find_lemma_by_guid(session, lemma_info["guid"], error_on_missing=False)
                if not lemma:
                    logger.error(f"Could not find lemma with GUID {lemma_info['guid']}")
                    failed += 1
                    continue

                result = self.generate_synonyms_for_lemma(
                    lemma_id=lemma.id, language_code=language_code, model=model, dry_run=False
                )

                if result.get("success"):
                    successful += 1
                    stored_synonyms = result.get("stored_synonyms", 0)
                    stored_alternatives = result.get("stored_abbreviations", 0) + result.get(
                        "stored_expanded_forms", 0
                    )
                    logger.info(
                        f"Successfully generated {stored_synonyms} synonyms and {stored_alternatives} alternatives"
                    )
                else:
                    failed += 1
                    logger.error(f"Failed: {result.get('error', 'Unknown error')}")

                if i < len(lemmas_to_process):
                    time.sleep(throttle)

        finally:
            session.close()

        logger.info(f"\n{'='*60}")
        logger.info("Fix complete:")
        logger.info(f"  Total needing fix: {total_needs_fix}")
        logger.info(f"  Processed: {len(lemmas_to_process)}")
        logger.info(f"  Successful: {successful}")
        logger.info(f"  Failed: {failed}")
        logger.info(f"{'='*60}")

        return {
            "total_needing_fix": total_needs_fix,
            "processed": len(lemmas_to_process),
            "successful": successful,
            "failed": failed,
            "dry_run": dry_run,
            "language_code": language_code,
        }
