#!/usr/bin/python3

"""Routes for sentence management."""

from config import Config
from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from sqlalchemy import case, func, or_

from barsukas.helpers.flash_helpers import flash_and_log
from barsukas.utils.task_queue import TaskType, enqueue_task
from wordfreq.storage.models.schema import (
    Lemma,
    Sentence,
    SentencePatternWord,
    SentenceTranslation,
    SentenceWord,
)
from wordfreq.storage.translation_helpers import get_languages_in_hierarchy, get_supported_languages

bp = Blueprint("sentences", __name__, url_prefix="/sentences")


@bp.route("/")
def list_sentences():
    """List all sentences with pagination and filtering."""
    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "").strip()
    pattern_type = request.args.get("pattern_type", "").strip()
    minimum_level = request.args.get("minimum_level", "", type=str).strip()
    show_all = request.args.get("show_all", "no")

    # Build query
    query = g.db.query(Sentence)

    # By default, exclude verified and rejected sentences unless specifically requested
    if show_all != "yes":
        query = query.filter(Sentence.verified == False)
        query = query.filter(Sentence.rejected == False)

    # Apply filters
    if search:
        # Search in sentence translations (any language)
        translation_subquery = g.db.query(SentenceTranslation.sentence_id).filter(
            SentenceTranslation.translation_text.ilike(f"%{search}%")
        )
        query = query.filter(Sentence.id.in_(translation_subquery))

    if pattern_type:
        query = query.filter(Sentence.pattern_type == pattern_type)

    if minimum_level:
        if minimum_level == "null":
            query = query.filter(Sentence.minimum_level.is_(None))
        else:
            query = query.filter(Sentence.minimum_level == int(minimum_level))

    # Order by minimum level (NULL at end), then by ID
    level_order = case(
        (Sentence.minimum_level.is_(None), 99), else_=Sentence.minimum_level  # NULL levels last
    )
    query = query.order_by(level_order, Sentence.id)

    # Paginate
    total = query.count()
    sentences = query.limit(Config.ITEMS_PER_PAGE).offset((page - 1) * Config.ITEMS_PER_PAGE).all()

    # Get unique pattern types for filter dropdown
    pattern_types = (
        g.db.query(Sentence.pattern_type).distinct().order_by(Sentence.pattern_type).all()
    )
    pattern_types = [p[0] for p in pattern_types if p[0]]

    # For each sentence, get a preview of the English translation (if available)
    sentence_previews = {}
    for sentence in sentences:
        # Get English translation for preview
        en_translation = (
            g.db.query(SentenceTranslation)
            .filter(
                SentenceTranslation.sentence_id == sentence.id,
                SentenceTranslation.language_code == "en",
            )
            .first()
        )
        if en_translation:
            sentence_previews[sentence.id] = en_translation.translation_text
        else:
            # Fall back to any translation
            any_translation = (
                g.db.query(SentenceTranslation)
                .filter(SentenceTranslation.sentence_id == sentence.id)
                .first()
            )
            sentence_previews[sentence.id] = (
                any_translation.translation_text if any_translation else "(No translation)"
            )

    # Calculate pagination
    total_pages = (total + Config.ITEMS_PER_PAGE - 1) // Config.ITEMS_PER_PAGE

    return render_template(
        "sentences/list.html",
        sentences=sentences,
        sentence_previews=sentence_previews,
        page=page,
        total_pages=total_pages,
        total=total,
        search=search,
        pattern_type=pattern_type,
        minimum_level=minimum_level,
        show_all=show_all,
        pattern_types=pattern_types,
    )


@bp.route("/<int:sentence_id>")
def view_sentence(sentence_id):
    """View a single sentence with all translations."""
    sentence = g.db.query(Sentence).get(sentence_id)
    if not sentence:
        flash("Sentence not found", "error")
        return redirect(url_for("sentences.list_sentences"))

    # Get all translations
    translations_query = (
        g.db.query(SentenceTranslation)
        .filter(SentenceTranslation.sentence_id == sentence_id)
        .order_by(SentenceTranslation.language_code)
        .all()
    )

    # Convert to dict keyed by language code
    translations = {t.language_code: t.translation_text for t in translations_query}
    language_names = get_supported_languages()

    # Get words used in the sentence (with lemma information)
    sentence_words = (
        g.db.query(SentenceWord)
        .filter(SentenceWord.sentence_id == sentence_id)
        .order_by(SentenceWord.language_code, SentenceWord.position)
        .all()
    )

    # Group by language
    words_by_language = {}
    for sw in sentence_words:
        if sw.language_code not in words_by_language:
            words_by_language[sw.language_code] = []

        # Get lemma details if available
        lemma = None
        if sw.lemma_id:
            lemma = g.db.query(Lemma).get(sw.lemma_id)

        words_by_language[sw.language_code].append(
            {
                "position": sw.position,
                "role": sw.word_role,
                "english_text": sw.english_text,
                "target_text": sw.target_language_text,
                "grammatical_form": sw.grammatical_form,
                "lemma": lemma,
                "lemma_id": sw.lemma_id,
            }
        )

    # Get pattern words (the original sentence pattern definition)
    pattern_words = (
        g.db.query(SentencePatternWord)
        .filter(SentencePatternWord.sentence_id == sentence_id)
        .order_by(SentencePatternWord.position)
        .all()
    )

    # Enrich pattern words with lemma details
    pattern_words_data = []
    for pw in pattern_words:
        lemma = g.db.query(Lemma).get(pw.lemma_id) if pw.lemma_id else None
        pattern_words_data.append(
            {
                "position": pw.position,
                "slot_name": pw.slot_name,
                "english_text": pw.english_text,
                "lemma": lemma,
                "lemma_id": pw.lemma_id,
            }
        )

    return render_template(
        "sentences/view.html",
        sentence=sentence,
        translations=translations,
        language_names=language_names,
        words_by_language=words_by_language,
        pattern_words=pattern_words_data,
    )


@bp.route("/<int:sentence_id>/update_level", methods=["POST"])
def update_level(sentence_id):
    """Update the minimum level for a sentence."""
    sentence = g.db.query(Sentence).get(sentence_id)
    if not sentence:
        flash("Sentence not found", "error")
        return redirect(url_for("sentences.list_sentences"))

    new_level = request.form.get("minimum_level", "").strip()

    try:
        if new_level == "" or new_level.lower() == "null":
            sentence.minimum_level = None
            flash(f"Sentence level cleared", "success")
        else:
            sentence.minimum_level = int(new_level)
            flash(f"Sentence level updated to {sentence.minimum_level}", "success")

        g.db.commit()
    except ValueError:
        flash("Invalid level value. Must be a number or empty.", "error")
    except Exception as e:
        flash(f"Error updating sentence level: {e}", "error")
        g.db.rollback()

    return redirect(url_for("sentences.view_sentence", sentence_id=sentence_id))


@bp.route("/<int:sentence_id>/auto_populate_level", methods=["POST"])
def auto_populate_level(sentence_id):
    """Auto-populate the minimum level based on max difficulty_level of words in the sentence."""
    sentence = g.db.query(Sentence).get(sentence_id)
    if not sentence:
        flash("Sentence not found", "error")
        return redirect(url_for("sentences.list_sentences"))

    try:
        # Get all words in the sentence with lemmas
        sentence_words = (
            g.db.query(SentenceWord)
            .filter(SentenceWord.sentence_id == sentence_id)
            .filter(SentenceWord.lemma_id.isnot(None))
            .all()
        )

        if not sentence_words:
            flash("No words with lemmas found in this sentence", "warning")
            return redirect(url_for("sentences.view_sentence", sentence_id=sentence_id))

        # Get the max difficulty_level from all lemmas
        max_level = None
        for sw in sentence_words:
            lemma = g.db.query(Lemma).get(sw.lemma_id)
            if lemma and lemma.difficulty_level is not None:
                if max_level is None or lemma.difficulty_level > max_level:
                    max_level = lemma.difficulty_level

        if max_level is None:
            flash("No lemmas with difficulty levels found in this sentence", "warning")
            return redirect(url_for("sentences.view_sentence", sentence_id=sentence_id))

        # Update the sentence level
        sentence.minimum_level = max_level
        g.db.commit()

        flash(f"Sentence level auto-populated to {max_level} (max word level)", "success")

    except Exception as e:
        flash(f"Error auto-populating level: {e}", "error")
        g.db.rollback()

    return redirect(url_for("sentences.view_sentence", sentence_id=sentence_id))


@bp.route("/<int:sentence_id>/translate", methods=["POST"])
def translate_sentence(sentence_id):
    """Translate a sentence to selected languages."""
    sentence = g.db.query(Sentence).get(sentence_id)
    if not sentence:
        flash("Sentence not found", "error")
        return redirect(url_for("sentences.list_sentences"))

    # Get selected languages from form
    selected_languages = request.form.getlist("languages")

    if not selected_languages:
        flash("Please select at least one language to translate to", "warning")
        return redirect(url_for("sentences.view_sentence", sentence_id=sentence_id))

    # Check if sentence has English translation
    en_translation = (
        g.db.query(SentenceTranslation)
        .filter_by(sentence_id=sentence_id, language_code="en")
        .first()
    )

    if not en_translation:
        flash(
            "Sentence must have an English translation before translating to other languages",
            "error",
        )
        return redirect(url_for("sentences.view_sentence", sentence_id=sentence_id))

    try:
        # Enqueue translation task to work queue
        result = enqueue_task(
            g.db,
            task_type=TaskType.TRANSLATE_SENTENCE,
            target_type="sentence",
            target_id=sentence_id,
            payload={"sentence_id": sentence_id, "selected_languages": selected_languages},
            dedup_key=f"{TaskType.TRANSLATE_SENTENCE}:{sentence_id}:{':'.join(sorted(selected_languages))}",
        )

        if result.created:
            lang_names = [get_supported_languages().get(lang, lang) for lang in selected_languages]
            flash(
                f"Queued translation to: {', '.join(lang_names)}. Results will appear soon.",
                "success",
            )
        else:
            flash(
                "A translation task for these languages is already in progress for this sentence.",
                "info",
            )

        g.db.commit()

    except Exception as e:
        flash(f"Error queueing translation task: {e}", "error")
        g.db.rollback()

    return redirect(url_for("sentences.view_sentence", sentence_id=sentence_id))


@bp.route("/<int:sentence_id>/accept", methods=["POST"])
def accept_sentence(sentence_id):
    """Accept a sentence: generate translations for all languages and auto-populate level.

    This does NOT verify the sentence - that requires a separate Verify action.
    """
    sentence = g.db.query(Sentence).get(sentence_id)
    if not sentence:
        flash("Sentence not found", "error")
        return redirect(url_for("sentences.list_sentences"))

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
                return redirect(request.referrer or url_for("sentences.list_sentences"))

        # Check if sentence already has translations for all languages
        existing_translations = {t.language_code for t in sentence.translations}
        target_languages = [lang["code"] for lang in get_languages_in_hierarchy() if lang["code"] != "en"]
        has_all_translations = all(lang in existing_translations for lang in target_languages)

        # Check that all per-word lemma translations exist BEFORE generating sentence translations
        from wordfreq.storage.translation_helpers import get_translation

        missing_translations = []

        for sw in sentence_words:
            lemma = g.db.query(Lemma).get(sw.lemma_id)
            if lemma:
                for lang_code in target_languages:
                    if not get_translation(g.db, lemma, lang_code):
                        missing_translations.append(
                            {"word": lemma.lemma_text, "language": lang_code}
                        )

        if missing_translations:
            # Group by word for cleaner error messages
            by_word = {}
            for item in missing_translations:
                word = item["word"]
                lang = item["language"]
                if word not in by_word:
                    by_word[word] = []
                by_word[word].append(lang)

            error_parts = [f"'{word}' ({', '.join(langs)})" for word, langs in by_word.items()]
            error_msg = (
                f"Cannot accept: Missing per-word translations for: {'; '.join(error_parts)}"
            )
            flash_and_log(error_msg, "error")
            return redirect(request.referrer or url_for("sentences.list_sentences"))

        # Generate missing translations (only if validation passed)
        if not has_all_translations:
            from wordfreq.translation.sentence import translate_sentence

            translate_sentence(sentence_id, target_languages, g.db, model="gpt-5-mini")

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
    return redirect(request.referrer or url_for("sentences.list_sentences"))


@bp.route("/<int:sentence_id>/verify", methods=["POST"])
def verify_sentence(sentence_id):
    """Mark a sentence as verified. Requires translations and level to be set."""
    sentence = g.db.query(Sentence).get(sentence_id)
    if not sentence:
        flash("Sentence not found", "error")
        return redirect(url_for("sentences.list_sentences"))

    try:
        # Check that sentence has translations and level
        existing_translations = {t.language_code for t in sentence.translations}
        target_languages = [lang["code"] for lang in get_languages_in_hierarchy() if lang["code"] != "en"]
        has_all_translations = all(lang in existing_translations for lang in target_languages)

        if not has_all_translations:
            flash(f"Cannot verify: sentence is missing translations. Click Accept first.", "error")
            return redirect(request.referrer or url_for("sentences.list_sentences"))

        if sentence.minimum_level is None:
            flash(f"Cannot verify: sentence has no level set. Click Accept first.", "error")
            return redirect(request.referrer or url_for("sentences.list_sentences"))

        sentence.verified = True
        g.db.commit()
        flash(f"Sentence #{sentence_id} verified and removed from list", "success")

    except Exception as e:
        flash(f"Error verifying sentence: {e}", "error")
        g.db.rollback()

    # Redirect back to the view page with current filters
    return redirect(request.referrer or url_for("sentences.list_sentences"))


@bp.route("/<int:sentence_id>/reject", methods=["POST"])
def reject_sentence(sentence_id):
    """Mark a sentence as rejected so it won't be regenerated."""
    sentence = g.db.query(Sentence).get(sentence_id)
    if not sentence:
        flash("Sentence not found", "error")
        return redirect(url_for("sentences.list_sentences"))

    try:
        sentence.rejected = True
        g.db.commit()
        flash(f"Sentence #{sentence_id} marked as rejected", "success")
    except Exception as e:
        flash(f"Error rejecting sentence: {e}", "error")
        g.db.rollback()

    # Redirect back to the view page with current filters
    return redirect(request.referrer or url_for("sentences.list_sentences"))
