#!/usr/bin/env python3
"""Publish local audio rejections into their S3 staging manifests.

A rejection recorded in this database (``status='needs_replacement'``) is
invisible to anyone else: the next database to run ``gandras`` re-imports the
same file and re-adopts audio this one already threw out. The staged audio is
content-addressed -- its key *is* the MD5 -- so the file itself can never be
edited or overwritten to signal anything. The manifest beside it can, and that
is where the verdict belongs.

This script walks the rejected rows and writes a ``rejected`` block into each
one's staged manifest (:func:`audiotools.s3_ops.mark_manifest_rejected`), so
the invalidation travels with the audio. ``gandras`` skips a manifest carrying
that block unless ``--import-rejected`` is passed.

Only manifests are rewritten; no MP3 is uploaded, downloaded, or deleted.

Usage::

    PYTHONPATH=src python src/scripts/push_audio_rejections_to_s3.py --dry-run
    PYTHONPATH=src python src/scripts/push_audio_rejections_to_s3.py --language lt
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from audiotools import s3_ops
from agents.common.common_args import add_backend_args, add_common_args, get_data_source_config
from clients.audio.s3_uploader import S3AudioUploader, get_staging_manifest_key
from storage.backend.factory import create_session
from storage.models.schema import AudioQualityReview

# The status this script publishes. Other statuses describe audio that is fine.
REJECTED_STATUS = "needs_replacement"


def rejection_reason(review: AudioQualityReview) -> str:
    """Build the human-readable reason recorded in the manifest.

    Prefers the reviewer's note, falling back to the structured issue codes,
    then to a bare statement -- the block should never claim more than the row
    actually says.
    """
    if review.notes:
        return str(review.notes)

    if review.quality_issues:
        try:
            issues = json.loads(review.quality_issues)
        except (json.JSONDecodeError, TypeError):
            issues = None
        if isinstance(issues, list) and issues:
            return ", ".join(str(issue) for issue in issues)

    return "Rejected during audio review"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write local audio rejections into their S3 staging manifests",
    )
    add_common_args(parser)
    add_backend_args(parser)
    parser.add_argument("--language", help="Only publish rejections for this language code")
    parser.add_argument("--limit", type=int, help="Stop after this many rejections")
    args = parser.parse_args()

    config = get_data_source_config(args)
    session = create_session(config)

    try:
        query = session.query(AudioQualityReview).filter(
            AudioQualityReview.status == REJECTED_STATUS
        )
        if args.language:
            query = query.filter(AudioQualityReview.language_code == args.language)
        query = query.order_by(AudioQualityReview.id)
        if args.limit:
            query = query.limit(args.limit)

        reviews: List[AudioQualityReview] = query.all()
        print(f"Rejected rows to publish: {len(reviews)}")
        if not reviews:
            return

        # Built lazily so a --dry-run needs no credentials.
        uploader: Optional[S3AudioUploader] = None

        published = 0
        skipped = 0
        failed = 0

        for review in reviews:
            if not review.manifest_md5:
                print(f"  SKIP {review.guid or review.sentence_id}: no manifest_md5 recorded")
                skipped += 1
                continue

            # Rebuilt from the row's own fields rather than parsed out of the
            # stored CDN URL, so a CDN/endpoint change cannot misaddress it.
            manifest_key = get_staging_manifest_key(
                review.language_code, review.voice_name, review.manifest_md5
            )
            label = review.guid or f"sentence_{review.sentence_id}"
            reason = rejection_reason(review)

            if args.dry_run:
                print(f"  [DRY RUN] would reject {label}: {manifest_key} ({reason})")
                published += 1
                continue

            if uploader is None:
                uploader = S3AudioUploader()

            ok = s3_ops.mark_manifest_rejected(
                uploader,
                manifest_key=manifest_key,
                reason=reason,
                rejected_by=str(review.reviewed_by or "audio review"),
                quality_issues=review.quality_issues,
            )
            if ok:
                print(f"  rejected {label}: {manifest_key}")
                published += 1
            else:
                print(f"  FAILED {label}: {manifest_key}")
                failed += 1

        print("\n" + "=" * 60)
        print(f"Published: {published}")
        print(f"Skipped (no MD5): {skipped}")
        print(f"Failed: {failed}")
        if args.dry_run:
            print("[DRY RUN - no manifests were written]")

    finally:
        session.close()


if __name__ == "__main__":
    main()
