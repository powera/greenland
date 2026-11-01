#!/usr/bin/env python3
"""Reattach audio stranded by subtype GUID changes; preview unless --apply.

Only subtype-only replacement chains and exact current spoken text qualify.
Conflicting takes are preserved under their historical GUID unless the user
explicitly chooses --prefer-review-id. That choice swaps the current and
historical references without deleting either recording or touching S3.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sqlalchemy.orm import Session

from audiotools.lemma_audio import lemma_audio_targets
from storage.backend.config import BackendType, DataSourceConfig
from storage.backend.factory import create_session
from storage.crud.guid_tombstone import get_replacement_chain
from storage.crud.operation_log import FieldChange, log_field_changes
from storage.models.guid_tombstone import TOMBSTONE_REASON_SUBTYPE_CHANGE, GuidTombstone
from storage.models.schema import AudioQualityReview, Lemma

SOURCE = "migration/20261101-repair-audio-guids"


def repair_audio_guids(
    session: Session, preferred_review_ids: frozenset[int] = frozenset()
) -> dict[str, list[int]]:
    """Stage safe repairs in the caller's transaction, retaining ambiguous takes."""
    report: dict[str, list[int]] = {
        "moved": [],
        "preferred": [],
        "conflicts": [],
        "text_mismatch": [],
        "unresolved": [],
    }
    for preferred_id in preferred_review_ids:
        selected = session.get(AudioQualityReview, preferred_id)
        if selected is None or selected.status == "needs_replacement":
            raise ValueError(f"Review {preferred_id} is missing or rejected")
    groups: dict[tuple[str, str, str, Optional[str]], list[AudioQualityReview]] = defaultdict(list)
    owners: dict[str, Lemma] = {}
    targets: dict[tuple[int, str], dict[Optional[str], str]] = {}
    historical = (
        session.query(AudioQualityReview)
        .join(GuidTombstone, GuidTombstone.guid == AudioQualityReview.guid)
        .filter(AudioQualityReview.sentence_id.is_(None))
        .order_by(AudioQualityReview.id)
        .all()
    )
    for recording in historical:
        assert recording.guid is not None
        chain = get_replacement_chain(session, recording.guid)
        replacement = chain[-1].replacement_guid if chain else None
        owner = session.query(Lemma).filter_by(guid=replacement).first() if replacement else None
        if (
            owner is None
            or any(step.reason != TOMBSTONE_REASON_SUBTYPE_CHANGE for step in chain)
            or any(step.lemma_id is not None and step.lemma_id != owner.id for step in chain)
        ):
            report["unresolved"].append(recording.id)
            continue
        assert owner.guid is not None
        target_key = (owner.id, recording.language_code)
        if target_key not in targets:
            targets[target_key] = {
                target.slot: target.text
                for target in lemma_audio_targets(
                    session, owner, recording.language_code, include_forms=True
                )
            }
        if targets[target_key].get(recording.grammatical_form) != recording.expected_text:
            report["text_mismatch"].append(recording.id)
            continue
        owners[owner.guid] = owner
        identity = (
            owner.guid,
            recording.language_code,
            recording.voice_name,
            recording.grammatical_form,
        )
        groups[identity].append(recording)

    for identity, candidates in groups.items():
        current_guid, language, voice, slot = identity
        current = (
            session.query(AudioQualityReview)
            .filter_by(
                guid=current_guid,
                language_code=language,
                voice_name=voice,
                grammatical_form=slot,
                sentence_id=None,
            )
            .all()
        )
        chosen = [candidate for candidate in candidates if candidate.id in preferred_review_ids]
        if len(chosen) > 1:
            raise ValueError(f"Multiple preferred reviews for {identity}")
        if not chosen and (current or len(candidates) != 1):
            report["conflicts"].extend(candidate.id for candidate in candidates)
            continue
        selected_recording = chosen[0] if chosen else candidates[0]
        if chosen and (
            len(current) > 1
            or any(row.expected_text != selected_recording.expected_text for row in current)
        ):
            raise ValueError(f"Ambiguous current recording for {identity}")
        retired_guid = selected_recording.guid
        if current:
            displaced = current[0]
            displaced.guid = None
            session.flush()
        selected_recording.guid = current_guid
        selected_recording.lemma_id = owners[current_guid].id
        session.flush()
        if current:
            displaced.guid = retired_guid
            session.flush()
        log_field_changes(
            session,
            source=SOURCE,
            operation_type="audio_guid_repair",
            entity_guid=current_guid,
            lemma_id=owners[current_guid].id,
            changes=[FieldChange("guid", retired_guid, current_guid)],
            extra={
                "audio_review_id": selected_recording.id,
                "displaced_review_id": current[0].id if current else None,
            },
        )
        report["preferred" if chosen else "moved"].append(selected_recording.id)
        report["conflicts"].extend(
            candidate.id for candidate in candidates if candidate is not selected_recording
        )
    session.flush()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--prefer-review-id", type=int, action="append", default=[])
    args = parser.parse_args()
    config = DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=args.db_path)
    session = create_session(config)
    try:
        report = repair_audio_guids(session, frozenset(args.prefer_review_id))
        print(
            json.dumps(
                {
                    "apply": args.apply,
                    "counts": {name: len(ids) for name, ids in report.items()},
                    "reviews": report,
                },
                indent=2,
            )
        )
        if args.apply:
            session.commit()
        else:
            session.rollback()
    finally:
        session.close()


if __name__ == "__main__":
    main()
