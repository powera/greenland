"""Integrity checks for lemma records.

All functions use a caller-owned session without changing its transaction.
"""

import logging
from typing import Any, Dict, List

from sqlalchemy import func
from sqlalchemy.orm import Session

from storage.models.schema import DerivativeForm, Lemma

logger = logging.getLogger(__name__)


def check_missing_required_fields(session: Session) -> Dict[str, Any]:
    """Return lemmas missing fields required by downstream exports."""
    try:
        issues: List[Dict[str, Any]] = []
        field_checks = (
            (
                "definition_text",
                (Lemma.definition_text.is_(None)) | (Lemma.definition_text == ""),
                "high",
            ),
            ("pos_type", (Lemma.pos_type.is_(None)) | (Lemma.pos_type == ""), "high"),
            (
                "difficulty_level",
                Lemma.guid.isnot(None) & Lemma.difficulty_level.is_(None),
                "medium",
            ),
        )
        for field_name, predicate, severity in field_checks:
            for lemma in session.query(Lemma).filter(predicate).all():
                issues.append(
                    {
                        "table": "lemmas",
                        "id": lemma.id,
                        "guid": lemma.guid,
                        "lemma_text": lemma.lemma_text,
                        "missing_field": field_name,
                        "severity": severity,
                    }
                )
        high_severity = [issue for issue in issues if issue["severity"] == "high"]
        medium_severity = [issue for issue in issues if issue["severity"] == "medium"]
        return {
            "total_issues": len(issues),
            "high_severity_count": len(high_severity),
            "medium_severity_count": len(medium_severity),
            "high_severity_issues": high_severity,
            "medium_severity_issues": medium_severity,
        }
    except Exception as error:
        logger.error("Error checking missing required fields: %s", error)
        return {
            "error": str(error),
            "total_issues": 0,
            "high_severity_count": 0,
            "medium_severity_count": 0,
            "high_severity_issues": [],
            "medium_severity_issues": [],
        }


def check_lemmas_without_derivatives(session: Session) -> Dict[str, Any]:
    """Return lemmas that have no derivative forms."""
    try:
        lemmas = session.query(Lemma).all()
        lemma_ids_with_forms = {
            lemma_id for lemma_id, in session.query(DerivativeForm.lemma_id).distinct().all()
        }
        missing = [
            {
                "id": lemma.id,
                "guid": lemma.guid,
                "lemma_text": lemma.lemma_text,
                "pos_type": lemma.pos_type,
                "difficulty_level": lemma.difficulty_level,
            }
            for lemma in lemmas
            if lemma.id not in lemma_ids_with_forms
        ]
        return {
            "total_lemmas": len(lemmas),
            "without_forms_count": len(missing),
            "lemmas_without_forms": missing,
        }
    except Exception as error:
        logger.error("Error checking lemmas without derivative forms: %s", error)
        return {
            "error": str(error),
            "total_lemmas": 0,
            "without_forms_count": 0,
            "lemmas_without_forms": [],
        }


def check_duplicate_guids(session: Session) -> Dict[str, Any]:
    """Return groups of lemmas sharing a non-null GUID."""
    try:
        guid_counts = (
            session.query(Lemma.guid, func.count(Lemma.id).label("count"))
            .filter(Lemma.guid.isnot(None))
            .group_by(Lemma.guid)
            .having(func.count(Lemma.id) > 1)
            .all()
        )
        duplicates: List[Dict[str, Any]] = []
        for guid, count in guid_counts:
            lemmas = session.query(Lemma).filter(Lemma.guid == guid).all()
            duplicates.append(
                {
                    "guid": guid,
                    "count": count,
                    "lemmas": [
                        {
                            "id": lemma.id,
                            "lemma_text": lemma.lemma_text,
                            "pos_type": lemma.pos_type,
                            "difficulty_level": lemma.difficulty_level,
                        }
                        for lemma in lemmas
                    ],
                }
            )
        return {"duplicate_count": len(duplicates), "duplicates": duplicates}
    except Exception as error:
        logger.error("Error checking duplicate GUIDs: %s", error)
        return {"error": str(error), "duplicate_count": 0, "duplicates": []}


def check_duplicate_words(session: Session) -> Dict[str, Any]:
    """Return duplicate lemma groups with equal text, POS, and disambiguation."""
    try:
        coalesced_disambiguation = func.coalesce(Lemma.disambiguation, "")
        duplicate_groups = (
            session.query(
                Lemma.lemma_text,
                Lemma.pos_type,
                coalesced_disambiguation.label("disambig"),
                func.count(Lemma.id).label("count"),
            )
            .group_by(Lemma.lemma_text, Lemma.pos_type, coalesced_disambiguation)
            .having(func.count(Lemma.id) > 1)
            .all()
        )
        duplicates: List[Dict[str, Any]] = []
        for lemma_text, pos_type, disambiguation, _count in duplicate_groups:
            query = session.query(Lemma).filter(
                Lemma.lemma_text == lemma_text,
                Lemma.pos_type == pos_type,
            )
            if disambiguation:
                query = query.filter(Lemma.disambiguation == disambiguation)
            else:
                query = query.filter(
                    (Lemma.disambiguation.is_(None)) | (Lemma.disambiguation == "")
                )
            lemmas = query.all()
            duplicates.append(
                {
                    "lemma_text": lemma_text,
                    "pos_type": pos_type,
                    "disambiguation": disambiguation or None,
                    "count": len(lemmas),
                    "lemmas": [
                        {
                            "id": lemma.id,
                            "guid": lemma.guid,
                            "definition_text": lemma.definition_text,
                            "difficulty_level": lemma.difficulty_level,
                            "verified": lemma.verified,
                        }
                        for lemma in lemmas
                    ],
                }
            )
        return {
            "duplicate_group_count": len(duplicates),
            "total_duplicate_lemmas": sum(item["count"] for item in duplicates),
            "duplicates": duplicates,
        }
    except Exception as error:
        logger.error("Error checking duplicate words: %s", error)
        return {
            "error": str(error),
            "duplicate_group_count": 0,
            "total_duplicate_lemmas": 0,
            "duplicates": [],
        }


def check_invalid_difficulty_levels(session: Session) -> Dict[str, Any]:
    """Return lemmas with difficulty levels outside 1 through 20."""
    try:
        invalid_lemmas = (
            session.query(Lemma)
            .filter(
                Lemma.difficulty_level.isnot(None),
                (Lemma.difficulty_level < 1) | (Lemma.difficulty_level > 20),
            )
            .all()
        )
        invalid_entries = [
            {
                "id": lemma.id,
                "guid": lemma.guid,
                "lemma_text": lemma.lemma_text,
                "invalid_level": lemma.difficulty_level,
            }
            for lemma in invalid_lemmas
        ]
        return {"invalid_count": len(invalid_entries), "invalid_entries": invalid_entries}
    except Exception as error:
        logger.error("Error checking invalid difficulty levels: %s", error)
        return {"error": str(error), "invalid_count": 0, "invalid_entries": []}
