#!/usr/bin/python3

"""Routes for pattern-based simple sentence generation."""

import logging

logger = logging.getLogger(__name__)

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

import constants
from storage.models.schema import Lemma, Sentence, SentenceTranslation, SentenceWord
from storage.translation_helpers import get_languages_in_hierarchy

bp = Blueprint("pattern_sentences", __name__, url_prefix="/pattern-sentences")


@bp.route("/")
def index() -> ResponseReturnValue:
    """Old bookmarks open the mechanical Trakaido practice tool."""
    return redirect(url_for("trakaido_activities.sentence_patterns"))


@bp.route("/<int:sentence_id>/reject", methods=["POST"])
def reject_sentence(sentence_id: int) -> ResponseReturnValue:
    """Mark a sentence as rejected so it won't be regenerated."""
    sentence = g.db.query(Sentence).get(sentence_id)
    if not sentence:
        flash("Sentence not found", "error")
        return redirect(url_for("pattern_sentences.view"))

    try:
        sentence.rejected = True
        g.db.commit()
        flash(f"Sentence #{sentence_id} marked as rejected", "success")
    except Exception as e:
        flash(f"Error rejecting sentence: {e}", "error")
        g.db.rollback()

    # Redirect back to the view page with current filters
    return redirect(request.referrer or url_for("pattern_sentences.view"))


@bp.route("/<int:sentence_id>/accept", methods=["POST"])
def accept_sentence(sentence_id: int) -> ResponseReturnValue:
    """Accept a sentence: generate translations for all languages and auto-populate level.

    This does NOT verify the sentence - that requires a separate Verify action.
    """
    sentence = g.db.query(Sentence).get(sentence_id)
    if not sentence:
        flash("Sentence not found", "error")
        return redirect(url_for("pattern_sentences.view"))

    try:
        # Check if any word has level -1
        sentence_words = (
            g.db.query(SentenceWord)
            .filter(SentenceWord.sentence_id == sentence_id)
            .filter(SentenceWord.lemma_id.isnot(None))
            .all()
        )

        for sw in sentence_words:
            lemma = g.db.query(Lemma).get(sw.lemma_id)
            if lemma and lemma.difficulty_level == -1:
                flash(
                    f"Cannot accept: word '{lemma.guid or lemma.lemma_text}' has difficulty level -1",
                    "error",
                )
                return redirect(request.referrer or url_for("pattern_sentences.view"))

        # Check if sentence already has translations for all languages
        existing_translations = {t.language_code for t in sentence.translations}
        target_languages = [
            lang["code"] for lang in get_languages_in_hierarchy() if lang["code"] != "en"
        ]
        has_all_translations = all(lang in existing_translations for lang in target_languages)

        # Generate missing translations
        if not has_all_translations:
            from sentences.translation import translate_sentence

            # Asked for by hand: ask again where a model was uncertain before;
            # each answer is still gated on its confidence.
            translate_sentence(
                sentence_id,
                target_languages,
                g.db,
                model=constants.DEFAULT_MODEL,
                retry_uncertain=True,
            )

        # Auto-populate the level if not set
        if sentence.minimum_level is None:
            max_level = None
            for sw in sentence_words:
                lemma = g.db.query(Lemma).get(sw.lemma_id)
                if lemma and lemma.difficulty_level is not None:
                    if max_level is None or lemma.difficulty_level > max_level:
                        max_level = lemma.difficulty_level

            if max_level is not None:
                sentence.minimum_level = max_level

        g.db.commit()

        if sentence.minimum_level is not None:
            flash(
                f"Sentence #{sentence_id} accepted with level {sentence.minimum_level}. Click Verify when ready.",
                "success",
            )
        else:
            flash(
                f"Sentence #{sentence_id} accepted (no level set - no words with difficulty levels). Click Verify when ready.",
                "warning",
            )

    except Exception as e:
        flash(f"Error accepting sentence: {e}", "error")
        g.db.rollback()

    # Redirect back to the view page with current filters
    return redirect(request.referrer or url_for("pattern_sentences.view"))


@bp.route("/<int:sentence_id>/verify", methods=["POST"])
def verify_sentence(sentence_id: int) -> ResponseReturnValue:
    """Mark a sentence as verified. Requires translations and level to be set."""
    sentence = g.db.query(Sentence).get(sentence_id)
    if not sentence:
        flash("Sentence not found", "error")
        return redirect(url_for("pattern_sentences.view"))

    try:
        # Check that sentence has translations and level
        existing_translations = {t.language_code for t in sentence.translations}
        target_languages = [
            lang["code"] for lang in get_languages_in_hierarchy() if lang["code"] != "en"
        ]
        has_all_translations = all(lang in existing_translations for lang in target_languages)

        if not has_all_translations:
            flash(f"Cannot verify: sentence is missing translations. Click Accept first.", "error")
            return redirect(request.referrer or url_for("pattern_sentences.view"))

        if sentence.minimum_level is None:
            flash(f"Cannot verify: sentence has no level set. Click Accept first.", "error")
            return redirect(request.referrer or url_for("pattern_sentences.view"))

        sentence.verified = True
        g.db.commit()
        flash(f"Sentence #{sentence_id} verified and removed from list", "success")

    except Exception as e:
        flash(f"Error verifying sentence: {e}", "error")
        g.db.rollback()

    # Redirect back to the view page with current filters
    return redirect(request.referrer or url_for("pattern_sentences.view"))


@bp.route("/view")
def view() -> ResponseReturnValue:
    """View generated pattern sentences with pagination."""
    page = request.args.get("page", 1, type=int)
    pattern_id = request.args.get("pattern_id", None)
    language_code = request.args.get("language_code", None)
    lemma_guid = request.args.get("lemma_guid", "").strip() or None
    show_all = request.args.get("show_all", "no")
    per_page = 20

    # Build query
    query = g.db.query(Sentence).filter(Sentence.source_filename.like("pattern:%"))

    # By default, exclude verified and rejected sentences unless specifically requested
    if show_all != "yes":
        query = query.filter(Sentence.verified == False)
        query = query.filter(Sentence.rejected == False)

    # Filter by pattern if specified
    if pattern_id:
        query = query.filter(Sentence.source_filename == f"pattern:{pattern_id}")

    # Filter by language if specified (only show sentences with translation in that language)
    if language_code:
        translation_subquery = g.db.query(SentenceTranslation.sentence_id).filter(
            SentenceTranslation.language_code == language_code
        )
        query = query.filter(Sentence.id.in_(translation_subquery))

    # Filter by lemma GUID if specified (only show sentences containing that lemma)
    if lemma_guid:
        # First find the lemma by GUID
        lemma = g.db.query(Lemma).filter(Lemma.guid == lemma_guid).first()
        if lemma:
            # Find sentences that use this lemma
            sentence_word_subquery = g.db.query(SentenceWord.sentence_id).filter(
                SentenceWord.lemma_id == lemma.id
            )
            query = query.filter(Sentence.id.in_(sentence_word_subquery))
        else:
            # If lemma GUID not found, return no results
            query = query.filter(Sentence.id == -1)

    # Get total count
    total = query.count()

    # Paginate
    sentences = (
        query.order_by(Sentence.id.desc()).limit(per_page).offset((page - 1) * per_page).all()
    )

    # Calculate pagination info
    total_pages = (total + per_page - 1) // per_page

    return render_template(
        "pattern_sentences/view.html",
        sentences=sentences,
        page=page,
        total_pages=total_pages,
        total=total,
        pattern_id=pattern_id,
        language_code=language_code,
        lemma_guid=lemma_guid,
        show_all=show_all,
        patterns=[
            {"pattern_id": row[0].removeprefix("pattern:"), "name": row[0].removeprefix("pattern:")}
            for row in g.db.query(Sentence.source_filename)
            .filter(Sentence.source_filename.like("pattern:%"))
            .distinct()
            .order_by(Sentence.source_filename)
        ],
        languages=get_languages_in_hierarchy(),
    )
