#!/usr/bin/python3

"""Routes for sentence management."""

from typing import Any, Optional, Union

import constants
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
from barsukas.helpers.elements import group_language_values
from barsukas.helpers.flash_helpers import flash_and_log
from langtools.ud_relations import ROOT_HEAD_POSITION
from workqueue.task_queue import TaskType, enqueue_task, get_tasks_for_target
from storage.models.schema import (
    AudioQualityReview,
    Conversation,
    ConversationSentence,
    Lemma,
    LemmaTranslation,
    Sentence,
    SentenceWordHint,
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


def _build_dependency_tree(language_words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Nest one language's words into a UD dependency tree for display.

    Returns a list of root nodes, each ``{"word": ..., "children": [...]}``,
    with children ordered by sentence position. Returns ``[]`` when the
    language has no UD annotation, so the template can simply omit the view.

    Deliberately tolerant of malformed graphs: rows can predate validation, a
    language can be partially annotated, and a head can point at a position
    that no longer exists. Anything unreachable from a root is surfaced as an
    additional root rather than silently dropped, and a cycle cannot hang the
    request because each word is attached at most once.
    """
    annotated = [word for word in language_words if word.get("ud_head_position") is not None]
    if not annotated:
        return []

    nodes: dict[int, dict[str, Any]] = {
        word["position"]: {"word": word, "children": []} for word in annotated
    }

    # Resolve each word to the parent it will actually hang from. A cycle must
    # be broken *here*, while building: attaching both members of a cycle to
    # each other would make the nested structure self-referential and the
    # recursive template macro would never terminate.
    parent_position: dict[int, Optional[int]] = {}
    for position in sorted(nodes):
        head_position = nodes[position]["word"]["ud_head_position"]
        # Head of -1, a self-loop, or a head naming a word that isn't here:
        # this word becomes a root of its own subtree.
        if (
            head_position == ROOT_HEAD_POSITION
            or head_position == position
            or head_position not in nodes
        ):
            parent_position[position] = None
            continue

        # Walk up from the prospective parent. If we arrive back at this word,
        # attaching would close a loop, so this word becomes a root instead.
        ancestor: Optional[int] = head_position
        seen: set[int] = {position}
        while ancestor is not None and ancestor in parent_position:
            if ancestor in seen:
                break
            seen.add(ancestor)
            ancestor = parent_position[ancestor]
        parent_position[position] = None if ancestor == position else head_position

    roots: list[dict[str, Any]] = []
    for position in sorted(nodes):
        node = nodes[position]
        head_position = parent_position[position]
        if head_position is None:
            # Flag roots that are only roots because the parse was broken, so a
            # bad tree looks wrong rather than looking deliberate.
            if node["word"]["ud_head_position"] != ROOT_HEAD_POSITION:
                node["orphaned"] = True
            roots.append(node)
        else:
            nodes[head_position]["children"].append(node)

    return roots


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

    # Get word hints (the words this sentence was generated to use)
    word_hints = (
        g.db.query(SentenceWordHint)
        .filter(SentenceWordHint.sentence_id == sentence_id)
        .order_by(SentenceWordHint.position)
        .all()
    )

    # Batch load ALL lemmas for sentence words and word hints in ONE query
    all_lemma_ids = set()
    for sw in sentence_words:
        if sw.lemma_id:
            all_lemma_ids.add(sw.lemma_id)
    for pw in word_hints:
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

    # Surface form of each word by (language, position), so a UD head — stored
    # as a bare integer — can be shown as the word it actually points at.
    surface_by_language_position: dict[tuple[str, int], str] = {
        (sw.language_code, sw.position): (sw.target_language_text or "") for sw in sentence_words
    }

    # Group sentence words by language
    words_by_language: dict[str, list[dict[str, Any]]] = {}
    for sw in sentence_words:
        if sw.language_code not in words_by_language:
            words_by_language[sw.language_code] = []

        lemma = lemmas_by_id.get(sw.lemma_id) if sw.lemma_id else None

        if sw.ud_head_position is None:
            ud_head_text = None
        elif sw.ud_head_position == ROOT_HEAD_POSITION:
            ud_head_text = "root"
        else:
            ud_head_text = surface_by_language_position.get((sw.language_code, sw.ud_head_position))

        words_by_language[sw.language_code].append(
            {
                "position": sw.position,
                "part_of_speech": sw.part_of_speech,
                "english_text": sw.english_text,
                "target_text": sw.target_language_text,
                "grammatical_form": sw.grammatical_form,
                "ud_relation": sw.ud_relation,
                "ud_head_position": sw.ud_head_position,
                "ud_head_text": ud_head_text,
                "lemma": lemma,
                "lemma_id": sw.lemma_id,
                "lemma_display_text": (
                    lemma_display_by_id.get(lemma.id, lemma.lemma_text) if lemma else None
                ),
            }
        )

    # Nested dependency tree per language, for the visual view that accompanies
    # the flat table. Built here rather than in the template because nesting is
    # data, not presentation.
    dependency_trees_by_language: dict[str, list[dict[str, Any]]] = {}
    ud_languages: set[str] = set()
    for language_code, language_words in words_by_language.items():
        if any(
            word["ud_relation"] is not None or word["ud_head_position"] is not None
            for word in language_words
        ):
            ud_languages.add(language_code)
        tree = _build_dependency_tree(language_words)
        if tree:
            dependency_trees_by_language[language_code] = tree

    # Aggregate lemma usage across languages: which lemma_guids appear in which
    # decomposed languages, with their surface form. Used to surface cross-lingual
    # alignment and flag potential decomposition gaps (a lemma missing from just
    # one or two languages is often a translation/decomposition error).
    decomposed_langs: set[str] = set(words_by_language.keys())
    n_decomposed = len(decomposed_langs)
    # Threshold: flag when missing <=1 lang (or <=2 when N>8)
    miss_threshold = 2 if n_decomposed > 8 else 1

    lemma_usage: dict[int, dict[str, Any]] = {}
    for sw in sentence_words:
        if not sw.lemma_id:
            continue
        lemma = lemmas_by_id.get(sw.lemma_id)
        if not lemma:
            continue
        entry = lemma_usage.setdefault(
            sw.lemma_id,
            {
                "lemma": lemma,
                "lemma_id": sw.lemma_id,
                "lemma_display_text": lemma_display_by_id.get(lemma.id, lemma.lemma_text),
                "surfaces": {},  # lang_code -> surface form
            },
        )
        # Keep first surface form seen per language (sentence_words is ordered by lang, position)
        if sw.language_code not in entry["surfaces"]:
            entry["surfaces"][sw.language_code] = sw.target_language_text

    # Function-word POS types: extra occurrences in just a few languages
    # (e.g. an extra "from" in 1/9 languages) are usually noise, not signal.
    function_word_pos_types = {
        "preposition",
        "conjunction",
        "article",
        "determiner",
        "interjection",
        "particle",
    }
    most_threshold = n_decomposed - miss_threshold

    lemmas_used: list[dict[str, Any]] = []
    for entry in lemma_usage.values():
        present = set(entry["surfaces"].keys())
        missing = sorted(decomposed_langs - present)
        count = len(present)
        entry["language_count"] = count
        entry["missing_languages"] = missing
        entry["flag_missing"] = 0 < len(missing) <= miss_threshold and count >= most_threshold
        if entry["lemma"].pos_type in function_word_pos_types and count < most_threshold:
            continue
        lemmas_used.append(entry)
    lemmas_used.sort(key=lambda e: (-e["language_count"], e["lemma_display_text"] or ""))

    # Enrich word hints with lemma details
    word_hints_data = []
    for pw in word_hints:
        lemma = lemmas_by_id.get(pw.lemma_id) if pw.lemma_id else None
        word_hints_data.append(
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
        # The flat translations dict above still drives the "which languages are
        # missing" checkboxes on the add-translation form; the grouped values
        # feed the shared elements/_language_values.html table.
        values_by_language=group_language_values(sentence.language_values),
        language_names=language_names,
        words_by_language=words_by_language,
        dependency_trees_by_language=dependency_trees_by_language,
        ud_languages=ud_languages,
        lemmas_used=lemmas_used,
        n_decomposed_languages=n_decomposed,
        word_hints=word_hints_data,
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

    # The sentence must have at least one translation row; the worker picks a
    # source language from whatever exists (preferring English) and produces
    # English on the fly when missing.
    has_any_translation = (
        g.db.query(SentenceTranslation).filter_by(sentence_id=sentence_id).first() is not None
    )
    if not has_any_translation:
        flash(
            "Sentence has no translations yet; cannot determine source language.",
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

            translate_sentence(sentence_id, target_languages, g.db, model=constants.DEFAULT_MODEL)

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
