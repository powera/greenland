#!/usr/bin/python3

"""Routes for lemma management."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from sqlalchemy import or_, func, case

from wordfreq.storage.models.schema import Lemma, DerivativeForm
from wordfreq.storage.crud.operation_log import log_translation_change
from wordfreq.storage.crud.difficulty_override import (
    get_all_overrides_for_lemma,
    get_effective_difficulty_level,
)
from wordfreq.storage.translation_helpers import get_all_translations, get_supported_languages
from wordfreq.storage.crud.derivative_form import delete_derivative_form
from wordfreq.storage.crud.lemma import handle_lemma_type_subtype_change
from config import Config

bp = Blueprint("lemmas", __name__, url_prefix="/lemmas")


@bp.route("/add", methods=["GET", "POST"])
def add_lemma():
    """Add a new lemma."""
    from flask import current_app
    from wordfreq.storage.utils.enums import VALID_POS_TYPES, get_subtype_values_for_pos
    import json

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
        from wordfreq.storage.utils.guid import generate_guid

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
            from wordfreq.storage.translation_helpers import set_translation

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
def list_lemmas():
    """List all lemmas with pagination and filtering."""
    from wordfreq.storage.models.schema import LemmaTranslation

    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "").strip()
    pos_type = request.args.get("pos_type", "").strip()
    difficulty = request.args.get("difficulty", "", type=str).strip()

    # Build query
    query = g.db.query(Lemma)

    # Apply filters
    if search:
        # Search in lemma text, definition, disambiguation, and ALL translations
        search_conditions = [
            Lemma.lemma_text.ilike(f"%{search}%"),
            Lemma.definition_text.ilike(f"%{search}%"),
            Lemma.disambiguation.ilike(f"%{search}%"),
            # Search in legacy translation columns
            Lemma.chinese_translation.ilike(f"%{search}%"),
            Lemma.french_translation.ilike(f"%{search}%"),
            Lemma.korean_translation.ilike(f"%{search}%"),
            Lemma.swahili_translation.ilike(f"%{search}%"),
            Lemma.lithuanian_translation.ilike(f"%{search}%"),
            Lemma.vietnamese_translation.ilike(f"%{search}%"),
        ]

        # Also search in LemmaTranslation table
        # Join with LemmaTranslation and search those translations too
        translation_subquery = g.db.query(LemmaTranslation.lemma_id).filter(
            LemmaTranslation.translation.ilike(f"%{search}%")
        )

        search_conditions.append(Lemma.id.in_(translation_subquery))

        query = query.filter(or_(*search_conditions))

    if pos_type:
        query = query.filter(Lemma.pos_type == pos_type)

    if difficulty:
        if difficulty == "-1":
            query = query.filter(Lemma.difficulty_level == -1)
        elif difficulty == "null":
            query = query.filter(Lemma.difficulty_level.is_(None))
        else:
            query = query.filter(Lemma.difficulty_level == int(difficulty))

    # Order by relevance: exact matches first, then starts-with, then contains
    # Use CASE expressions to create a relevance score
    if search:
        search_lower = search.lower()
        relevance = case(
            (func.lower(Lemma.lemma_text) == search_lower, 1),  # Exact match in lemma
            (func.lower(Lemma.lemma_text).startswith(search_lower), 2),  # Starts with in lemma
            (func.lower(Lemma.lemma_text).contains(search_lower), 3),  # Contains in lemma
            (func.lower(Lemma.definition_text).contains(search_lower), 4),  # Contains in definition
            (
                func.lower(Lemma.disambiguation).contains(search_lower),
                5,
            ),  # Contains in disambiguation
            # Translation matches
            (func.lower(Lemma.lithuanian_translation).contains(search_lower), 6),
            (func.lower(Lemma.chinese_translation).contains(search_lower), 6),
            (func.lower(Lemma.french_translation).contains(search_lower), 6),
            (func.lower(Lemma.korean_translation).contains(search_lower), 6),
            (func.lower(Lemma.swahili_translation).contains(search_lower), 6),
            (func.lower(Lemma.vietnamese_translation).contains(search_lower), 6),
            else_=7,
        )
        query = query.order_by(relevance, func.lower(Lemma.lemma_text))
    else:
        # No search: order by difficulty level first, then case-insensitive alphabetically
        # Put NULL levels at the end, then -1 (not applicable), then levels 1-9
        level_order = case(
            (Lemma.difficulty_level.is_(None), 99),  # NULL levels last
            (Lemma.difficulty_level == -1, 98),  # -1 (not applicable) second to last
            else_=Lemma.difficulty_level,
        )
        query = query.order_by(level_order, func.lower(Lemma.lemma_text))

    # Paginate
    total = query.count()
    lemmas = query.limit(Config.ITEMS_PER_PAGE).offset((page - 1) * Config.ITEMS_PER_PAGE).all()

    # Get unique POS types for filter dropdown
    pos_types = g.db.query(Lemma.pos_type).distinct().order_by(Lemma.pos_type).all()
    pos_types = [p[0] for p in pos_types if p[0]]

    # Calculate pagination
    total_pages = (total + Config.ITEMS_PER_PAGE - 1) // Config.ITEMS_PER_PAGE

    return render_template(
        "lemmas/list.html",
        lemmas=lemmas,
        page=page,
        total_pages=total_pages,
        total=total,
        search=search,
        pos_type=pos_type,
        difficulty=difficulty,
        pos_types=pos_types,
    )


@bp.route("/<int:lemma_id>")
def view_lemma(lemma_id):
    """View a single lemma with all details."""
    from wordfreq.storage.models.schema import DerivativeForm, SentenceWord

    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    # Get all translations
    translations = get_all_translations(g.db, lemma)
    language_names = get_supported_languages()

    # Get difficulty overrides
    overrides = get_all_overrides_for_lemma(g.db, lemma_id)

    # Calculate effective levels for each language
    effective_levels = {}
    for lang_code in language_names.keys():
        effective_levels[lang_code] = get_effective_difficulty_level(g.db, lemma, lang_code)

    # Get difficulty level distribution for same POS type/subtype
    difficulty_stats = _get_difficulty_stats(g.db, lemma.pos_type, lemma.pos_subtype)

    # Get derivative forms grouped by language
    derivative_forms = (
        g.db.query(DerivativeForm)
        .filter(DerivativeForm.lemma_id == lemma_id)
        .order_by(
            DerivativeForm.language_code,
            DerivativeForm.is_base_form.desc(),
            DerivativeForm.grammatical_form,
        )
        .all()
    )

    # Group forms by language and type
    forms_by_language = {}
    synonyms_by_language = {}
    alternative_forms_by_language = {}

    for form in derivative_forms:
        lang_code = form.language_code

        # Separate synonyms and alternative forms
        # Alternative forms include: abbreviation, expanded_form, alternate_spelling, and legacy 'alternative_form'
        is_alternative = form.grammatical_form in [
            "abbreviation",
            "expanded_form",
            "alternate_spelling",
            "alternative_form",
        ]
        is_synonym = form.grammatical_form == "synonym"

        if is_synonym:
            if lang_code not in synonyms_by_language:
                synonyms_by_language[lang_code] = []
            synonyms_by_language[lang_code].append(form)
        elif is_alternative:
            if lang_code not in alternative_forms_by_language:
                alternative_forms_by_language[lang_code] = []
            alternative_forms_by_language[lang_code].append(form)
        else:
            # Regular grammatical forms (conjugations, declensions, etc.)
            if lang_code not in forms_by_language:
                forms_by_language[lang_code] = []
            forms_by_language[lang_code].append(form)

    # Get all languages that have synonyms or alternatives
    all_synonym_languages = sorted(
        set(list(synonyms_by_language.keys()) + list(alternative_forms_by_language.keys()))
    )

    # Get count of sentences using this lemma (for nouns)
    sentence_count = 0
    if lemma.pos_type == "noun":
        sentence_count = g.db.query(SentenceWord).filter(SentenceWord.lemma_id == lemma_id).count()

    # Check if disambiguation check button should be shown
    # Show if: (1) no parenthetical in current lemma_text AND (2) other lemmas exist with same base text
    needs_disambiguation_check = False
    if lemma.lemma_text and "(" not in lemma.lemma_text:
        # Quick check: are there other lemmas with this exact lemma_text?
        duplicate_count = (
            g.db.query(Lemma)
            .filter(
                Lemma.lemma_text == lemma.lemma_text, Lemma.guid.isnot(None), Lemma.id != lemma_id
            )
            .count()
        )
        needs_disambiguation_check = duplicate_count > 0

    # Get grammar facts for this lemma
    from wordfreq.storage.crud.grammar_fact import get_grammar_facts

    grammar_facts = get_grammar_facts(g.db, lemma_id)

    # Get audio files for this lemma
    from wordfreq.storage.models.schema import AudioQualityReview

    audio_files = (
        g.db.query(AudioQualityReview)
        .filter(AudioQualityReview.lemma_id == lemma_id)
        .order_by(AudioQualityReview.language_code, AudioQualityReview.voice_name)
        .all()
    )

    # Get tombstone entries for this lemma
    from wordfreq.storage.crud.guid_tombstone import get_tombstones_by_lemma_id

    tombstones = get_tombstones_by_lemma_id(g.db, lemma_id)

    return render_template(
        "lemmas/view.html",
        lemma=lemma,
        translations=translations,
        language_names=language_names,
        overrides=overrides,
        effective_levels=effective_levels,
        difficulty_stats=difficulty_stats,
        forms_by_language=forms_by_language,
        audio_files=audio_files,
        synonyms_by_language=synonyms_by_language,
        alternative_forms_by_language=alternative_forms_by_language,
        all_synonym_languages=all_synonym_languages,
        sentence_count=sentence_count,
        needs_disambiguation_check=needs_disambiguation_check,
        grammar_facts=grammar_facts,
        tombstones=tombstones,
    )


@bp.route("/<int:lemma_id>/edit", methods=["GET", "POST"])
def edit_lemma(lemma_id):
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
        changes = []

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
                    ("pos_subtype", lemma.pos_subtype if not subtype_changed else None, new_pos_subtype)
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
    difficulty_stats = _get_difficulty_stats(g.db, lemma.pos_type, lemma.pos_subtype)

    # Get POS types and subtypes for dropdowns
    from wordfreq.storage.utils.enums import VALID_POS_TYPES, get_subtype_values_for_pos
    import json

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


def _get_difficulty_stats(session, pos_type, pos_subtype):
    """Get difficulty level distribution for a given POS type/subtype."""
    query = session.query(Lemma.difficulty_level, func.count(Lemma.id)).filter(
        Lemma.pos_type == pos_type, Lemma.difficulty_level.isnot(None)
    )

    if pos_subtype:
        query = query.filter(Lemma.pos_subtype == pos_subtype)

    query = query.group_by(Lemma.difficulty_level).order_by(Lemma.difficulty_level)

    results = query.all()

    # Format as a dictionary
    stats = {}
    for level, count in results:
        stats[level] = count

    return stats


@bp.route("/<int:lemma_id>/delete-synonym/<int:form_id>", methods=["POST"])
def delete_synonym(lemma_id, form_id):
    """Delete a single synonym or alternative form."""
    from flask import current_app
    from wordfreq.storage.crud.grammar_fact import update_alternate_forms_facts_after_deletion

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
def delete_all_synonyms(lemma_id):
    """Delete all synonyms and/or alternative forms for a lemma."""
    from flask import current_app
    from wordfreq.storage.crud.grammar_fact import update_alternate_forms_facts_after_deletion

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
        query = query.filter(DerivativeForm.grammatical_form == "synonym")
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
            from wordfreq.storage.translation_helpers import get_supported_languages

            language_names = get_supported_languages()
            msg += f" for {language_names.get(lang_code, lang_code)}"
        flash(msg, "success")
    else:
        flash("Failed to delete forms", "error")

    return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))
