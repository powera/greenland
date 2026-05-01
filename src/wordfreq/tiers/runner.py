"""Shared import driver for tier sources.

Loads entries from a TierImporter, resolves each one against the database,
upserts LemmaTier rows for matched entries, and queues the rest for review.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from storage.models.imports import PendingImport
from storage.models.schema import LemmaTier, TierDefinition
from wordfreq.tiers.base import ResolveStatus, TierEntry, TierImporter
from wordfreq.tiers.bootstrap import bootstrap_tier_definitions

logger = logging.getLogger(__name__)


@dataclass
class ImportReport:
    """Summary of a tier import run."""

    source: str
    total: int = 0
    matched: int = 0
    ambiguous: int = 0
    unmatched: int = 0
    upserts_inserted: int = 0
    upserts_updated: int = 0
    queued_for_review: int = 0
    unknown_tier_names: List[str] = field(default_factory=list)
    examples: Dict[str, List[str]] = field(default_factory=dict)

    def add_example(self, bucket: str, label: str, limit: int = 5) -> None:
        self.examples.setdefault(bucket, [])
        if len(self.examples[bucket]) < limit:
            self.examples[bucket].append(label)


def _known_tier_names(session: Session, source: str) -> set[str]:
    return {
        row.tier_name
        for row in session.query(TierDefinition).filter(TierDefinition.source == source).all()
    }


def _upsert_lemma_tier(
    session: Session,
    *,
    lemma_id: int,
    source: str,
    tier_name: str,
    themes: tuple[str, ...],
) -> bool:
    """Insert or update a LemmaTier row. Returns True if a new row was inserted."""
    themes_json = json.dumps(list(themes)) if themes else None
    existing = (
        session.query(LemmaTier)
        .filter(LemmaTier.lemma_id == lemma_id, LemmaTier.source == source)
        .first()
    )
    if existing is None:
        session.add(
            LemmaTier(
                lemma_id=lemma_id,
                source=source,
                tier_name=tier_name,
                themes=themes_json,
            )
        )
        return True
    existing.tier_name = tier_name
    existing.themes = themes_json
    return False


def _queue_for_review(session: Session, source: str, entry: TierEntry, reason: str) -> None:
    """Add a PendingImport row representing an unresolved tier entry.

    Uses the existing pending_imports table so reviewers see tier misses in the
    same place as other unresolved word imports. The disambiguation_translation
    field is set to the original word as a placeholder since these rows do not
    carry a foreign-language translation.
    """
    note_payload = {
        "tier_source": source,
        "tier_name": entry.tier_name,
        "pos_hint": entry.pos_hint,
        "sense_hint": entry.sense_hint,
        "themes": list(entry.themes),
        "reason": reason,
    }
    session.add(
        PendingImport(
            english_word=entry.word,
            definition=f"[tier:{source}:{entry.tier_name}] needs review: {reason}",
            disambiguation_translation=entry.word,
            disambiguation_language=entry.language_code,
            pos_type=entry.pos_hint,
            source=f"tier:{source}",
            notes=json.dumps(note_payload),
        )
    )


def run_import(
    session: Session,
    importer: TierImporter,
    *,
    bootstrap: bool = True,
    queue_unresolved: bool = True,
    dry_run: bool = False,
) -> ImportReport:
    """Run a tier importer end-to-end against the given session.

    Args:
        session: Database session (caller manages connection lifecycle).
        importer: A TierImporter implementation (e.g., CambridgeYleImporter).
        bootstrap: Insert any missing TierDefinition rows for the source first.
        queue_unresolved: Write PendingImport rows for ambiguous/unmatched entries.
        dry_run: If True, do not commit; the report still reflects intended changes.
    """
    source = importer.source
    if bootstrap:
        bootstrap_tier_definitions(session, sources=[source])

    known_tiers = _known_tier_names(session, source)
    entries = importer.load_entries()
    report = ImportReport(source=source, total=len(entries))

    for entry in entries:
        if entry.tier_name not in known_tiers:
            if entry.tier_name not in report.unknown_tier_names:
                report.unknown_tier_names.append(entry.tier_name)
            report.unmatched += 1
            report.add_example("unknown_tier", f"{entry.word} -> {entry.tier_name}")
            continue

        result = importer.resolve(session, entry)
        if result.status is ResolveStatus.MATCHED:
            inserted = _upsert_lemma_tier(
                session,
                lemma_id=result.lemma_ids[0],
                source=source,
                tier_name=entry.tier_name,
                themes=entry.themes,
            )
            report.matched += 1
            if inserted:
                report.upserts_inserted += 1
            else:
                report.upserts_updated += 1
        elif result.status is ResolveStatus.AMBIGUOUS:
            report.ambiguous += 1
            report.add_example("ambiguous", f"{entry.word} ({len(result.lemma_ids)} candidates)")
            if queue_unresolved:
                _queue_for_review(session, source, entry, result.reason or "ambiguous lemma match")
                report.queued_for_review += 1
        else:
            report.unmatched += 1
            report.add_example("unmatched", entry.word)
            if queue_unresolved:
                _queue_for_review(session, source, entry, result.reason or "no lemma match")
                report.queued_for_review += 1

    if dry_run:
        session.rollback()
    else:
        session.commit()

    logger.info(
        "tier import %s: total=%d matched=%d ambiguous=%d unmatched=%d "
        "(inserted=%d updated=%d queued=%d)",
        source,
        report.total,
        report.matched,
        report.ambiguous,
        report.unmatched,
        report.upserts_inserted,
        report.upserts_updated,
        report.queued_for_review,
    )
    return report
