#!/usr/bin/env python3
"""GEGUTE agent: idiom generation, equivalent population, and auditing.

The generation logic itself lives in ``idioms.generation``; execution belongs to
the capability handlers in ``workqueue.handlers.idioms``. This module is
responsible only for:

- Discovering which idioms need work (missing equivalents, unaudited rows).
- Reporting that coverage for a human.
- Running the work, either inline or by enqueueing capability tasks.

Per ``agents/WORKQUEUE_REFACTOR_PLAN.md`` the queue path emits canonical task
names (``idioms.generate``, ``idioms.equivalents.populate``,
``idioms.equivalents.validate``) rather than agent-prefixed ones, so nothing
downstream has to know this agent is called gegute.

"Gegute" means "cuckoo" in Lithuanian - a bird that places its charges in other
birds' nests, as an idiom places one language's meaning inside another's words.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from idioms.generation import (
    default_target_languages,
    generate_idioms_for_language,
    missing_languages_for_idiom,
    populate_equivalents_for_idiom,
    validate_equivalents_for_idiom,
)
from storage.backend.config import DataSourceConfig
from storage.crud.idiom import get_idiom_by_guid, list_idioms
from storage.models.idiom import Idiom

logger = logging.getLogger(__name__)


@dataclass
class IdiomCoverage:
    """What one idiom is missing, for reporting and work discovery."""

    idiom_id: int
    guid: Optional[str]
    expression: str
    source_language_code: str
    equivalent_count: int
    missing_languages: List[str]

    @property
    def is_complete(self) -> bool:
        return not self.missing_languages


class GeguteAgent:
    """Discovery and execution entry point for idiom work."""

    def __init__(
        self,
        config: Optional[DataSourceConfig] = None,
        debug: bool = False,
    ) -> None:
        self.config = config
        self.debug = debug
        if debug:
            logger.setLevel(logging.DEBUG)

    # ------------------------------------------------------------------ #
    # Discovery                                                          #
    # ------------------------------------------------------------------ #

    def select_idioms(
        self,
        session: Session,
        *,
        guid: Optional[str] = None,
        source_language: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Idiom]:
        """Return the idioms this run should consider.

        A ``guid`` selects exactly one idiom and ignores the other filters, so
        a single-item run is reproducible.
        """
        if guid:
            idiom = get_idiom_by_guid(session, guid)
            if idiom is None:
                logger.error("No idiom found with GUID: %s", guid)
                return []
            return [idiom]

        idioms, _ = list_idioms(session, source_language_code=source_language, limit=limit)
        return idioms

    def coverage(
        self,
        session: Session,
        *,
        guid: Optional[str] = None,
        source_language: Optional[str] = None,
        target_languages: Optional[Sequence[str]] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Report equivalent coverage without changing anything."""
        idioms = self.select_idioms(
            session, guid=guid, source_language=source_language, limit=limit
        )

        rows: List[IdiomCoverage] = []
        for idiom in idioms:
            targets = list(target_languages or default_target_languages(idiom.source_language_code))
            rows.append(
                IdiomCoverage(
                    idiom_id=idiom.id,
                    guid=idiom.guid,
                    expression=idiom.expression,
                    source_language_code=idiom.source_language_code,
                    equivalent_count=len(idiom.equivalents),
                    missing_languages=missing_languages_for_idiom(idiom, targets),
                )
            )

        incomplete = [row for row in rows if not row.is_complete]
        return {
            "total_idioms": len(rows),
            "complete": len(rows) - len(incomplete),
            "incomplete": len(incomplete),
            "missing_equivalent_slots": sum(len(row.missing_languages) for row in rows),
            "rows": rows,
        }

    # ------------------------------------------------------------------ #
    # Execution                                                          #
    # ------------------------------------------------------------------ #

    def generate(
        self,
        session: Session,
        language_code: str,
        *,
        count: int = 10,
        theme: Optional[str] = None,
        difficulty_level: int = -1,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Generate new idioms for one source language."""
        result = generate_idioms_for_language(
            session,
            language_code,
            config=self.config,
            count=count,
            theme=theme,
            difficulty_level=difficulty_level,
        )

        if not result.get("success"):
            session.rollback()
            return result

        if dry_run:
            session.rollback()
            result["dry_run"] = True
        else:
            session.commit()
        return result

    def populate(
        self,
        session: Session,
        idioms: Sequence[Idiom],
        *,
        target_languages: Optional[Sequence[str]] = None,
        only_missing: bool = True,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Fill in missing equivalents for each of ``idioms``.

        Commits per idiom so a mid-run failure keeps the work already done -
        an LLM call per idiom is the expensive part, and discarding earlier
        successes because a later call failed would waste it.
        """
        stored = 0
        failed: List[Dict[str, Any]] = []
        processed = 0

        for idiom in idioms:
            result = populate_equivalents_for_idiom(
                session,
                idiom,
                config=self.config,
                target_languages=target_languages,
                only_missing=only_missing,
            )
            processed += 1

            if not result.get("success"):
                session.rollback()
                failed.append(
                    {
                        "guid": idiom.guid,
                        "expression": idiom.expression,
                        "error": result.get("error"),
                    }
                )
                continue

            stored += result.get("stored", 0)
            if dry_run:
                session.rollback()
            else:
                session.commit()

        return {
            "success": True,
            "processed": processed,
            "stored": stored,
            "failed": failed,
            "dry_run": dry_run,
        }

    def validate(
        self,
        session: Session,
        idioms: Sequence[Idiom],
    ) -> Dict[str, Any]:
        """Audit stored equivalents for each of ``idioms``.

        Read-only: findings are returned for a human to act on. See
        ``idioms.generation.validate_equivalents_for_idiom`` for why the
        corrections are not applied automatically.
        """
        findings: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []
        checked = 0

        for idiom in idioms:
            result = validate_equivalents_for_idiom(session, idiom, config=self.config)

            if not result.get("success"):
                failed.append(
                    {
                        "guid": idiom.guid,
                        "expression": idiom.expression,
                        "error": result.get("error"),
                    }
                )
                continue

            checked += result.get("checked", 0)
            for problem in result.get("problems", []):
                findings.append(
                    {
                        "guid": idiom.guid,
                        "expression": idiom.expression,
                        **problem,
                    }
                )

        return {
            "success": True,
            "checked": checked,
            "findings": findings,
            "failed": failed,
        }
