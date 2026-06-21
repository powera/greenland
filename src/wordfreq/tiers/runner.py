"""Shared import driver for tier sources.

For each TierEntry from an importer:

1. Get-or-create a WordToken for ``(entry.word, entry.language_code)``.
2. Upsert an ExternalLexemeAnnotation row keyed by
   ``(word_token_id, source, pos_hint, sense_hint)``.
3. Resolve to candidate Lemma ids via the importer.
4. For each candidate, upsert an ExternalLexemeAnnotationLemma row and a
   LemmaTier row.

The annotation row exists regardless of how many lemmas matched, so the
annotation table is itself the registry of "words this source knows about,
including ones with no lemma yet." Reconcile after lemma additions to attach
new candidates.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sqlalchemy import insert
from sqlalchemy.orm import Session

from storage.models.schema import (
    ExternalLexemeAnnotation,
    ExternalLexemeAnnotationLemma,
    LemmaTier,
    TierDefinition,
    WordToken,
)
from wordfreq.tiers.base import TierEntry, TierImporter
from wordfreq.tiers.bootstrap import bootstrap_tier_definitions

logger = logging.getLogger(__name__)


@dataclass
class ImportReport:
    """Summary of a tier import run."""

    source: str
    total: int = 0
    annotations_inserted: int = 0
    annotations_updated: int = 0
    lemma_links_inserted: int = 0
    lemma_tiers_inserted: int = 0
    lemma_tiers_updated: int = 0
    unattached: int = 0  # annotations with zero matched lemmas
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


@dataclass
class _ImportCaches:
    """In-memory lookup tables seeded once per import run.

    The per-entry helpers issue one SELECT each to decide insert-vs-update.
    For a large source (CEFR is ~10k entries) against the golden-mode in-memory
    DB those SELECTs dominate the runtime, and every one of them misses because
    the tables start empty. Seeding these maps from the current rows once lets
    the helpers answer "does this already exist?" without a query, while
    staying correct against an already-populated DB.
    """

    # (token_text, language_code) -> word_token_id
    word_token_ids: Dict[tuple[str, str], int] = field(default_factory=dict)
    # (word_token_id, source, pos_hint, sense_hint) -> ExternalLexemeAnnotation
    annotations: Dict[tuple[int, str, Optional[str], Optional[str]], ExternalLexemeAnnotation] = (
        field(default_factory=dict)
    )
    # set of (annotation_id, lemma_id) links that already exist
    lemma_links: set[tuple[int, int]] = field(default_factory=set)
    # (lemma_id, source) -> LemmaTier
    lemma_tiers: Dict[tuple[int, str], LemmaTier] = field(default_factory=dict)


def _build_import_caches(session: Session, source: str) -> _ImportCaches:
    """Preload existing rows relevant to ``source`` into in-memory maps."""
    caches = _ImportCaches()

    for token in session.query(WordToken).all():
        caches.word_token_ids[(token.token, token.language_code)] = token.id

    annotations = (
        session.query(ExternalLexemeAnnotation)
        .filter(ExternalLexemeAnnotation.source == source)
        .all()
    )
    annotation_ids: set[int] = set()
    for annotation in annotations:
        caches.annotations[
            (
                annotation.word_token_id,
                annotation.source,
                annotation.pos_hint,
                annotation.sense_hint,
            )
        ] = annotation
        annotation_ids.add(annotation.id)

    if annotation_ids:
        for link in (
            session.query(ExternalLexemeAnnotationLemma)
            .filter(ExternalLexemeAnnotationLemma.annotation_id.in_(annotation_ids))
            .all()
        ):
            caches.lemma_links.add((link.annotation_id, link.lemma_id))

    for tier in session.query(LemmaTier).filter(LemmaTier.source == source).all():
        caches.lemma_tiers[(tier.lemma_id, tier.source)] = tier

    return caches


def _bulk_create_word_tokens(
    session: Session,
    entries: List[TierEntry],
    caches: _ImportCaches,
) -> None:
    """Insert every WordToken an import needs in one bulk statement.

    All token texts are known up front, so rather than get-or-create (with a
    per-entry flush) inside the loop, we compute the set of tokens not already
    in the cache and insert them with a single ``bulk_insert_mappings``, then
    re-read their ids back into the cache. After this, ``_word_token_id`` is a
    pure dictionary lookup with no further flushes.
    """
    needed: set[tuple[str, str]] = {(entry.word, entry.language_code) for entry in entries}
    missing = sorted(needed - caches.word_token_ids.keys())
    if not missing:
        return

    session.execute(
        insert(WordToken),
        [{"token": token_text, "language_code": lang} for token_text, lang in missing],
    )
    session.flush()

    # Re-read the ids assigned to the rows we just inserted. Filtering by the
    # languages present keeps this to the tokens this source cares about.
    languages = {lang for _, lang in missing}
    for token in session.query(WordToken).filter(WordToken.language_code.in_(languages)).all():
        caches.word_token_ids[(token.token, token.language_code)] = token.id


def _word_token_id(token_text: str, language_code: str, caches: _ImportCaches) -> int:
    """Return the id for a token that ``_bulk_create_word_tokens`` already made."""
    token_id = caches.word_token_ids.get((token_text, language_code))
    assert token_id is not None, f"word token {(token_text, language_code)!r} not pre-created"
    return token_id


def _bulk_upsert_annotations(
    session: Session,
    importer: TierImporter,
    entries: List[TierEntry],
    report: ImportReport,
    caches: _ImportCaches,
) -> None:
    """Upsert every annotation an import needs without per-entry flushing.

    Splits entries into rows already present (updated in place) and new rows,
    inserts the new rows in one bulk statement, then re-reads them back into
    ``caches.annotations`` so the per-entry pass can look up annotation ids
    without flushing once per row. ``report`` is updated with the same
    inserted/updated counts the previous per-entry path produced.
    """
    source = importer.source
    # Pending new-annotation rows, keyed so a repeated key updates the pending
    # row instead of inserting a duplicate. dict preserves insertion order.
    new_rows: dict[tuple[int, str, Optional[str], Optional[str]], dict[str, object]] = {}
    for entry in entries:
        word_token_id = _word_token_id(entry.word, entry.language_code, caches)
        key = (word_token_id, source, entry.pos_hint, entry.sense_hint)
        themes_json = json.dumps(list(entry.themes)) if entry.themes else None
        existing = caches.annotations.get(key)
        if existing is not None:
            existing.tier_name = entry.tier_name
            existing.themes = themes_json
            report.annotations_updated += 1
            continue
        # Two entries in the same file can share a key (same token/pos/sense).
        # As in the original per-entry upsert, the first occurrence inserts and
        # later ones count as updates (overwriting the still-pending fields).
        pending = new_rows.get(key)
        if pending is not None:
            pending["tier_name"] = entry.tier_name
            pending["themes"] = themes_json
            report.annotations_updated += 1
            continue
        report.annotations_inserted += 1
        new_rows[key] = {
            "word_token_id": word_token_id,
            "source": source,
            "tier_name": entry.tier_name,
            "pos_hint": entry.pos_hint,
            "sense_hint": entry.sense_hint,
            "themes": themes_json,
        }

    if new_rows:
        session.execute(insert(ExternalLexemeAnnotation), list(new_rows.values()))
        session.flush()
        # Re-read the rows we just inserted so the cache holds their ids.
        for annotation in (
            session.query(ExternalLexemeAnnotation)
            .filter(ExternalLexemeAnnotation.source == source)
            .all()
        ):
            caches.annotations[
                (
                    annotation.word_token_id,
                    annotation.source,
                    annotation.pos_hint,
                    annotation.sense_hint,
                )
            ] = annotation


def _annotation_for(
    importer: TierImporter, entry: TierEntry, caches: _ImportCaches
) -> ExternalLexemeAnnotation:
    """Return the annotation ``_bulk_upsert_annotations`` created for an entry."""
    word_token_id = _word_token_id(entry.word, entry.language_code, caches)
    key = (word_token_id, importer.source, entry.pos_hint, entry.sense_hint)
    annotation = caches.annotations.get(key)
    assert annotation is not None, f"annotation for {entry.word!r} not pre-created"
    return annotation


def _ensure_lemma_link(
    session: Session,
    annotation_id: int,
    lemma_id: int,
    caches: _ImportCaches,
) -> bool:
    """Insert an annotation->lemma link if missing. Returns True if inserted."""
    if (annotation_id, lemma_id) in caches.lemma_links:
        return False
    session.add(ExternalLexemeAnnotationLemma(annotation_id=annotation_id, lemma_id=lemma_id))
    caches.lemma_links.add((annotation_id, lemma_id))
    return True


def _upsert_lemma_tier(
    session: Session,
    *,
    lemma_id: int,
    source: str,
    tier_name: str,
    themes: tuple[str, ...],
    caches: _ImportCaches,
) -> bool:
    """Insert or update a LemmaTier. Returns True if a new row was inserted."""
    themes_json = json.dumps(list(themes)) if themes else None
    existing = caches.lemma_tiers.get((lemma_id, source))
    if existing is None:
        row = LemmaTier(
            lemma_id=lemma_id,
            source=source,
            tier_name=tier_name,
            themes=themes_json,
        )
        session.add(row)
        caches.lemma_tiers[(lemma_id, source)] = row
        return True
    existing.tier_name = tier_name
    existing.themes = themes_json
    return False


def _process_entry(
    session: Session,
    importer: TierImporter,
    entry: TierEntry,
    report: ImportReport,
    caches: _ImportCaches,
) -> None:
    # The annotation row (and its counts) was already created by
    # _bulk_upsert_annotations; here we only attach lemmas.
    annotation = _annotation_for(importer, entry, caches)

    candidate_ids = importer.resolve(session, entry)
    if not candidate_ids:
        report.unattached += 1
        report.add_example("unattached", entry.word)
        return

    for lemma_id in candidate_ids:
        if _ensure_lemma_link(session, annotation.id, lemma_id, caches):
            report.lemma_links_inserted += 1
        if _upsert_lemma_tier(
            session,
            lemma_id=lemma_id,
            source=importer.source,
            tier_name=entry.tier_name,
            themes=entry.themes,
            caches=caches,
        ):
            report.lemma_tiers_inserted += 1
        else:
            report.lemma_tiers_updated += 1

    if len(candidate_ids) > 1:
        report.add_example("multi_lemma", f"{entry.word} -> {len(candidate_ids)} lemmas")


def run_import(
    session: Session,
    importer: TierImporter,
    *,
    bootstrap: bool = True,
    dry_run: bool = False,
) -> ImportReport:
    """Run a tier importer end-to-end against the given session.

    Args:
        session: Database session (caller manages connection lifecycle).
        importer: A TierImporter implementation (e.g., CambridgeYleImporter).
        bootstrap: Insert any missing TierDefinition rows for the source first.
        dry_run: If True, do not commit; the report still reflects intended changes.
    """
    source = importer.source
    if bootstrap:
        bootstrap_tier_definitions(session, sources=[source])

    known_tiers = _known_tier_names(session, source)
    caches = _build_import_caches(session, source)
    entries = importer.load_entries()
    report = ImportReport(source=source, total=len(entries))

    # Split out entries with an unknown tier so they neither create word tokens
    # nor get processed (matching the original per-entry skip).
    processable: List[TierEntry] = []
    for entry in entries:
        if entry.tier_name not in known_tiers:
            if entry.tier_name not in report.unknown_tier_names:
                report.unknown_tier_names.append(entry.tier_name)
            report.add_example("unknown_tier", f"{entry.word} -> {entry.tier_name}")
            continue
        processable.append(entry)

    # Create all needed WordTokens and annotations in bulk up front, so the
    # per-entry path below never flushes just to mint a token or annotation id.
    _bulk_create_word_tokens(session, processable, caches)
    _bulk_upsert_annotations(session, importer, processable, report, caches)

    for entry in processable:
        _process_entry(session, importer, entry, report, caches)

    if dry_run:
        session.rollback()
    else:
        session.commit()

    logger.info(
        "tier import %s: total=%d annot(ins=%d upd=%d) "
        "lemma_links=%d lemma_tiers(ins=%d upd=%d) unattached=%d",
        source,
        report.total,
        report.annotations_inserted,
        report.annotations_updated,
        report.lemma_links_inserted,
        report.lemma_tiers_inserted,
        report.lemma_tiers_updated,
        report.unattached,
    )
    return report


def reconcile_external_annotations(
    session: Session,
    importer: TierImporter,
    *,
    dry_run: bool = False,
) -> ImportReport:
    """Re-resolve every ExternalLexemeAnnotation for the importer's source.

    Useful after lemmas have been added: walks existing annotation rows,
    re-runs ``importer.resolve`` against each, and inserts any missing
    ExternalLexemeAnnotationLemma + LemmaTier rows. Does not modify the
    annotation rows themselves and does not delete stale links.
    """
    source = importer.source
    annotations = (
        session.query(ExternalLexemeAnnotation)
        .filter(ExternalLexemeAnnotation.source == source)
        .all()
    )
    report = ImportReport(source=source, total=len(annotations))
    caches = _build_import_caches(session, source)
    for annotation in annotations:
        token = annotation.word_token
        themes_tuple: tuple[str, ...] = (
            tuple(json.loads(annotation.themes)) if annotation.themes else ()
        )
        entry = TierEntry(
            word=token.token,
            language_code=token.language_code,
            pos_hint=annotation.pos_hint,
            tier_name=annotation.tier_name,
            sense_hint=annotation.sense_hint,
            themes=themes_tuple,
        )
        candidate_ids = importer.resolve(session, entry)
        if not candidate_ids:
            report.unattached += 1
            continue
        for lemma_id in candidate_ids:
            if _ensure_lemma_link(session, annotation.id, lemma_id, caches):
                report.lemma_links_inserted += 1
            if _upsert_lemma_tier(
                session,
                lemma_id=lemma_id,
                source=source,
                tier_name=annotation.tier_name,
                themes=themes_tuple,
                caches=caches,
            ):
                report.lemma_tiers_inserted += 1
            else:
                report.lemma_tiers_updated += 1

    if dry_run:
        session.rollback()
    else:
        session.commit()

    logger.info(
        "reconcile %s: scanned=%d new_links=%d new_tiers=%d unattached=%d",
        source,
        report.total,
        report.lemma_links_inserted,
        report.lemma_tiers_inserted,
        report.unattached,
    )
    return report
