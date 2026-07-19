#!/usr/bin/python3

"""Quality Hub routes.

Single entry point for the "find and fix weak data" loop, combining:

1. Rapid Review - keyboard-driven review of sentences and audio
2. Data Quality Checks - in-process integrity checks and duplicate scans
3. Data Completeness - coverage reports for translations, IPA, and audio

The heavier LLM-based tools (translation verification, sentence linking)
remain on the Data Quality (bebras) page, which this hub links to.
"""

from flask import Blueprint, current_app, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from sqlalchemy import and_, case, func

from barsukas.helpers.flash_helpers import flash_and_log
from barsukas.helpers.integrity_runner import (
    FIXABLE_CHECKS,
    INTEGRITY_CHECKS,
    run_integrity_check,
)
from storage.models.schema import AudioQualityReview, Lemma, Sentence

bp = Blueprint("quality", __name__, url_prefix="/quality")


@bp.route("/")
def index() -> ResponseReturnValue:
    """Display the Quality Hub with review queues, checks, and completeness links."""
    # Sentence review queue: ready = not yet verified or rejected.
    sentence_stats = g.db.query(
        func.count(Sentence.id).label("total"),
        func.count(
            case((and_(Sentence.verified == False, Sentence.rejected == False), 1))  # noqa: E712
        ).label("ready"),
        func.count(case((Sentence.verified == True, 1))).label("verified"),  # noqa: E712
        func.count(case((Sentence.rejected == True, 1))).label("rejected"),  # noqa: E712
    ).first()

    # Audio review queue, split by lemma vs sentence audio.
    audio_stats = g.db.query(
        func.count(AudioQualityReview.id).label("total"),
        func.count(case((AudioQualityReview.status == "pending_review", 1))).label("pending"),
        func.count(
            case(
                (
                    and_(
                        AudioQualityReview.status == "pending_review",
                        AudioQualityReview.sentence_id.is_(None),
                    ),
                    1,
                )
            )
        ).label("pending_lemma"),
        func.count(
            case(
                (
                    and_(
                        AudioQualityReview.status == "pending_review",
                        AudioQualityReview.sentence_id.isnot(None),
                    ),
                    1,
                )
            )
        ).label("pending_sentence"),
        func.count(case((AudioQualityReview.status == "needs_replacement", 1))).label(
            "needs_replacement"
        ),
    ).first()

    total_lemmas = g.db.query(func.count(Lemma.id)).filter(Lemma.guid.isnot(None)).scalar() or 0

    # Languages that currently have audio pending review, split by audio type,
    # for the per-language quick-start links.
    pending_by_language = (
        g.db.query(
            AudioQualityReview.language_code,
            func.count(case((AudioQualityReview.sentence_id.is_(None), 1))).label("lemma_count"),
            func.count(case((AudioQualityReview.sentence_id.isnot(None), 1))).label(
                "sentence_count"
            ),
        )
        .filter(AudioQualityReview.status == "pending_review")
        .group_by(AudioQualityReview.language_code)
        .order_by(AudioQualityReview.language_code)
        .all()
    )
    lemma_audio_languages = [row.language_code for row in pending_by_language if row.lemma_count]
    sentence_audio_languages = [
        row.language_code for row in pending_by_language if row.sentence_count
    ]

    return render_template(
        "quality/index.html",
        sentence_stats=sentence_stats,
        audio_stats=audio_stats,
        total_lemmas=total_lemmas,
        lemma_audio_languages=lemma_audio_languages,
        sentence_audio_languages=sentence_audio_languages,
        integrity_checks=INTEGRITY_CHECKS,
        fixable_checks=FIXABLE_CHECKS,
    )


@bp.route("/run-check", methods=["POST"])
def run_check() -> ResponseReturnValue:
    """Run a single integrity check in-process and show its results."""
    check_type = request.form.get("check_type", "").strip()
    fix_issues = request.form.get("fix_issues") == "true"

    if fix_issues and current_app.config.get("READONLY", False):
        flash_and_log("Fixing issues is not available in read-only mode", "error")
        return redirect(url_for("quality.index"))

    results = run_integrity_check(check_type, fix=fix_issues)
    if results is None:
        flash_and_log(f"Unknown check type: {check_type}", "error")
        return redirect(url_for("quality.index"))

    return render_template(
        "bebras/integrity_results.html",
        check_type=check_type,
        results=results,
        back_url=url_for("quality.index"),
        back_label="Back to Quality Hub",
    )
