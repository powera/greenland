"""
Lokys - English Lemma Validation Agent

⚠️  IMPORTANT: This agent has a custom Barsukas API in src/barsukas/routes/agents.py
    If you modify the public interface of this agent, you MUST update:
    - /agents/check-definition/<lemma_id> endpoint
    - /agents/apply-definition/<lemma_id> endpoint
    - /agents/check-disambiguation/<lemma_id> endpoint
    - /agents/apply-disambiguation/<lemma_id> endpoint
    Keep the API contract in sync to prevent runtime errors!

This agent runs autonomously to validate English-language properties:
1. Lemma forms are in proper dictionary/base form (e.g., "shoe" not "shoes")
2. English definitions are accurate and well-formed
3. POS types and subtypes are correct
4. Lemmas are properly disambiguated when English polysemy requires it

Note: The base concept label/definition can come from base.json inputs and may
not be English. LOKYS focuses on populating and validating the English lemma
text and definition when they are missing or need correction.

"Lokys" means "bear" in Lithuanian - thorough and careful in checking quality.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from wordfreq.storage.backend import create_session as create_backend_session
from wordfreq.storage.backend.config import DataSourceConfig
from wordfreq.storage.models.schema import Lemma
from wordfreq.storage.translation_helpers import get_translation
from wordfreq.tools.llm_validators import (
    suggest_disambiguation,
    validate_definition,
    validate_disambiguation_need,
    validate_lemma_form,
)

# Configure logging
logger = logging.getLogger(__name__)


class LokysAgent:
    """Agent for validating English lemma forms and properties."""

    disambiguation_confidence_threshold = 0.7

    def __init__(self, config: DataSourceConfig):
        """
        Initialize the Lokys agent.

        Args:
            config: DataSourceConfig with model, debug, and backend settings (required)
        """
        self.config = config
        self.debug = config.debug

        if self.debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self):
        """Get database session using backend abstraction."""
        return create_backend_session(self.config)

    def check_lemma_forms(
        self,
        limit: Optional[int] = None,
        sample_rate: float = 1.0,
        confidence_threshold: float = 0.7,
    ) -> Dict[str, any]:
        """
        Check that English lemma_text values are in proper lemma form.

        Args:
            limit: Maximum number of lemmas to check
            sample_rate: Fraction of lemmas to sample (0.0-1.0)
            confidence_threshold: Minimum confidence to flag issues

        Returns:
            Dictionary with check results
        """
        logger.info("Checking English lemma forms...")

        session = self.get_session()
        try:
            # Get lemmas with GUIDs (these are the curated ones)
            query = session.query(Lemma).filter(Lemma.guid.isnot(None)).order_by(Lemma.id)

            if limit:
                query = query.limit(limit)

            lemmas = query.all()
            logger.info(f"Found {len(lemmas)} lemmas to check")

            # Sample if needed
            if sample_rate < 1.0:
                import random

                sample_size = int(len(lemmas) * sample_rate)
                lemmas = random.sample(lemmas, sample_size)
                logger.info(f"Sampling {len(lemmas)} lemmas ({sample_rate*100:.0f}%)")

            # Validate lemma forms
            issues_found = []
            checked_count = 0

            for lemma in lemmas:
                checked_count += 1
                if checked_count % 10 == 0:
                    logger.info(f"Checked {checked_count}/{len(lemmas)} lemmas...")

                result = validate_lemma_form(lemma.lemma_text, lemma.pos_type, self.config.model)

                if not result["is_lemma"] and result["confidence"] >= confidence_threshold:
                    issues_found.append(
                        {
                            "guid": lemma.guid,
                            "current_lemma": lemma.lemma_text,
                            "suggested_lemma": result["suggested_lemma"],
                            "pos_type": lemma.pos_type,
                            "reason": result["reason"],
                            "confidence": result["confidence"],
                        }
                    )
                    logger.warning(
                        f"Lemma issue: '{lemma.lemma_text}' → '{result['suggested_lemma']}' "
                        f"({lemma.guid}, confidence: {result['confidence']:.2f})"
                    )

            logger.info(f"Found {len(issues_found)} lemmas with potential issues")

            return {
                "total_checked": checked_count,
                "issues_found": len(issues_found),
                "issue_rate": (len(issues_found) / checked_count * 100) if checked_count else 0,
                "issues": issues_found,
                "confidence_threshold": confidence_threshold,
            }

        except Exception as e:
            logger.error(f"Error checking lemma forms: {e}")
            return {
                "error": str(e),
                "total_checked": 0,
                "issues_found": 0,
                "issue_rate": 0,
                "issues": [],
            }
        finally:
            session.close()

    def check_definitions(
        self,
        limit: Optional[int] = None,
        sample_rate: float = 1.0,
        confidence_threshold: float = 0.7,
    ) -> Dict[str, any]:
        """
        Check that definition_text values are well-formed and appropriate.

        Args:
            limit: Maximum number of definitions to check
            sample_rate: Fraction of definitions to sample (0.0-1.0)
            confidence_threshold: Minimum confidence to flag issues

        Returns:
            Dictionary with check results
        """
        logger.info("Checking English definitions...")

        session = self.get_session()
        try:
            # Get lemmas with GUIDs (these are the curated ones)
            query = session.query(Lemma).filter(Lemma.guid.isnot(None)).order_by(Lemma.id)

            if limit:
                query = query.limit(limit)

            lemmas = query.all()
            logger.info(f"Found {len(lemmas)} lemmas to check")

            # Sample if needed
            if sample_rate < 1.0:
                import random

                sample_size = int(len(lemmas) * sample_rate)
                lemmas = random.sample(lemmas, sample_size)
                logger.info(f"Sampling {len(lemmas)} lemmas ({sample_rate*100:.0f}%)")

            # Validate definitions
            issues_found = []
            checked_count = 0

            for lemma in lemmas:
                checked_count += 1
                if checked_count % 10 == 0:
                    logger.info(f"Checked {checked_count}/{len(lemmas)} definitions...")

                result = validate_definition(
                    lemma.lemma_text,
                    lemma.definition_text or "",
                    lemma.pos_type,
                    self.config.model,
                    translation_language="Lithuanian",
                    translation_text=get_translation(session, lemma, "lt"),
                )

                if not result["is_valid"] and result["confidence"] >= confidence_threshold:
                    issues_found.append(
                        {
                            "guid": lemma.guid,
                            "lemma": lemma.lemma_text,
                            "current_definition": lemma.definition_text,
                            "suggested_definition": result["suggested_definition"],
                            "pos_type": lemma.pos_type,
                            "issues": result["issues"],
                            "confidence": result["confidence"],
                        }
                    )

                    # Update the database with the suggested definition
                    if result["suggested_definition"]:
                        old_definition = lemma.definition_text
                        lemma.definition_text = result["suggested_definition"]
                        session.commit()
                        logger.info(
                            f"Updated definition for '{lemma.lemma_text}' (GUID: {lemma.guid}): "
                            f"'{old_definition}' → '{result['suggested_definition']}'"
                        )
                    else:
                        logger.warning(
                            f"Definition issue: '{lemma.lemma_text}' (GUID: {lemma.guid}) - {', '.join(result['issues'])} "
                            f"(confidence: {result['confidence']:.2f}) - No suggested definition provided"
                        )

            logger.info(f"Found {len(issues_found)} definitions with potential issues")

            return {
                "total_checked": checked_count,
                "issues_found": len(issues_found),
                "issue_rate": (len(issues_found) / checked_count * 100) if checked_count else 0,
                "issues": issues_found,
                "confidence_threshold": confidence_threshold,
            }

        except Exception as e:
            logger.error(f"Error checking definitions: {e}")
            return {
                "error": str(e),
                "total_checked": 0,
                "issues_found": 0,
                "issue_rate": 0,
                "issues": [],
            }
        finally:
            session.close()

    def check_disambiguation(self, limit: Optional[int] = None) -> Dict[str, any]:
        """
        Check for lemmas that need disambiguation (parentheticals).

        Detects when multiple lemmas share the same base English word but have
        different translations, indicating they need parenthetical disambiguation
        like "mouse (animal)" vs "mouse (computer)".

        Args:
            limit: Maximum number of lemma groups to check

        Returns:
            Dictionary with check results including lemmas needing disambiguation
        """
        logger.info("Checking for lemmas needing disambiguation...")

        session = self.get_session()
        try:
            from sqlalchemy import func

            from wordfreq.storage.translation_helpers import get_supported_languages

            # Find lemma_text values that appear multiple times
            duplicates_query = (
                session.query(Lemma.lemma_text, func.count(Lemma.id).label("count"))
                .filter(Lemma.guid.isnot(None))  # Only curated lemmas
                .group_by(Lemma.lemma_text)
                .having(func.count(Lemma.id) > 1)
                .order_by(func.count(Lemma.id).desc())
            )

            if limit:
                duplicates_query = duplicates_query.limit(limit)

            duplicate_groups = duplicates_query.all()
            logger.info(f"Found {len(duplicate_groups)} lemma_text values with duplicates")

            # Get all supported languages
            supported_languages = get_supported_languages()

            issues = []
            total_checked = 0
            needs_disambiguation = 0

            for lemma_text, count in duplicate_groups:
                # Get all lemmas with this lemma_text
                lemmas = (
                    session.query(Lemma)
                    .filter(Lemma.lemma_text == lemma_text, Lemma.guid.isnot(None))
                    .all()
                )

                total_checked += len(lemmas)

                # Check if translations differ (indicating different meanings)
                translations_differ = False
                translation_map = {}

                for lemma in lemmas:
                    # Collect non-null translations for each lemma using the helper
                    lemma_translations = []
                    for lang_code in supported_languages.keys():
                        try:
                            translation = get_translation(session, lemma, lang_code)
                            if translation:
                                lemma_translations.append((lang_code, translation))
                        except ValueError:
                            # Language not supported, skip
                            continue

                    translation_map[lemma.guid] = lemma_translations

                # Compare translations across lemmas
                if len(translation_map) > 1:
                    guids = list(translation_map.keys())
                    for i in range(len(guids)):
                        for j in range(i + 1, len(guids)):
                            trans_i = dict(translation_map[guids[i]])
                            trans_j = dict(translation_map[guids[j]])

                            # Check if any shared language has different translations
                            for lang in set(trans_i.keys()) & set(trans_j.keys()):
                                if trans_i[lang] != trans_j[lang]:
                                    translations_differ = True
                                    break
                            if translations_differ:
                                break

                # If translations differ, check if lemmas have parentheticals
                if translations_differ:
                    missing_parentheticals = []
                    for lemma in lemmas:
                        has_parenthetical = "(" in lemma.lemma_text and ")" in lemma.lemma_text
                        if not has_parenthetical:
                            missing_parentheticals.append(
                                {
                                    "guid": lemma.guid,
                                    "lemma_text": lemma.lemma_text,
                                    "definition": (
                                        lemma.definition_text[:100]
                                        if lemma.definition_text
                                        else None
                                    ),
                                    "pos_type": lemma.pos_type,
                                    "disambiguation": lemma.disambiguation,
                                }
                            )

                    if missing_parentheticals:
                        needs_disambiguation += len(missing_parentheticals)
                        issues.append(
                            {
                                "lemma_text": lemma_text,
                                "total_count": count,
                                "missing_disambiguation": missing_parentheticals,
                                "all_guids": [l.guid for l in lemmas],
                            }
                        )

            logger.info(f"Checked {total_checked} lemmas in {len(duplicate_groups)} groups")
            logger.info(f"Found {needs_disambiguation} lemmas needing disambiguation")

            return {
                "total_checked": total_checked,
                "duplicate_groups": len(duplicate_groups),
                "needs_disambiguation": needs_disambiguation,
                "issues": issues,
            }

        except Exception as e:
            logger.error(f"Error checking disambiguation: {e}", exc_info=True)
            return {"error": str(e), "total_checked": 0, "needs_disambiguation": 0, "issues": []}
        finally:
            session.close()

    def run_full_check(
        self,
        output_file: Optional[str] = None,
        limit: Optional[int] = None,
        sample_rate: float = 1.0,
        confidence_threshold: float = 0.7,
        check_type: str = "both",
    ) -> Dict[str, any]:
        """
        Run English lemma validation and generate a comprehensive report.

        Args:
            output_file: Optional path to write JSON report
            limit: Maximum items to check
            sample_rate: Fraction to sample (0.0-1.0)
            confidence_threshold: Minimum confidence to flag issues
            check_type: Type of check to run ("lemma", "definitions", "disambiguation", or "both")

        Returns:
            Dictionary with all check results
        """
        logger.info("Starting English lemma validation check...")
        start_time = datetime.now()

        results = {
            "timestamp": start_time.isoformat(),
            "backend_type": str(self.config.backend_type),
            "model": self.config.model,
            "sample_rate": sample_rate,
            "confidence_threshold": confidence_threshold,
            "check_type": check_type,
            "checks": {},
        }

        # Check English lemma forms
        if check_type in ["lemma", "both"]:
            results["checks"]["lemma_forms"] = self.check_lemma_forms(
                limit=limit, sample_rate=sample_rate, confidence_threshold=confidence_threshold
            )

        # Check English definitions
        if check_type in ["definitions", "both"]:
            results["checks"]["definitions"] = self.check_definitions(
                limit=limit, sample_rate=sample_rate, confidence_threshold=confidence_threshold
            )

        # Check disambiguation
        if check_type in ["disambiguation", "both"]:
            results["checks"]["disambiguation"] = self.check_disambiguation(limit=limit)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        results["duration_seconds"] = duration

        # Print summary
        self._print_summary(results, start_time, duration)

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

    # === Barsukas Web Interface Helper Methods ===
    # These methods provide a simplified, single-lemma interface for the web UI

    def check_single_definition(self, lemma, session=None) -> Dict[str, any]:
        """
        Check the definition of a single lemma using LLM validation.

        This is a convenience method for the Barsukas web interface.
        See src/barsukas/routes/agents.py for usage.

        Args:
            lemma: Lemma object to check
            session: Optional database session (if None, uses internal session)

        Returns:
            Dictionary with validation result from validate_definition()
        """
        result = validate_definition(
            word=lemma.lemma_text,
            definition=lemma.definition_text or "",
            pos_type=lemma.pos_type,
            model=self.config.model,
        )
        return result

    def check_single_disambiguation(self, lemma, session) -> Dict[str, any]:
        """
        Check if a lemma needs disambiguation (parentheticals in lemma_text).

        This method finds other lemmas with the same lemma_text and checks if they
        have different translations, indicating different meanings that need disambiguation.

        This is a convenience method for the Barsukas web interface.
        See src/barsukas/routes/agents.py for usage.

        Args:
            lemma: Lemma object to check
            session: Database session

        Returns:
            Dictionary with:
            - needs_disambiguation: bool
            - duplicate_count: int
            - has_parenthetical: bool
            - duplicates: list of Lemma objects
            - translations_by_guid: dict mapping GUID to translations
            - llm_suggestions: dict from suggest_disambiguation (if applicable)
        """
        from wordfreq.storage.translation_helpers import get_supported_languages

        # Find duplicates
        duplicates = (
            session.query(Lemma)
            .filter(Lemma.lemma_text == lemma.lemma_text, Lemma.guid.isnot(None))
            .all()
        )

        if len(duplicates) <= 1:
            return self._check_polysemy_disambiguation(
                lemma=lemma, session=session, duplicate_count=len(duplicates)
            )

        # Get translations for all duplicates
        supported_languages = get_supported_languages()
        translations_by_guid = {}

        for dup in duplicates:
            translations = {}
            for lang_code in supported_languages.keys():
                try:
                    translation = get_translation(session, dup, lang_code)
                    if translation:
                        translations[lang_code] = translation
                except ValueError:
                    continue
            translations_by_guid[dup.guid] = translations

        # Check if translations differ
        translations_differ = False
        if len(translations_by_guid) > 1:
            guids = list(translations_by_guid.keys())
            for i in range(len(guids)):
                for j in range(i + 1, len(guids)):
                    trans_i = translations_by_guid[guids[i]]
                    trans_j = translations_by_guid[guids[j]]
                    for lang in set(trans_i.keys()) & set(trans_j.keys()):
                        if trans_i[lang] != trans_j[lang]:
                            translations_differ = True
                            break
                    if translations_differ:
                        break

        if not translations_differ:
            return self._check_polysemy_disambiguation(
                lemma=lemma,
                session=session,
                duplicate_count=len(duplicates),
                duplicates=duplicates,
                translations_by_guid=translations_by_guid,
                reason="translations_identical",
            )

        # Check if already has parentheticals
        has_parenthetical = "(" in lemma.lemma_text and ")" in lemma.lemma_text

        # Get LLM suggestions
        definitions_data = []
        for dup in duplicates:
            item = {
                "guid": dup.guid,
                "definition": dup.definition_text or "No definition",
                "translations": {},
            }
            for lang_code in supported_languages.keys():
                try:
                    trans = get_translation(session, dup, lang_code)
                    if trans:
                        item["translations"][lang_code] = trans
                except ValueError:
                    continue
            definitions_data.append(item)

        llm_result = suggest_disambiguation(
            word=lemma.lemma_text, definitions=definitions_data, model=self.config.model
        )

        return {
            "needs_disambiguation": True,
            "duplicate_count": len(duplicates),
            "has_parenthetical": has_parenthetical,
            "duplicates": duplicates,
            "translations_by_guid": translations_by_guid,
            "llm_suggestions": llm_result,
        }

    def _check_polysemy_disambiguation(
        self,
        lemma: Lemma,
        session,
        duplicate_count: int,
        duplicates: Optional[List[Lemma]] = None,
        translations_by_guid: Optional[Dict[str, Dict[str, str]]] = None,
        reason: str = "no_duplicates",
    ) -> Dict[str, any]:
        """Check for disambiguation needs when duplicates aren't sufficient."""
        from wordfreq.storage.translation_helpers import get_supported_languages

        has_parenthetical = "(" in lemma.lemma_text and ")" in lemma.lemma_text
        if has_parenthetical:
            return {
                "needs_disambiguation": False,
                "duplicate_count": duplicate_count,
                "reason": "already_disambiguated",
                "has_parenthetical": has_parenthetical,
                "duplicates": duplicates or [],
                "translations_by_guid": translations_by_guid or {},
            }

        supported_languages = get_supported_languages()
        translations = {}
        for lang_code in supported_languages.keys():
            try:
                translation = get_translation(session, lemma, lang_code)
                if translation:
                    translations[lang_code] = translation
            except ValueError:
                continue

        llm_result = validate_disambiguation_need(
            word=lemma.lemma_text,
            pos_type=lemma.pos_type,
            definition=lemma.definition_text or "",
            translations=translations,
            has_parenthetical=has_parenthetical,
            model=self.config.model,
        )

        needs_disambiguation = (
            llm_result.get("needs_disambiguation", False)
            and llm_result.get("confidence", 0.0) >= self.disambiguation_confidence_threshold
        )

        return {
            "needs_disambiguation": needs_disambiguation,
            "duplicate_count": duplicate_count,
            "reason": "polysemy_detected" if needs_disambiguation else reason,
            "has_parenthetical": has_parenthetical,
            "duplicates": duplicates or [],
            "translations_by_guid": translations_by_guid or {},
            "llm_suggestions": llm_result,
        }

    def _print_summary(self, results: Dict, start_time: datetime, duration: float):
        """Print a summary of the check results."""
        logger.info("=" * 80)
        logger.info("LOKYS AGENT REPORT - English Lemma Validation")
        logger.info("=" * 80)
        logger.info(f"Timestamp: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Model: {results['model']}")
        logger.info(f"Sample Rate: {results['sample_rate']*100:.0f}%")
        logger.info(f"Confidence Threshold: {results['confidence_threshold']}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info("")

        # Lemma forms check
        if "lemma_forms" in results["checks"]:
            lemma_check = results["checks"]["lemma_forms"]
            logger.info(f"ENGLISH LEMMA FORMS:")
            logger.info(f"  Total checked: {lemma_check['total_checked']}")
            logger.info(f"  Issues found: {lemma_check['issues_found']}")
            logger.info(f"  Issue rate: {lemma_check['issue_rate']:.1f}%")
            logger.info("")

        # Definitions check
        if "definitions" in results["checks"]:
            def_check = results["checks"]["definitions"]
            logger.info(f"ENGLISH DEFINITIONS:")
            logger.info(f"  Total checked: {def_check['total_checked']}")
            logger.info(f"  Issues found: {def_check['issues_found']}")
            logger.info(f"  Issue rate: {def_check['issue_rate']:.1f}%")
            logger.info("")

        # Disambiguation check
        if "disambiguation" in results["checks"]:
            dis_check = results["checks"]["disambiguation"]
            logger.info("DISAMBIGUATION:")
            logger.info(f"  Total checked: {dis_check['total_checked']}")
            logger.info(f"  Duplicate groups: {dis_check['duplicate_groups']}")
            logger.info(f"  Needs disambiguation: {dis_check['needs_disambiguation']}")
            logger.info("")

        logger.info("=" * 80)
