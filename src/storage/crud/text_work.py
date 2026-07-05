"""CRUD operations for the TextWork / TextVersion models (the story library).

All slug handling goes through ``normalize_concept_slug`` (shared with
concepts) so space/underscore variants of a title resolve to the same row.
Q-ids are normalized via ``storage.wikidata.normalize_qid``.

The version-level invariants from docs/fables_design.md are enforced here
(mirroring the CRUD-layer posture used for the sub-concepts one-target guard):

1. At most one canonical version per work, only for canonical-type works.
2. At most one version per (work, lang, difficulty_level) slot, treating NULL
   difficulty as its own slot (SQLite treats NULLs as distinct in unique
   indexes, so this cannot be a UniqueConstraint).
3. Canonical versions require ``license``.
"""

import logging
from typing import Any, Optional, cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from storage.models.concept import normalize_concept_slug
from storage.models.text_work import (
    ALL_TEXT_TYPES,
    SUPPORTED_TEXT_VERSION_LANGS,
    TextVersion,
    TextWork,
    is_canonical_text_type,
    is_intake_deferred_text_type,
)

logger = logging.getLogger(__name__)

# Sentinel for "argument not supplied" on updates of nullable fields, where
# None is a meaningful value (e.g. clearing difficulty_level).
_UNSET: Any = object()


def _normalized_qid_or_none(qid: Optional[str]) -> Optional[str]:
    """Return the canonical Q-id for a raw value, or None when absent/invalid."""
    from storage.wikidata import normalize_qid

    if qid is None or not qid.strip():
        return None
    return normalize_qid(qid)


def get_text_work_by_slug(session: Session, slug: str) -> Optional[TextWork]:
    """Look up a text work by slug, normalizing space/underscore equivalence."""
    normalized = normalize_concept_slug(slug)
    return cast(
        Optional[TextWork],
        session.query(TextWork).filter(TextWork.slug == normalized).first(),
    )


def get_text_work_by_id(session: Session, work_id: int) -> Optional[TextWork]:
    """Return a text work by its internal id, or None."""
    return cast(Optional[TextWork], session.query(TextWork).filter(TextWork.id == work_id).first())


def get_text_work_by_qid(session: Session, qid: str) -> Optional[TextWork]:
    """Return the text work whose own Q-id matches, or None.

    This is the lookup behind the "Read the story" box on concept pages: the
    Q-id is the work's own identity (``TextWork.qid``), not the attribution.
    """
    from storage.wikidata import normalize_qid

    normalized_qid = normalize_qid(qid)
    if normalized_qid is None:
        return None
    return cast(
        Optional[TextWork],
        session.query(TextWork).filter(TextWork.qid == normalized_qid).first(),
    )


def create_text_work(
    session: Session,
    title: str,
    text_type: str,
    *,
    qid: Optional[str] = None,
    attribution_qid: Optional[str] = None,
    attribution: Optional[str] = None,
    summary: Optional[str] = None,
    verified: bool = False,
    notes: Optional[str] = None,
) -> Optional[TextWork]:
    """Create a new text work (no versions yet).

    Args:
        session: Database session (concepts backend).
        title: Human-entered title; normalized to the canonical slug.
        text_type: One of ALL_TEXT_TYPES. Intake-deferred types ("quote") are
            refused until their phase lands.
        qid: The work's own Wikidata Q-id (unique across works), if any.
        attribution_qid: Q-id of the attributed person/source, if any.
        attribution: Display attribution line ("Robert Frost").
        summary: One-sentence description (scenario brief for conversations).
        verified: Whether a human has reviewed the work metadata.
        notes: Optional notes (e.g. curation context).

    Returns:
        The created TextWork, or None if the type is invalid/deferred, the
        slug is empty, a supplied Q-id is invalid, or slug/qid already exist.
    """
    if text_type not in ALL_TEXT_TYPES:
        logger.warning("Refusing to create text work with unknown type %r", text_type)
        return None
    if is_intake_deferred_text_type(text_type):
        logger.warning(
            "Refusing to create text work of deferred type %r (no intake yet)", text_type
        )
        return None
    slug = normalize_concept_slug(title)
    if not slug:
        logger.warning("Refusing to create text work with empty title")
        return None

    normalized_qid: Optional[str] = None
    if qid is not None and qid.strip():
        normalized_qid = _normalized_qid_or_none(qid)
        if normalized_qid is None:
            logger.warning("Refusing to create text work with invalid Q-id %r", qid)
            return None
    normalized_attribution_qid: Optional[str] = None
    if attribution_qid is not None and attribution_qid.strip():
        normalized_attribution_qid = _normalized_qid_or_none(attribution_qid)
        if normalized_attribution_qid is None:
            logger.warning(
                "Refusing to create text work with invalid attribution Q-id %r", attribution_qid
            )
            return None

    work = TextWork(
        slug=slug,
        text_type=text_type,
        qid=normalized_qid,
        attribution_qid=normalized_attribution_qid,
        attribution=attribution,
        summary=summary,
        verified=verified,
        notes=notes,
    )
    try:
        session.add(work)
        session.commit()
        logger.info(f"Created text work: {slug} [{text_type}]")
        return work
    except IntegrityError as error:
        session.rollback()
        logger.warning(f"Text work already exists or constraint violated for {slug!r}: {error}")
        return None


def update_text_work(
    session: Session,
    work: TextWork,
    *,
    title: Optional[str] = None,
    text_type: Optional[str] = None,
    qid: Any = _UNSET,
    attribution_qid: Any = _UNSET,
    attribution: Optional[str] = None,
    summary: Optional[str] = None,
    verified: Optional[bool] = None,
    notes: Optional[str] = None,
) -> Optional[TextWork]:
    """Update fields on an existing text work.

    Only supplied arguments are applied (``qid``/``attribution_qid`` accept
    None to clear; omit them to leave unchanged). Returns None (and rolls
    back) on slug/qid collision, an invalid type, or a type change that would
    orphan an existing canonical version (an authored-type work can never hold
    one).
    """
    if text_type is not None:
        if text_type not in ALL_TEXT_TYPES or is_intake_deferred_text_type(text_type):
            logger.warning("Refusing to set unknown/deferred text type %r", text_type)
            return None
        if not is_canonical_text_type(text_type) and work.canonical_version is not None:
            logger.warning(
                "Refusing to change %r to authored type %r: a canonical version exists",
                work.slug,
                text_type,
            )
            return None
        work.text_type = text_type
    if title is not None:
        work.slug = normalize_concept_slug(title)
    if qid is not _UNSET:
        if qid is None or not str(qid).strip():
            work.qid = None
        else:
            normalized_qid = _normalized_qid_or_none(str(qid))
            if normalized_qid is None:
                logger.warning("Refusing to set invalid Q-id %r on %r", qid, work.slug)
                return None
            work.qid = normalized_qid
    if attribution_qid is not _UNSET:
        if attribution_qid is None or not str(attribution_qid).strip():
            work.attribution_qid = None
        else:
            normalized_attribution_qid = _normalized_qid_or_none(str(attribution_qid))
            if normalized_attribution_qid is None:
                logger.warning(
                    "Refusing to set invalid attribution Q-id %r on %r", attribution_qid, work.slug
                )
                return None
            work.attribution_qid = normalized_attribution_qid
    if attribution is not None:
        work.attribution = attribution or None
    if summary is not None:
        work.summary = summary
    if verified is not None:
        work.verified = verified
    if notes is not None:
        work.notes = notes

    try:
        session.commit()
        logger.info(f"Updated text work: {work.slug}")
        return work
    except IntegrityError as error:
        session.rollback()
        logger.warning(f"Update collided for text work {work.slug!r}: {error}")
        return None


def delete_text_work(session: Session, work: TextWork) -> bool:
    """Delete a text work and (via ORM cascade) all its versions."""
    session.delete(work)
    session.commit()
    logger.info(f"Deleted text work: {work.slug}")
    return True


# --- Versions ----------------------------------------------------------------


def get_text_version_by_id(session: Session, version_id: int) -> Optional[TextVersion]:
    """Return a text version by its internal id, or None."""
    return cast(
        Optional[TextVersion],
        session.query(TextVersion).filter(TextVersion.id == version_id).first(),
    )


def get_text_version_for_slot(
    session: Session,
    work: TextWork,
    lang: str,
    difficulty_level: Optional[int],
) -> Optional[TextVersion]:
    """Return the version occupying a (work, lang, difficulty) slot, if any."""
    return cast(
        Optional[TextVersion],
        session.query(TextVersion)
        .filter(
            TextVersion.work_id == work.id,
            TextVersion.lang == lang,
            (
                TextVersion.difficulty_level.is_(None)
                if difficulty_level is None
                else TextVersion.difficulty_level == difficulty_level
            ),
        )
        .first(),
    )


def create_text_version(
    session: Session,
    work: TextWork,
    *,
    lang: str = "en",
    body: Optional[str] = None,
    is_canonical: bool = False,
    difficulty_level: Optional[int] = None,
    source_model: Optional[str] = None,
    confidence: float = 0.0,
    text_source: Optional[str] = None,
    license: Optional[str] = None,
    verified: bool = False,
    notes: Optional[str] = None,
) -> Optional[TextVersion]:
    """Create a version of a work, enforcing the version invariants.

    Args:
        session: Database session (concepts backend).
        work: The work this version renders.
        lang: Language code of the text (English-only for now).
        body: The text itself (Markdown, no wiki links). May be None for a
            metadata-only canonical version.
        is_canonical: True only for the authoritative text of a
            canonical-type work; requires ``license``.
        difficulty_level: Target difficulty (lemma scale), or None.
        source_model: Generating model name (authored versions).
        confidence: LLM confidence (authored versions).
        text_source: Where a canonical text was transcribed from.
        license: License of a canonical text (required when canonical).
        verified: Whether a human has reviewed the text.
        notes: Optional notes.

    Returns:
        The created TextVersion, or None if an invariant is violated.
    """
    if lang not in SUPPORTED_TEXT_VERSION_LANGS:
        logger.warning("Refusing to create version in unsupported language %r", lang)
        return None
    if is_canonical:
        if not is_canonical_text_type(work.text_type):
            logger.warning(
                "Refusing canonical version for authored-type work %r [%s]",
                work.slug,
                work.text_type,
            )
            return None
        if work.canonical_version is not None:
            logger.warning("Work %r already has a canonical version", work.slug)
            return None
        if not (license or "").strip():
            logger.warning("Refusing canonical version without a license for %r", work.slug)
            return None
    if get_text_version_for_slot(session, work, lang, difficulty_level) is not None:
        logger.warning(
            "Version slot (%r, %r, %r) already occupied for %r",
            lang,
            difficulty_level,
            "canonical" if is_canonical else "authored",
            work.slug,
        )
        return None

    version = TextVersion(
        work_id=work.id,
        lang=lang,
        body=body,
        is_canonical=is_canonical,
        difficulty_level=difficulty_level,
        source_model=source_model,
        confidence=confidence,
        text_source=text_source,
        license=license,
        verified=verified,
        notes=notes,
    )
    try:
        session.add(version)
        session.commit()
        logger.info(f"Created text version for {work.slug}: {version.variant_label}")
        return version
    except IntegrityError as error:
        session.rollback()
        logger.warning(f"Failed to create version for {work.slug!r}: {error}")
        return None


def update_text_version(
    session: Session,
    version: TextVersion,
    *,
    body: Optional[str] = None,
    difficulty_level: Any = _UNSET,
    source_model: Optional[str] = None,
    confidence: Optional[float] = None,
    text_source: Optional[str] = None,
    license: Optional[str] = None,
    verified: Optional[bool] = None,
    notes: Optional[str] = None,
) -> Optional[TextVersion]:
    """Update fields on an existing version.

    Only supplied arguments are applied (``difficulty_level`` accepts None to
    clear; omit it to leave unchanged). A canonical version cannot have its
    license blanked, and a difficulty change may not land on an occupied
    (lang, difficulty) slot.
    """
    if license is not None:
        if version.is_canonical and not license.strip():
            logger.warning("Refusing to blank the license on a canonical version")
            return None
        version.license = license.strip() or None
    if difficulty_level is not _UNSET and difficulty_level != version.difficulty_level:
        work = version.work
        occupied = get_text_version_for_slot(session, work, version.lang, difficulty_level)
        if occupied is not None and occupied.id != version.id:
            logger.warning(
                "Version slot (%r, %r) already occupied for %r",
                version.lang,
                difficulty_level,
                work.slug,
            )
            return None
        version.difficulty_level = difficulty_level
    if body is not None:
        version.body = body
    if source_model is not None:
        version.source_model = source_model
    if confidence is not None:
        version.confidence = confidence
    if text_source is not None:
        version.text_source = text_source.strip() or None
    if verified is not None:
        version.verified = verified
    if notes is not None:
        version.notes = notes

    try:
        session.commit()
        logger.info(f"Updated text version {version.id} ({version.variant_label})")
        return version
    except IntegrityError as error:
        session.rollback()
        logger.warning(f"Failed to update version {version.id}: {error}")
        return None


def delete_text_version(session: Session, version: TextVersion) -> bool:
    """Delete a single version of a work. Returns True if deleted."""
    session.delete(version)
    session.commit()
    logger.info(f"Deleted text version {version.id}")
    return True
