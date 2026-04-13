#!/usr/bin/python3

"""Routes for sentence management."""

from typing import Any, Union

from barsukas.config import Config
from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from sqlalchemy import case, func, or_
from werkzeug.wrappers import Response

from audioshoe.coqui.types import CoquiVoice
from audioshoe.espeak.types import EspeakVoice
from audioshoe.piper.types import PiperVoice
from audioshoe.qwen.types import QwenVoice
from clients.audio.azure_tts import AzureVoice
from clients.audio.google_tts import GoogleTtsVoice
from clients.audio.polly_tts import PollyVoice
from barsukas.helpers.flash_helpers import flash_and_log
from workqueue.task_queue import TaskType, enqueue_task, get_tasks_for_target
from storage.models.schema import (
    AudioQualityReview,
    Conversation,
    ConversationSentence,
    Lemma,
    LemmaTranslation,
    Sentence,
    SentencePatternWord,
    SentenceTranslation,
    SentenceWord,
)
from storage.translation_helpers import (
    get_languages_in_hierarchy,
    get_supported_languages,
    get_tier_1_and_tier_2_languages,
    normalize_llm_language_codes,
)

bp = Blueprint("sentences", __name__, url_prefix="/sentences")


@bp.route("/")
def list_sentences() -> ResponseReturnValue:
    """List all sentences with pagination and filtering."""
    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "").strip()
    pattern_type = request.args.get("pattern_type", "").strip()
    minimum_level = request.args.get("minimum_level", "", type=str).strip()
    has_translation = request.args.get("has_translation", "").strip()
    exclude_rejected = request.args.get("exclude_rejected", "no")
    exclude_verified = request.args.get("exclude_verified", "no")

    # Build query
    query = g.db.query(Sentence)

    # Apply optional filters for rejected and verified sentences
    if exclude_rejected == "yes":
        query = query.filter(Sentence.rejected == False)
    if exclude_verified == "yes":
        query = query.filter(Sentence.verified == False)

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
        elif minimum_level.endswith("+"):
            # "8+" means level >= 8
            level_value = int(minimum_level[:-1])
            query = query.filter(Sentence.minimum_level >= level_value)
        else:
            query = query.filter(Sentence.minimum_level == int(minimum_level))

    if has_translation:
        # Filter sentences that have a translation in the specified language
        translation_subquery = g.db.query(SentenceTranslation.sentence_id).filter(
            SentenceTranslation.language_code == has_translation
        )
        query = query.filter(Sentence.id.in_(translation_subquery))

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

    # Batch load ALL translations for sentences in ONE query instead of 2N queries
    sentence_ids = [s.id for s in sentences]
    sentence_previews = {}
    if sentence_ids:
        all_translations = (
            g.db.query(SentenceTranslation)
            .filter(SentenceTranslation.sentence_id.in_(sentence_ids))
            .all()
        )

        # Group translations by sentence_id
        translations_by_sentence: dict[int, dict[str, str]] = {}
        for t in all_translations:
            if t.sentence_id not in translations_by_sentence:
                translations_by_sentence[t.sentence_id] = {}
            translations_by_sentence[t.sentence_id][t.language_code] = t.translation_text

        # Build previews: prefer English, fall back to any
        for sentence in sentences:
            trans = translations_by_sentence.get(sentence.id, {})
            if "en" in trans:
                sentence_previews[sentence.id] = trans["en"]
            elif trans:
                # Get first available translation
                sentence_previews[sentence.id] = next(iter(trans.values()))
            else:
                sentence_previews[sentence.id] = "(No translation)"

    # Calculate pagination
    total_pages = (total + Config.ITEMS_PER_PAGE - 1) // Config.ITEMS_PER_PAGE

    # Get languages for the translation filter dropdown
    languages = get_languages_in_hierarchy()

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
        has_translation=has_translation,
        exclude_rejected=exclude_rejected,
        exclude_verified=exclude_verified,
        pattern_types=pattern_types,
        languages=languages,
    )


@bp.route("/<int:sentence_id>")
def view_sentence(sentence_id: int) -> Union[str, Response]:
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

    # Get pattern words (the original sentence pattern definition)
    pattern_words = (
        g.db.query(SentencePatternWord)
        .filter(SentencePatternWord.sentence_id == sentence_id)
        .order_by(SentencePatternWord.position)
        .all()
    )

    # Batch load ALL lemmas for sentence words and pattern words in ONE query
    all_lemma_ids = set()
    for sw in sentence_words:
        if sw.lemma_id:
            all_lemma_ids.add(sw.lemma_id)
    for pw in pattern_words:
        if pw.lemma_id:
            all_lemma_ids.add(pw.lemma_id)

    lemmas_by_id: dict[int, Lemma] = {}
    lemma_display_by_id: dict[int, str] = {}
    ui_lang = getattr(g, "ui_lang", "en")
    if all_lemma_ids:
        lemmas = g.db.query(Lemma).filter(Lemma.id.in_(all_lemma_ids)).all()
        lemmas_by_id = {lemma.id: lemma for lemma in lemmas}
        lemma_display_by_id = {lemma.id: lemma.lemma_text for lemma in lemmas}

        if ui_lang != "en":
            localized_translations = (
                g.db.query(LemmaTranslation)
                .filter(
                    LemmaTranslation.lemma_id.in_(all_lemma_ids),
                    LemmaTranslation.language_code == ui_lang,
                )
                .all()
            )
            for translation in localized_translations:
                if translation.translation:
                    lemma_display_by_id[translation.lemma_id] = translation.translation

    # Group sentence words by language
    words_by_language: dict[str, list[dict[str, Any]]] = {}
    for sw in sentence_words:
        if sw.language_code not in words_by_language:
            words_by_language[sw.language_code] = []

        lemma = lemmas_by_id.get(sw.lemma_id) if sw.lemma_id else None

        words_by_language[sw.language_code].append(
            {
                "position": sw.position,
                "role": sw.word_role,
                "english_text": sw.english_text,
                "target_text": sw.target_language_text,
                "grammatical_form": sw.grammatical_form,
                "lemma": lemma,
                "lemma_id": sw.lemma_id,
                "lemma_display_text": (
                    lemma_display_by_id.get(lemma.id, lemma.lemma_text) if lemma else None
                ),
            }
        )

    # Enrich pattern words with lemma details
    pattern_words_data = []
    for pw in pattern_words:
        lemma = lemmas_by_id.get(pw.lemma_id) if pw.lemma_id else None
        pattern_words_data.append(
            {
                "position": pw.position,
                "slot_name": pw.slot_name,
                "english_text": pw.english_text,
                "lemma": lemma,
                "lemma_id": pw.lemma_id,
                "lemma_display_text": (
                    lemma_display_by_id.get(lemma.id, lemma.lemma_text) if lemma else None
                ),
            }
        )

    # Get audio files for this sentence
    audio_files = (
        g.db.query(AudioQualityReview).filter(AudioQualityReview.sentence_id == sentence_id).all()
    )

    # Group audio by language and voice
    audio_by_language: dict[str, list[AudioQualityReview]] = {}
    for audio in audio_files:
        if audio.language_code not in audio_by_language:
            audio_by_language[audio.language_code] = []
        audio_by_language[audio.language_code].append(audio)

    # Get conversations that include this sentence
    conversation_links = (
        g.db.query(ConversationSentence, Conversation)
        .join(Conversation, ConversationSentence.conversation_id == Conversation.id)
        .filter(ConversationSentence.sentence_id == sentence_id)
        .all()
    )
    conversations_data = [
        {
            "conversation": conv,
            "position": cs.position,
            "speaker": cs.speaker,
        }
        for cs, conv in conversation_links
    ]

    # Get queued background tasks for this sentence
    queued_tasks = get_tasks_for_target(g.db, "sentence", sentence_id, limit=8)

    # Prepare voice options for audio generation
    openai_voices = [
        "ash",
        "alloy",
        "nova",
        "ballad",
        "coral",
        "echo",
        "fable",
        "onyx",
        "sage",
        "shimmer",
    ]

    # eSpeak-NG voices by language
    espeak_voices = {}
    for lang_code in language_names.keys():
        espeak_voice_list = EspeakVoice.get_voices_for_language(lang_code)
        espeak_voices[lang_code] = [{"name": v.name, "gender": v.gender} for v in espeak_voice_list]

    # Piper voices by language
    piper_voices = {}
    for lang_code in language_names.keys():
        piper_voice_list = PiperVoice.get_voices_for_language(lang_code)
        piper_voices[lang_code] = [
            {"name": v.name, "ui_name": v.ui_name, "gender": v.gender} for v in piper_voice_list
        ]

    # Coqui voices by language
    coqui_voices = {}
    for lang_code in language_names.keys():
        coqui_voice_list = CoquiVoice.get_voices_for_language(lang_code)
        coqui_voices[lang_code] = [
            {"name": v.name, "ui_name": v.ui_name, "gender": v.gender} for v in coqui_voice_list
        ]

    # Qwen3 voices by language
    qwen3_voices = {}
    for lang_code in language_names.keys():
        qwen3_voice_list = QwenVoice.get_voices_for_language(lang_code)
        qwen3_voices[lang_code] = [
            {"name": v.name, "ui_name": v.ui_name, "gender": v.gender} for v in qwen3_voice_list
        ]

    # Amazon Polly voices by language
    polly_voices = {}
    for lang_code in language_names.keys():
        polly_voice_list = PollyVoice.get_voices_for_language(lang_code)
        polly_voices[lang_code] = [
            {"name": v.name, "ui_name": v.ui_name, "gender": v.gender} for v in polly_voice_list
        ]

    # Azure TTS voices by language
    azure_voices = {}
    for lang_code in language_names.keys():
        azure_voice_list = AzureVoice.get_voices_for_language(lang_code)
        azure_voices[lang_code] = [
            {"name": v.name, "ui_name": v.ui_name, "gender": v.gender} for v in azure_voice_list
        ]

    # Google Cloud TTS voices by language
    google_voices = {}
    for lang_code in language_names.keys():
        google_voice_list = GoogleTtsVoice.get_voices_for_language(lang_code)
        google_voices[lang_code] = [
            {"name": v.name, "ui_name": v.ui_name, "gender": v.gender} for v in google_voice_list
        ]

    return render_template(
        "sentences/view.html",
        sentence=sentence,
        translations=translations,
        language_names=language_names,
        words_by_language=words_by_language,
        pattern_words=pattern_words_data,
        audio_by_language=audio_by_language,
        conversations_data=conversations_data,
        queued_tasks=queued_tasks,
        openai_voices=openai_voices,
        espeak_voices=espeak_voices,
        piper_voices=piper_voices,
        coqui_voices=coqui_voices,
        qwen3_voices=qwen3_voices,
        polly_voices=polly_voices,
        azure_voices=azure_voices,
        google_voices=google_voices,
    )


@bp.route("/<int:sentence_id>/update_level", methods=["POST"])
def update_level(sentence_id: int) -> Response:
    """Update the minimum level for a sentence."""
    if current_app.config.get("READONLY"):
        flash("Cannot modify data in read-only mode", "error")
        return redirect(url_for("sentences.view_sentence", sentence_id=sentence_id))

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
def auto_populate_level(sentence_id: int) -> Response:
    """Auto-populate the minimum level based on max difficulty_level of words in the sentence."""
    if current_app.config.get("READONLY"):
        flash("Cannot modify data in read-only mode", "error")
        return redirect(url_for("sentences.view_sentence", sentence_id=sentence_id))

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

        # Batch load ALL lemmas in ONE query instead of N queries
        lemma_ids = [sw.lemma_id for sw in sentence_words]
        lemmas_by_id = {}
        if lemma_ids:
            lemmas = g.db.query(Lemma).filter(Lemma.id.in_(lemma_ids)).all()
            lemmas_by_id = {lemma.id: lemma for lemma in lemmas}

        # Get the max difficulty_level from all lemmas
        max_level = None
        for sw in sentence_words:
            lemma = lemmas_by_id.get(sw.lemma_id)
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
def translate_sentence(sentence_id: int) -> Response:
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

    requested_language_count = len(selected_languages)
    selected_languages = normalize_llm_language_codes(
        selected_languages,
        operation_name="Barsukas sentence translation",
        all_expansion=get_tier_1_and_tier_2_languages(),
    )

    if not selected_languages:
        flash("No valid target languages after normalization", "warning")
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
            task_type=TaskType.SENTENCES_TRANSLATE,
            target_type="sentence",
            target_id=sentence_id,
            payload={"sentence_id": sentence_id, "selected_languages": selected_languages},
            dedup_key=f"{TaskType.SENTENCES_TRANSLATE}:{sentence_id}:{':'.join(sorted(selected_languages))}",
        )

        if result.created:
            lang_names = [get_supported_languages().get(lang, lang) for lang in selected_languages]
            flash(
                f"Queued translation to: {', '.join(lang_names)}. Results will appear soon.",
                "success",
            )
            if requested_language_count > len(selected_languages):
                flash(
                    f"Requested {requested_language_count} languages; using first {len(selected_languages)}.",
                    "warning",
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
def accept_sentence(sentence_id: int) -> Response:
    """Accept a sentence: generate translations for all languages and auto-populate level.

    This does NOT verify the sentence - that requires a separate Verify action.
    """
    if current_app.config.get("READONLY"):
        flash("Cannot modify data in read-only mode", "error")
        return redirect(url_for("sentences.list_sentences"))

    sentence = g.db.query(Sentence).get(sentence_id)
    if not sentence:
        flash("Sentence not found", "error")
        return redirect(url_for("sentences.list_sentences"))

    try:
        # Get all sentence words with lemma_id
        sentence_words = (
            g.db.query(SentenceWord)
            .filter(SentenceWord.sentence_id == sentence_id)
            .filter(SentenceWord.lemma_id.isnot(None))
            .all()
        )

        # Batch load ALL lemmas in ONE query instead of 3N queries
        lemma_ids = [sw.lemma_id for sw in sentence_words]
        lemmas_by_id = {}
        if lemma_ids:
            lemmas = g.db.query(Lemma).filter(Lemma.id.in_(lemma_ids)).all()
            lemmas_by_id = {lemma.id: lemma for lemma in lemmas}

        # Check if any word has level -1
        for sw in sentence_words:
            lemma = lemmas_by_id.get(sw.lemma_id)
            if lemma and lemma.difficulty_level == -1:
                flash(
                    f"Cannot accept: word '{lemma.guid or lemma.lemma_text}' has difficulty level -1",
                    "error",
                )
                return redirect(request.referrer or url_for("sentences.list_sentences"))

        # Check if sentence already has translations for all languages
        existing_translations = {t.language_code for t in sentence.translations}
        target_languages = [
            lang["code"] for lang in get_languages_in_hierarchy() if lang["code"] != "en"
        ]
        has_all_translations = all(lang in existing_translations for lang in target_languages)

        # Batch load ALL lemma translations in ONE query for the missing translations check
        from storage.models.schema import LemmaTranslation

        all_lemma_translations: dict[int, set[str]] = {}
        if lemma_ids:
            translations = (
                g.db.query(LemmaTranslation).filter(LemmaTranslation.lemma_id.in_(lemma_ids)).all()
            )
            for t in translations:
                if t.lemma_id not in all_lemma_translations:
                    all_lemma_translations[t.lemma_id] = set()
                all_lemma_translations[t.lemma_id].add(t.language_code)

        # Check that all per-word lemma translations exist BEFORE generating sentence translations
        missing_translations = []

        for sw in sentence_words:
            lemma = lemmas_by_id.get(sw.lemma_id)
            if lemma:
                existing_langs = all_lemma_translations.get(lemma.id, set())
                for lang_code in target_languages:
                    if lang_code not in existing_langs:
                        missing_translations.append(
                            {"word": lemma.lemma_text, "language": lang_code}
                        )

        if missing_translations:
            # Group by word for cleaner error messages
            by_word: dict[str, list[str]] = {}
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
            from sentences.translation import translate_sentence

            translate_sentence(sentence_id, target_languages, g.db, model="gpt-5.4-mini")

        # Auto-populate the level if not set (reuse already-loaded lemmas)
        if sentence.minimum_level is None:
            max_level = None
            for sw in sentence_words:
                lemma = lemmas_by_id.get(sw.lemma_id)
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
def verify_sentence(sentence_id: int) -> Response:
    """Mark a sentence as verified. Requires translations and level to be set."""
    if current_app.config.get("READONLY"):
        flash("Cannot modify data in read-only mode", "error")
        return redirect(url_for("sentences.list_sentences"))

    sentence = g.db.query(Sentence).get(sentence_id)
    if not sentence:
        flash("Sentence not found", "error")
        return redirect(url_for("sentences.list_sentences"))

    try:
        # Check that sentence has translations and level
        existing_translations = {t.language_code for t in sentence.translations}
        target_languages = [
            lang["code"] for lang in get_languages_in_hierarchy() if lang["code"] != "en"
        ]
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
def reject_sentence(sentence_id: int) -> Response:
    """Mark a sentence as rejected so it won't be regenerated."""
    if current_app.config.get("READONLY"):
        flash("Cannot modify data in read-only mode", "error")
        return redirect(url_for("sentences.list_sentences"))

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


@bp.route("/<int:sentence_id>/unverify", methods=["POST"])
def unverify_sentence(sentence_id: int) -> Response:
    """Unverify a sentence and mark it as rejected."""
    if current_app.config.get("READONLY"):
        flash("Cannot modify data in read-only mode", "error")
        return redirect(url_for("sentences.view_sentence", sentence_id=sentence_id))

    sentence = g.db.query(Sentence).get(sentence_id)
    if not sentence:
        flash("Sentence not found", "error")
        return redirect(url_for("sentences.list_sentences"))

    try:
        sentence.verified = False
        sentence.rejected = True
        g.db.commit()
        flash(f"Sentence #{sentence_id} unverified and marked as rejected", "success")
    except Exception as e:
        flash(f"Error unverifying sentence: {e}", "error")
        g.db.rollback()

    return redirect(url_for("sentences.view_sentence", sentence_id=sentence_id))
