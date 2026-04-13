#!/usr/bin/python3

"""Routes for lemma management."""

from typing import Any, List, Optional, Tuple, Union

from barsukas.config import Config
from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from audioshoe.coqui.types import CoquiVoice
from audioshoe.espeak.types import EspeakVoice
from audioshoe.piper.types import PiperVoice
from audioshoe.qwen.types import QwenVoice
from clients.audio.azure_tts import AzureVoice
from clients.audio.google_tts import GoogleTtsVoice
from clients.audio.polly_tts import PollyVoice
from barsukas.helpers.lemma_display import (
    build_lemma_pronunciation_rows,
    get_pronunciation_languages,
    get_difficulty_stats,
    group_derivative_forms,
    group_populated_pronunciations,
)
from workqueue.task_queue import get_tasks_for_target
from storage.crud.derivative_form import delete_derivative_form
from storage.crud.difficulty_override import get_all_overrides_for_lemma
from storage.crud.lemma import handle_lemma_type_subtype_change
from storage.crud.operation_log import log_translation_change
from storage.models.schema import DerivativeForm, Lemma, LemmaTranslation
from storage.queries.lemma import build_lemma_search_query
from storage.translation_helpers import (
    TIER_3_LANGUAGES,
    get_all_translations,
    get_supported_languages,
)

bp = Blueprint("lemmas", __name__, url_prefix="/lemmas")


@bp.route("/add", methods=["GET", "POST"])
def add_lemma() -> ResponseReturnValue:
    """Add a new lemma."""
    import json

    from flask import current_app

    from storage.utils.enums import VALID_POS_TYPES, get_subtype_values_for_pos

    if request.method == "POST":
        if current_app.config.get("READONLY", False):
            flash("Cannot add lemma: running in read-only mode", "error")
            return redirect(url_for("lemmas.list_lemmas"))

        # Get form data
        lemma_text = request.form.get("lemma_text", "").strip()
        definition_text = request.form.get("definition_text", "").strip()
        pos_type = request.form.get("pos_type", "").strip()
        pos_subtype = request.form.get("pos_subtype", "").strip() or None
        difficulty_level_str = request.form.get("difficulty_level", "").strip()
        initial_translation_lang = request.form.get("initial_translation_lang", "").strip()
        initial_translation_text = request.form.get("initial_translation_text", "").strip()

        # Validate required fields
        if not lemma_text:
            flash("Lemma text is required", "error")
            return render_template("lemmas/add.html")

        if not definition_text:
            flash("Definition is required", "error")
            return render_template("lemmas/add.html")

        if not pos_type:
            flash("POS type is required", "error")
            return render_template("lemmas/add.html")

        if not pos_subtype:
            flash("POS subtype is required for GUID generation", "error")
            return render_template("lemmas/add.html")

        # Check if lemma already exists
        existing = (
            g.db.query(Lemma)
            .filter(Lemma.lemma_text == lemma_text, Lemma.pos_type == pos_type)
            .first()
        )

        if existing:
            flash(f'Lemma "{lemma_text}" with POS type "{pos_type}" already exists', "error")
            return redirect(url_for("lemmas.view_lemma", lemma_id=existing.id))

        # Generate GUID based on pos_subtype
        from storage.utils.guid import generate_guid

        try:
            guid = generate_guid(g.db, pos_type, pos_subtype)
        except ValueError as e:
            flash(f"Invalid POS subtype for GUID generation: {e}", "error")
            return render_template("lemmas/add.html")

        # Parse difficulty level
        difficulty_level = None
        if difficulty_level_str:
            try:
                difficulty_level = int(difficulty_level_str)
                # Validate difficulty level
                if difficulty_level != Config.EXCLUDE_DIFFICULTY_LEVEL and (
                    difficulty_level < Config.MIN_DIFFICULTY_LEVEL
                    or difficulty_level > Config.MAX_DIFFICULTY_LEVEL
                ):
                    flash(
                        f"Difficulty level must be -1 or between {Config.MIN_DIFFICULTY_LEVEL} and {Config.MAX_DIFFICULTY_LEVEL}",
                        "error",
                    )
                    return render_template("lemmas/add.html")
            except ValueError:
                flash("Invalid difficulty level", "error")
                return render_template("lemmas/add.html")

        # Create new lemma
        new_lemma = Lemma(
            lemma_text=lemma_text,
            definition_text=definition_text,
            pos_type=pos_type,
            pos_subtype=pos_subtype,
            guid=guid,
            difficulty_level=difficulty_level,
            confidence=0.0,
            verified=False,
        )

        g.db.add(new_lemma)
        g.db.flush()  # Get the ID

        # Log the creation
        log_translation_change(
            session=g.db,
            source=Config.OPERATION_LOG_SOURCE,
            operation_type="lemma_create",
            lemma_id=new_lemma.id,
            field_name="created",
            old_value=None,
            new_value=f"{lemma_text} ({pos_type})",
        )

        # Save initial translation if provided
        if initial_translation_lang and initial_translation_text:
            from storage.translation_helpers import set_translation

            try:
                set_translation(g.db, new_lemma, initial_translation_lang, initial_translation_text)
                # Log the translation
                log_translation_change(
                    session=g.db,
                    source=Config.OPERATION_LOG_SOURCE,
                    operation_type="translation_add",
                    lemma_id=new_lemma.id,
                    field_name=f"{initial_translation_lang}_translation",
                    old_value=None,
                    new_value=initial_translation_text,
                )
            except Exception as e:
                # Don't fail lemma creation if translation fails
                flash(f"Warning: Failed to save translation: {str(e)}", "warning")

        g.db.commit()

        success_message = f"Created new lemma: {lemma_text}"
        if initial_translation_lang and initial_translation_text:
            success_message += f" (with {initial_translation_lang.upper()} translation)"
        flash(success_message, "success")

        return redirect(url_for("lemmas.view_lemma", lemma_id=new_lemma.id))

    # For GET request, provide POS types and subtypes
    pos_types = sorted(list(VALID_POS_TYPES))

    # Build a mapping of POS type to subtypes for JavaScript
    pos_subtypes_map = {}
    for pos_type in pos_types:
        subtypes = get_subtype_values_for_pos(pos_type)
        if subtypes:
            pos_subtypes_map[pos_type] = subtypes

    return render_template(
        "lemmas/add.html",
        pos_types=pos_types,
        pos_subtypes_map=json.dumps(pos_subtypes_map),
    )


@bp.route("/")
def list_lemmas() -> ResponseReturnValue:
    """List all lemmas with pagination and filtering."""
    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "").strip()
    pos_type = request.args.get("pos_type", "").strip()
    pos_subtype = request.args.get("pos_subtype", "").strip()
    difficulty = request.args.get("difficulty", "", type=str).strip()
    supported_languages = get_supported_languages()
    requested_display_lang = getattr(g, "ui_lang", "en")
    display_language_code = (
        requested_display_lang if requested_display_lang in supported_languages else "en"
    )

    # Build filtered and ordered query
    query = build_lemma_search_query(
        session=g.db,
        search=search or None,
        pos_type=pos_type or None,
        pos_subtype=pos_subtype or None,
        difficulty=difficulty or None,
        display_language_code=display_language_code,
    )

    # Paginate
    total = query.count()
    lemmas = query.limit(Config.ITEMS_PER_PAGE).offset((page - 1) * Config.ITEMS_PER_PAGE).all()

    lemma_ids = [lemma.id for lemma in lemmas]
    translation_languages = {"en", display_language_code}
    translations_by_lemma: dict[int, dict[str, LemmaTranslation]] = {}
    if lemma_ids:
        translation_rows = (
            g.db.query(LemmaTranslation)
            .filter(
                LemmaTranslation.lemma_id.in_(lemma_ids),
                LemmaTranslation.language_code.in_(list(translation_languages)),
            )
            .all()
        )
        for translation_row in translation_rows:
            if translation_row.lemma_id not in translations_by_lemma:
                translations_by_lemma[translation_row.lemma_id] = {}
            translations_by_lemma[translation_row.lemma_id][
                translation_row.language_code
            ] = translation_row

    lemma_cards: list[dict[str, Any]] = []
    for lemma in lemmas:
        lemma_translations = translations_by_lemma.get(lemma.id, {})
        display_translation = lemma_translations.get(display_language_code)
        display_lemma_text = (
            display_translation.translation
            if display_language_code != "en"
            and display_translation
            and display_translation.translation
            else lemma.lemma_text
        )
        if display_language_code == "en":
            display_definition = lemma.definition_text
        elif display_translation and display_translation.definition_text:
            display_definition = display_translation.definition_text
        else:
            display_definition = f"{lemma.lemma_text}: {lemma.definition_text}"

        lemma_cards.append(
            {
                "id": lemma.id,
                "display_lemma_text": display_lemma_text,
                "display_definition": display_definition,
                "pos_type": lemma.pos_type,
                "pos_subtype": lemma.pos_subtype,
                "difficulty_level": lemma.difficulty_level,
                "verified": lemma.verified,
            }
        )

    # Get filter options in optimized queries (replaces 2 separate DISTINCT queries)
    from barsukas.helpers.db_optimization import get_lemma_list_filter_options

    filter_options = get_lemma_list_filter_options(g.db, pos_type or None)
    pos_types = filter_options["pos_types"]
    pos_subtypes = filter_options["pos_subtypes"]

    # Calculate pagination
    total_pages = (total + Config.ITEMS_PER_PAGE - 1) // Config.ITEMS_PER_PAGE

    return render_template(
        "lemmas/list.html",
        lemmas=lemma_cards,
        page=page,
        total_pages=total_pages,
        total=total,
        search=search,
        pos_type=pos_type,
        pos_subtype=pos_subtype,
        difficulty=difficulty,
        pos_types=pos_types,
        pos_subtypes=pos_subtypes,
        display_language_code=display_language_code,
    )


@bp.route("/<int:lemma_id>")
def view_lemma(lemma_id: int) -> ResponseReturnValue:
    """View a single lemma with all details."""
    from barsukas.helpers.db_optimization import get_lemma_view_data
    from storage.crud.guid_tombstone import get_tombstones_by_lemma_id

    # Get all lemma data in optimized bulk queries (replaces 10+ separate queries)
    data = get_lemma_view_data(g.db, lemma_id)

    lemma = data["lemma"]
    if not lemma:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    # Extract pre-fetched data
    translations = data["translations"]
    definitions = data["definitions"]
    translation_disambiguations = data["translation_disambiguations"]
    translation_pronunciations = data["translation_pronunciations"]
    language_names = get_supported_languages()
    overrides = data["overrides"]
    effective_levels = data["effective_levels"]
    derivative_forms = data["derivative_forms"]
    grammar_facts = data["grammar_facts"]
    audio_files = data["audio_files"]
    sentence_count = data["sentence_count"]
    needs_disambiguation_check = data["needs_disambiguation_check"]
    related_lemmas = data["related_lemmas"]

    # Get difficulty level distribution for same POS type/subtype
    difficulty_stats = get_difficulty_stats(g.db, lemma.pos_type, lemma.pos_subtype)

    # Group forms by language and type
    (
        forms_by_language,
        synonyms_by_language,
        alternative_forms_by_language,
        all_synonym_languages,
    ) = group_derivative_forms(derivative_forms)
    pronunciation_forms_by_language = group_populated_pronunciations(derivative_forms)
    pronunciation_languages = get_pronunciation_languages(derivative_forms, translations)
    lemma_pronunciation_rows = build_lemma_pronunciation_rows(
        derivative_forms,
        translations,
        translation_pronunciations,
    )

    # Get tombstone entries for this lemma
    tombstones = get_tombstones_by_lemma_id(g.db, lemma_id)

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

    queued_tasks = get_tasks_for_target(g.db, "lemma", lemma_id, limit=8)

    return render_template(
        "lemmas/view.html",
        lemma=lemma,
        translations=translations,
        definitions=definitions,
        translation_disambiguations=translation_disambiguations,
        language_names=language_names,
        overrides=overrides,
        effective_levels=effective_levels,
        difficulty_stats=difficulty_stats,
        forms_by_language=forms_by_language,
        derivative_forms=derivative_forms,
        pronunciation_forms_by_language=pronunciation_forms_by_language,
        pronunciation_languages=pronunciation_languages,
        lemma_pronunciation_rows=lemma_pronunciation_rows,
        audio_files=audio_files,
        synonyms_by_language=synonyms_by_language,
        alternative_forms_by_language=alternative_forms_by_language,
        all_synonym_languages=all_synonym_languages,
        sentence_count=sentence_count,
        needs_disambiguation_check=needs_disambiguation_check,
        grammar_facts=grammar_facts,
        tombstones=tombstones,
        openai_voices=openai_voices,
        espeak_voices=espeak_voices,
        piper_voices=piper_voices,
        coqui_voices=coqui_voices,
        qwen3_voices=qwen3_voices,
        polly_voices=polly_voices,
        azure_voices=azure_voices,
        google_voices=google_voices,
        related_lemmas=related_lemmas,
        queued_tasks=queued_tasks,
        tier_3_languages=set(TIER_3_LANGUAGES),
    )


@bp.route("/<int:lemma_id>/edit", methods=["GET", "POST"])
def edit_lemma(lemma_id: int) -> ResponseReturnValue:
    """Edit a lemma."""
    from flask import current_app

    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    if request.method == "POST":
        if current_app.config.get("READONLY", False):
            flash("Cannot update: running in read-only mode", "error")
            return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))
        # Track changes for logging
        changes: List[Tuple[str, Any, Any]] = []

        # Update basic fields
        new_lemma_text = request.form.get("lemma_text", "").strip()
        if new_lemma_text != lemma.lemma_text:
            changes.append(("lemma_text", lemma.lemma_text, new_lemma_text))
            lemma.lemma_text = new_lemma_text

        new_definition = request.form.get("definition_text", "").strip()
        if new_definition != lemma.definition_text:
            changes.append(("definition_text", lemma.definition_text, new_definition))
            lemma.definition_text = new_definition

        # Handle type/subtype changes specially
        new_pos_type = request.form.get("pos_type", "").strip()
        new_pos_subtype = request.form.get("pos_subtype", "").strip() or None

        type_changed = new_pos_type != lemma.pos_type
        subtype_changed = new_pos_subtype != lemma.pos_subtype

        if type_changed or subtype_changed:
            # Use the special handler for type/subtype changes
            # This will create tombstone, regenerate GUID, and invalidate translations/forms
            result = handle_lemma_type_subtype_change(
                session=g.db,
                lemma=lemma,
                new_pos_type=new_pos_type,
                new_pos_subtype=new_pos_subtype,
                source=Config.OPERATION_LOG_SOURCE,
                notes=f"Type/subtype changed via BARSUKAS edit form",
            )

            # Add changes to track for user feedback
            if type_changed:
                changes.append(("pos_type", result.get("old_guid", lemma.pos_type), new_pos_type))
            if subtype_changed:
                changes.append(
                    (
                        "pos_subtype",
                        lemma.pos_subtype if not subtype_changed else None,
                        new_pos_subtype,
                    )
                )

            # Flash informative message about the type/subtype change
            if result["tombstone_created"]:
                flash(
                    f"Type/subtype changed. Old GUID {result['old_guid']} tombstoned, "
                    f"new GUID: {result['new_guid']}",
                    "warning",
                )
            if result["translations_cleared"] > 0:
                flash(
                    f"Cleared {result['translations_cleared']} translation(s) due to type/subtype change",
                    "warning",
                )
            if result["derivative_forms_deleted"] > 0:
                flash(
                    f"Deleted {result['derivative_forms_deleted']} derivative form(s) due to type/subtype change",
                    "warning",
                )

        # Allow manual GUID override (but only if type/subtype didn't change)
        new_guid = request.form.get("guid", "").strip() or None
        if new_guid != lemma.guid and not (type_changed or subtype_changed):
            changes.append(("guid", lemma.guid, new_guid))
            lemma.guid = new_guid

        # Handle difficulty level
        difficulty_str = request.form.get("difficulty_level", "").strip()
        new_difficulty = None
        if difficulty_str:
            try:
                new_difficulty = int(difficulty_str)
                # Validate
                if new_difficulty != Config.EXCLUDE_DIFFICULTY_LEVEL and (
                    new_difficulty < Config.MIN_DIFFICULTY_LEVEL
                    or new_difficulty > Config.MAX_DIFFICULTY_LEVEL
                ):
                    flash(
                        f"Difficulty level must be -1 or between {Config.MIN_DIFFICULTY_LEVEL} and {Config.MAX_DIFFICULTY_LEVEL}",
                        "error",
                    )
                    return render_template("lemmas/edit.html", lemma=lemma)
            except ValueError:
                flash("Invalid difficulty level", "error")
                return render_template("lemmas/edit.html", lemma=lemma)

        if new_difficulty != lemma.difficulty_level:
            changes.append(("difficulty_level", lemma.difficulty_level, new_difficulty))
            lemma.difficulty_level = new_difficulty

        # Handle verified checkbox
        new_verified = request.form.get("verified") == "on"
        if new_verified != lemma.verified:
            changes.append(("verified", lemma.verified, new_verified))
            lemma.verified = new_verified

        # Handle confidence
        confidence_str = request.form.get("confidence", "").strip()
        if confidence_str:
            try:
                new_confidence = float(confidence_str)
                if new_confidence != lemma.confidence:
                    changes.append(("confidence", lemma.confidence, new_confidence))
                    lemma.confidence = new_confidence
            except ValueError:
                flash("Invalid confidence value", "error")
                return render_template("lemmas/edit.html", lemma=lemma)

        # Handle notes and tags
        new_notes = request.form.get("notes", "").strip() or None
        if new_notes != lemma.notes:
            changes.append(("notes", lemma.notes, new_notes))
            lemma.notes = new_notes

        new_tags = request.form.get("tags", "").strip() or None
        if new_tags != lemma.tags:
            changes.append(("tags", lemma.tags, new_tags))
            lemma.tags = new_tags

        # Handle disambiguation
        new_disambiguation = request.form.get("disambiguation", "").strip() or None
        if new_disambiguation != lemma.disambiguation:
            changes.append(("disambiguation", lemma.disambiguation, new_disambiguation))
            lemma.disambiguation = new_disambiguation

        # Log all changes
        for field_name, old_value, new_value in changes:
            log_translation_change(
                session=g.db,
                source=Config.OPERATION_LOG_SOURCE,
                operation_type="lemma_update",
                lemma_id=lemma.id,
                field_name=field_name,
                old_value=str(old_value) if old_value is not None else None,
                new_value=str(new_value) if new_value is not None else None,
            )

        g.db.commit()
        flash(f"Updated lemma: {lemma.lemma_text}", "success")
        return redirect(url_for("lemmas.view_lemma", lemma_id=lemma.id))

    # Get difficulty level distribution for same POS type/subtype
    difficulty_stats = get_difficulty_stats(g.db, lemma.pos_type, lemma.pos_subtype)

    # Get POS types and subtypes for dropdowns
    import json

    from storage.utils.enums import VALID_POS_TYPES, get_subtype_values_for_pos

    pos_types = sorted(list(VALID_POS_TYPES))

    # Build a mapping of POS type to subtypes for JavaScript
    pos_subtypes_map = {}
    for pos_type in pos_types:
        subtypes = get_subtype_values_for_pos(pos_type)
        if subtypes:
            pos_subtypes_map[pos_type] = subtypes

    return render_template(
        "lemmas/edit.html",
        lemma=lemma,
        difficulty_stats=difficulty_stats,
        pos_types=pos_types,
        pos_subtypes_map=json.dumps(pos_subtypes_map),
    )


@bp.route("/<int:lemma_id>/delete-synonym/<int:form_id>", methods=["POST"])
def delete_synonym(lemma_id: int, form_id: int) -> ResponseReturnValue:
    """Delete a single synonym or alternative form."""
    from flask import current_app

    from storage.crud.grammar_fact import update_alternate_forms_facts_after_deletion

    if current_app.config.get("READONLY", False):
        flash("Cannot delete: running in read-only mode", "error")
        return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

    # Verify the form belongs to this lemma
    form = (
        g.db.query(DerivativeForm)
        .filter(DerivativeForm.id == form_id, DerivativeForm.lemma_id == lemma_id)
        .first()
    )

    if not form:
        flash("Synonym or alternative form not found", "error")
        return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

    # Store form details for flash message and grammar fact update
    form_text = form.derivative_form_text
    form_type = form.grammatical_form.replace("_", " ").title()
    language_code = form.language_code
    grammatical_form = form.grammatical_form

    # Delete the form
    if delete_derivative_form(g.db, form_id):
        # Update grammar facts based on remaining forms
        update_alternate_forms_facts_after_deletion(
            session=g.db,
            lemma_id=lemma_id,
            language_code=language_code,
            deleted_form_type=grammatical_form,
        )

        # Log the deletion
        log_translation_change(
            session=g.db,
            source=Config.OPERATION_LOG_SOURCE,
            operation_type="derivative_form_delete",
            lemma_id=lemma_id,
            field_name=f"{language_code}_{grammatical_form}",
            old_value=form_text,
            new_value=None,
        )
        flash(f'Deleted {form_type}: "{form_text}"', "success")
    else:
        flash(f'Failed to delete {form_type}: "{form_text}"', "error")

    return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))


@bp.route("/<int:lemma_id>/delete-all-synonyms", methods=["POST"])
def delete_all_synonyms(lemma_id: int) -> ResponseReturnValue:
    """Delete all synonyms and/or alternative forms for a lemma."""
    from flask import current_app

    from storage.crud.grammar_fact import update_alternate_forms_facts_after_deletion

    if current_app.config.get("READONLY", False):
        flash("Cannot delete: running in read-only mode", "error")
        return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

    # Get optional filters from request
    lang_code = request.form.get("lang_code")  # Optional: filter by language
    form_category = request.form.get("form_category")  # 'synonyms', 'alternatives', or 'all'

    # Verify lemma exists
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    # Build query for forms to delete
    query = g.db.query(DerivativeForm).filter(DerivativeForm.lemma_id == lemma_id)

    # Apply language filter if provided
    if lang_code:
        query = query.filter(DerivativeForm.language_code == lang_code)

    # Apply form category filter
    if form_category == "synonyms":
        query = query.filter(
            DerivativeForm.grammatical_form.in_(
                [
                    "synonym",
                    "synonym_near",
                    "synonym_regional",
                    "synonym_register",
                    "synonym_related",
                    "synonym_spelling",
                    "synonym_synecdoche",
                ]
            )
        )
    elif form_category == "alternatives":
        query = query.filter(
            DerivativeForm.grammatical_form.in_(
                ["abbreviation", "expanded_form", "alternate_spelling", "alternative_form"]
            )
        )
    # If 'all' or not specified, delete both synonyms and alternatives

    forms_to_delete = query.all()

    if not forms_to_delete:
        flash("No matching forms found to delete", "warning")
        return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

    # Collect affected languages for grammar fact updates
    affected_languages = set(form.language_code for form in forms_to_delete)

    # Delete all matching forms
    deleted_count = 0
    for form in forms_to_delete:
        if delete_derivative_form(g.db, form.id):
            deleted_count += 1
            # Log each deletion
            log_translation_change(
                session=g.db,
                source=Config.OPERATION_LOG_SOURCE,
                operation_type="derivative_form_delete",
                lemma_id=lemma_id,
                field_name=f"{form.language_code}_{form.grammatical_form}",
                old_value=form.derivative_form_text,
                new_value=None,
            )

    # Update grammar facts for all affected languages
    # Since we may have deleted forms of multiple types, recalculate all facts (deleted_form_type=None)
    for language in affected_languages:
        update_alternate_forms_facts_after_deletion(
            session=g.db,
            lemma_id=lemma_id,
            language_code=language,
            deleted_form_type=None,  # Recalculate all types since bulk delete may affect multiple
        )

    # Create success message
    if deleted_count > 0:
        msg = f"Deleted {deleted_count} form(s)"
        if lang_code:
            from storage.translation_helpers import get_supported_languages

            language_names = get_supported_languages()
            msg += f" for {language_names.get(lang_code, lang_code)}"
        flash(msg, "success")
    else:
        flash("Failed to delete forms", "error")

    return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))
