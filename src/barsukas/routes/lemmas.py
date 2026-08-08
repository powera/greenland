#!/usr/bin/python3

"""Routes for lemma management."""

from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import func

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
from barsukas.helpers.elements import group_language_values
from barsukas.helpers.lemma_display import (
    build_lemma_pronunciation_rows,
    get_pronunciation_languages,
    get_difficulty_stats,
    group_derivative_forms,
    group_populated_pronunciations,
    group_variant_forms,
)
from workqueue.task_queue import get_tasks_for_target
from storage.crud.derivative_form import delete_derivative_form
from storage.crud.difficulty_override import get_all_overrides_for_lemma
from storage.crud.lemma import handle_lemma_type_subtype_change
from storage.crud.lemma_tags import parse_tags_input, serialize_tags_for_column
from storage.crud.operation_log import log_translation_change
from storage.models.schema import (
    SYNONYM_GRAMMATICAL_FORMS,
    DerivativeForm,
    Lemma,
    LemmaTranslation,
)
from storage.models.variant_form import VARIANT_KIND_SPELLING, VariantForm
from storage.queries.lemma import build_lemma_search_query
from storage.translation_helpers import (
    DEFAULT_GENERATION_LANGUAGES,
    get_supported_languages,
)

bp = Blueprint("lemmas", __name__, url_prefix="/lemmas")


# Synthetic ranks each tier source contributes to the combined frequency rank,
# keyed by source name -> {tier_name: rank}. Imported from the combined-rank
# module so the lemma view shows the exact value used in the harmonic mean.
def _tier_ranks_by_source() -> Dict[str, Dict[str, int]]:
    from wordfreq.frequency.combined_rank import (
        BASIC_ENGLISH_TIER_RANKS,
        CEFR_TIER_RANKS,
        YLE_TIER_RANKS,
    )

    return {
        "cambridge_yle": YLE_TIER_RANKS,
        "cefr": CEFR_TIER_RANKS,
        "basic_english": BASIC_ENGLISH_TIER_RANKS,
    }


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


def _get_lemma_page_context(lemma_id: int) -> Optional[Dict[str, Any]]:
    """Build the template context shared by all lemma subpages.

    Returns None when the lemma does not exist. The context includes the
    grouped derivative-form data plus the per-tab counts used by the lemma
    sub-navigation, so every subpage can render the same nav.
    """
    from barsukas.helpers.db_optimization import get_lemma_view_data

    data = get_lemma_view_data(g.db, lemma_id)
    lemma = data["lemma"]
    if not lemma:
        return None

    translations = data["translations"]
    language_names = get_supported_languages()
    derivative_forms = data["derivative_forms"]

    (
        forms_by_language,
        synonyms_by_language,
        alternative_forms_by_language,
        all_synonym_languages,
    ) = group_derivative_forms(derivative_forms)
    variants_by_language, all_variant_languages = group_variant_forms(data["variant_forms"])
    pronunciation_forms_by_language = group_populated_pronunciations(derivative_forms)
    lemma_pronunciation_rows = build_lemma_pronunciation_rows(
        derivative_forms,
        translations,
        data["translation_pronunciations"],
    )

    forms_total = sum(len(forms) for forms in forms_by_language.values())
    # Variants count once per paradigm rather than once per row: "grey" is one
    # entry in the UI even though it is three rows.
    variants_total = sum(len(variants) for variants in variants_by_language.values())
    related_total = (
        sum(len(forms) for forms in synonyms_by_language.values())
        + sum(len(forms) for forms in alternative_forms_by_language.values())
        + variants_total
        + len(data["related_lemmas"])
    )

    return {
        "lemma": lemma,
        "translations": translations,
        # The flat dicts above still drive the edit forms and the slash check,
        # which ask about absent keys; the grouped values feed the shared
        # elements/_language_values.html table.
        "values_by_language": group_language_values(lemma.language_values),
        "definitions": data["definitions"],
        "translation_disambiguations": data["translation_disambiguations"],
        "language_names": language_names,
        "overrides": data["overrides"],
        "effective_levels": data["effective_levels"],
        "derivative_forms": derivative_forms,
        "forms_by_language": forms_by_language,
        "synonyms_by_language": synonyms_by_language,
        "alternative_forms_by_language": alternative_forms_by_language,
        "all_synonym_languages": all_synonym_languages,
        "variants_by_language": variants_by_language,
        "all_variant_languages": all_variant_languages,
        "pronunciation_forms_by_language": pronunciation_forms_by_language,
        "lemma_pronunciation_rows": lemma_pronunciation_rows,
        "grammar_facts": data["grammar_facts"],
        "audio_files": data["audio_files"],
        "sentence_count": data["sentence_count"],
        "needs_disambiguation_check": data["needs_disambiguation_check"],
        "related_lemmas": data["related_lemmas"],
        "hidden_languages": set(language_names) - set(DEFAULT_GENERATION_LANGUAGES),
        # Per-tab counts for the lemma sub-navigation
        "nav_counts": {
            "forms": forms_total + len(data["grammar_facts"]),
            "audio": len(data["audio_files"]),
            "related": related_total,
            "levels": len(data["overrides"]),
        },
    }


@bp.route("/<int:lemma_id>")
def view_lemma(lemma_id: int) -> ResponseReturnValue:
    """Lemma overview: details, translations, and per-language coverage summary."""
    from barsukas.helpers.lemma_display import build_language_coverage_rows
    from storage.crud.concept import get_link_for_lemma

    context = _get_lemma_page_context(lemma_id)
    if context is None:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    # Paired concept (one-to-one, by Q-id). The link lives in the lemma/main DB,
    # so it is available here even when concepts are hosted in a separate,
    # read-only database. Only surfaced when the lemma is actually paired.
    concept_link = get_link_for_lemma(g.db, lemma_id)

    coverage_rows = build_language_coverage_rows(
        language_names=context["language_names"],
        translations=context["translations"],
        forms_by_language=context["forms_by_language"],
        pronunciation_forms_by_language=context["pronunciation_forms_by_language"],
        lemma_pronunciation_rows=context["lemma_pronunciation_rows"],
        audio_files=context["audio_files"],
        default_languages=DEFAULT_GENERATION_LANGUAGES,
    )

    queued_tasks = get_tasks_for_target(g.db, "lemma", lemma_id, limit=8)

    return render_template(
        "lemmas/view.html",
        active_tab="overview",
        concept_link=concept_link,
        coverage_rows=coverage_rows,
        queued_tasks=queued_tasks,
        **context,
    )


@bp.route("/<int:lemma_id>/translations/edit")
def edit_lemma_translations(lemma_id: int) -> ResponseReturnValue:
    """Edit every translation for a lemma on one page.

    The overview table previously carried a modal and an AI button per row,
    which meant its read-only presentation could not be shared with the other
    element types. Collecting the writes here keeps the overview a pure read
    view and gives each language a full-width form instead of a modal.
    """
    context = _get_lemma_page_context(lemma_id)
    if context is None:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    return render_template(
        "lemmas/translations_edit.html",
        active_tab="overview",
        **context,
    )


@bp.route("/<int:lemma_id>/forms")
def view_lemma_forms(lemma_id: int) -> ResponseReturnValue:
    """Grammatical forms, pronunciations, and grammar facts for a lemma."""
    from storage.config.grammar_fact_registry import get_generatable_fact_definitions

    context = _get_lemma_page_context(lemma_id)
    if context is None:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    pronunciation_languages = get_pronunciation_languages(
        context["derivative_forms"], context["translations"]
    )
    generatable_grammar_fact_defs = [
        {
            "fact_type": definition.fact_type,
            "languages": list(definition.languages),
            "display_label": definition.display_label,
            "description": definition.description,
        }
        for definition in get_generatable_fact_definitions().values()
        if context["lemma"].pos_type in definition.required_pos
    ]

    return render_template(
        "lemmas/forms.html",
        active_tab="forms",
        pronunciation_languages=pronunciation_languages,
        generatable_grammar_fact_defs=generatable_grammar_fact_defs,
        **context,
    )


@bp.route("/<int:lemma_id>/audio")
def view_lemma_audio(lemma_id: int) -> ResponseReturnValue:
    """Audio files and audio generation for a lemma."""
    context = _get_lemma_page_context(lemma_id)
    if context is None:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    return render_template(
        "lemmas/audio.html",
        active_tab="audio",
        **_build_voice_options(context["language_names"]),
        **context,
    )


@bp.route("/<int:lemma_id>/related")
def view_lemma_related(lemma_id: int) -> ResponseReturnValue:
    """Synonyms, alternative forms, related lemmas, and example sentences."""
    context = _get_lemma_page_context(lemma_id)
    if context is None:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    return render_template(
        "lemmas/related.html",
        active_tab="related",
        **context,
    )


@bp.route("/<int:lemma_id>/levels")
def view_lemma_levels(lemma_id: int) -> ResponseReturnValue:
    """Frequency/tier signals and per-language difficulty overrides for a lemma."""
    from storage.lexeme import get_lexeme
    from storage.models.schema import (
        ExternalLexemeAnnotation,
        LemmaTier,
        TierDefinition,
    )
    from wordfreq.frequency.corpus import get_enabled_corpus_configs
    from wordfreq.lexeme_frequency import get_lexeme_frequencies_all_corpora

    context = _get_lemma_page_context(lemma_id)
    if context is None:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    lemma = context["lemma"]

    # Get difficulty level distribution for same POS type/subtype
    difficulty_stats = get_difficulty_stats(g.db, lemma.pos_type, lemma.pos_subtype)

    lemma_tiers = (
        g.db.query(LemmaTier)
        .filter(LemmaTier.lemma_id == lemma_id)
        .order_by(LemmaTier.source, LemmaTier.tier_name)
        .all()
    )

    tier_sources: set[str] = {tier.source for tier in lemma_tiers}
    tier_definitions = (
        g.db.query(TierDefinition).filter(TierDefinition.source.in_(tier_sources)).all()
        if tier_sources
        else []
    )
    tier_display_by_source_name: Dict[Tuple[str, str], str] = {
        (row.source, row.tier_name): (row.display_name or row.tier_name) for row in tier_definitions
    }
    tier_ordinal_by_source_name: Dict[Tuple[str, str], int] = {
        (row.source, row.tier_name): row.ordinal for row in tier_definitions
    }
    tier_size_by_source: Dict[str, int] = {}
    for row in tier_definitions:
        tier_size_by_source[row.source] = tier_size_by_source.get(row.source, 0) + 1

    # The synthetic rank each tier assignment contributes to the combined
    # frequency rank (lower = more common), surfaced so the view explains the
    # number rather than just the tier label.
    ranks_by_source = _tier_ranks_by_source()
    tier_rank_by_source_name: Dict[Tuple[str, str], Optional[int]] = {
        (tier.source, tier.tier_name): ranks_by_source[tier.source].get(tier.tier_name)
        for tier in lemma_tiers
        if tier.source in ranks_by_source
    }

    target_corpora = ["19th_books", "20th_books", "cooking", "wiki_vital"]
    enabled_corpora = {cfg.name for cfg in get_enabled_corpus_configs()}
    lexeme_frequency_by_corpus = {}
    lexeme_rank_by_corpus: Dict[str, Optional[int]] = {}
    english_lexeme = get_lexeme(g.db, lemma_id, "en")
    if english_lexeme:
        all_rollups = get_lexeme_frequencies_all_corpora(g.db, english_lexeme)
        form_token_ids = [
            form.word_token_id for form in english_lexeme.forms if form.word_token_id is not None
        ]
        for corpus_name in target_corpora:
            if corpus_name not in enabled_corpora:
                continue
            lexeme_frequency_by_corpus[corpus_name] = all_rollups.get(corpus_name)
            best_rank: Optional[int] = None
            if form_token_ids:
                source_name = f"wordfreq_{corpus_name}"
                rank_row = (
                    g.db.query(func.min(ExternalLexemeAnnotation.ordinal_rank))
                    .filter(
                        ExternalLexemeAnnotation.word_token_id.in_(form_token_ids),
                        ExternalLexemeAnnotation.source == source_name,
                        ExternalLexemeAnnotation.ordinal_rank.isnot(None),
                    )
                    .scalar()
                )
                best_rank = int(rank_row) if rank_row is not None else None
            lexeme_rank_by_corpus[corpus_name] = best_rank

    return render_template(
        "lemmas/levels.html",
        active_tab="levels",
        difficulty_stats=difficulty_stats,
        lemma_tiers=lemma_tiers,
        tier_display_by_source_name=tier_display_by_source_name,
        tier_ordinal_by_source_name=tier_ordinal_by_source_name,
        tier_size_by_source=tier_size_by_source,
        tier_rank_by_source_name=tier_rank_by_source_name,
        lexeme_frequency_by_corpus=lexeme_frequency_by_corpus,
        lexeme_rank_by_corpus=lexeme_rank_by_corpus,
        **context,
    )


def _build_voice_options(language_names: Dict[str, str]) -> Dict[str, Any]:
    """Build the per-engine voice option lists used by the audio generation modal."""
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

    espeak_voices: Dict[str, List[Dict[str, Any]]] = {}
    piper_voices: Dict[str, List[Dict[str, Any]]] = {}
    coqui_voices: Dict[str, List[Dict[str, Any]]] = {}
    qwen3_voices: Dict[str, List[Dict[str, Any]]] = {}
    polly_voices: Dict[str, List[Dict[str, Any]]] = {}
    azure_voices: Dict[str, List[Dict[str, Any]]] = {}
    google_voices: Dict[str, List[Dict[str, Any]]] = {}
    for lang_code in language_names.keys():
        espeak_voices[lang_code] = [
            {"name": v.name, "gender": v.gender}
            for v in EspeakVoice.get_voices_for_language(lang_code)
        ]
        piper_voices[lang_code] = [
            {"name": v.name, "ui_name": v.ui_name, "gender": v.gender}
            for v in PiperVoice.get_voices_for_language(lang_code)
        ]
        coqui_voices[lang_code] = [
            {"name": v.name, "ui_name": v.ui_name, "gender": v.gender}
            for v in CoquiVoice.get_voices_for_language(lang_code)
        ]
        qwen3_voices[lang_code] = [
            {"name": v.name, "ui_name": v.ui_name, "gender": v.gender}
            for v in QwenVoice.get_voices_for_language(lang_code)
        ]
        polly_voices[lang_code] = [
            {"name": v.name, "ui_name": v.ui_name, "gender": v.gender}
            for v in PollyVoice.get_voices_for_language(lang_code)
        ]
        azure_voices[lang_code] = [
            {"name": v.name, "ui_name": v.ui_name, "gender": v.gender}
            for v in AzureVoice.get_voices_for_language(lang_code)
        ]
        google_voices[lang_code] = [
            {"name": v.name, "ui_name": v.ui_name, "gender": v.gender}
            for v in GoogleTtsVoice.get_voices_for_language(lang_code)
        ]

    return {
        "openai_voices": openai_voices,
        "espeak_voices": espeak_voices,
        "piper_voices": piper_voices,
        "coqui_voices": coqui_voices,
        "qwen3_voices": qwen3_voices,
        "polly_voices": polly_voices,
        "azure_voices": azure_voices,
        "google_voices": google_voices,
    }


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

        # The field accepts either a JSON array or a comma-separated list; both
        # are normalized to the JSON array that Lemma.tags is defined to hold.
        # Storing the raw input here would write a bare string that read_tags()
        # then has to treat as one legacy tag.
        raw_tags = request.form.get("tags", "").strip()
        try:
            parsed_tags = parse_tags_input(raw_tags)
        except ValueError as tag_error:
            flash(f"Invalid tags: {tag_error}", "error")
            return render_template("lemmas/edit.html", lemma=lemma)

        new_tags = serialize_tags_for_column(parsed_tags)
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
        return redirect(url_for("lemmas.view_lemma_related", lemma_id=lemma_id))

    # Verify the form belongs to this lemma
    form = (
        g.db.query(DerivativeForm)
        .filter(DerivativeForm.id == form_id, DerivativeForm.lemma_id == lemma_id)
        .first()
    )

    if not form:
        flash("Synonym or alternative form not found", "error")
        return redirect(url_for("lemmas.view_lemma_related", lemma_id=lemma_id))

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

    return redirect(url_for("lemmas.view_lemma_related", lemma_id=lemma_id))


@bp.route("/<int:lemma_id>/delete-all-synonyms", methods=["POST"])
def delete_all_synonyms(lemma_id: int) -> ResponseReturnValue:
    """Delete all synonyms and/or alternative forms for a lemma."""
    from flask import current_app

    from storage.crud.grammar_fact import update_alternate_forms_facts_after_deletion

    if current_app.config.get("READONLY", False):
        flash("Cannot delete: running in read-only mode", "error")
        return redirect(url_for("lemmas.view_lemma_related", lemma_id=lemma_id))

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
        query = query.filter(DerivativeForm.grammatical_form.in_(tuple(SYNONYM_GRAMMATICAL_FORMS)))
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
        return redirect(url_for("lemmas.view_lemma_related", lemma_id=lemma_id))

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

    return redirect(url_for("lemmas.view_lemma_related", lemma_id=lemma_id))


@bp.route("/<int:lemma_id>/add-variant", methods=["POST"])
def add_variant(lemma_id: int) -> ResponseReturnValue:
    """Add a spelling variant, expanding it into a paradigm where possible."""
    from flask import current_app

    from words.synonyms import store_spelling_variants

    if current_app.config.get("READONLY", False):
        flash("Cannot add variant: running in read-only mode", "error")
        return redirect(url_for("lemmas.view_lemma_related", lemma_id=lemma_id))

    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    variant_text = request.form.get("variant_text", "").strip()
    lang_code = request.form.get("lang_code", "").strip()
    variant_kind = request.form.get("variant_kind", "").strip() or VARIANT_KIND_SPELLING

    if not variant_text:
        flash("Variant spelling is required", "error")
        return redirect(url_for("lemmas.view_lemma_related", lemma_id=lemma_id))
    if not lang_code:
        flash("Language is required", "error")
        return redirect(url_for("lemmas.view_lemma_related", lemma_id=lemma_id))

    stored = store_spelling_variants(
        session=g.db,
        lemma=lemma,
        language_code=lang_code,
        alternate_spellings=[variant_text],
        variant_kind=variant_kind,
    )

    if not stored:
        flash(f'Failed to add variant "{variant_text}"', "error")
        return redirect(url_for("lemmas.view_lemma_related", lemma_id=lemma_id))

    log_translation_change(
        session=g.db,
        source=Config.OPERATION_LOG_SOURCE,
        operation_type="variant_form_add",
        lemma_id=lemma_id,
        field_name=f"{lang_code}_{variant_kind}",
        old_value=None,
        new_value=variant_text,
    )
    g.db.commit()

    flash(f'Added variant "{variant_text}"', "success")
    return redirect(url_for("lemmas.view_lemma_related", lemma_id=lemma_id))


@bp.route("/<int:lemma_id>/delete-variant-form/<int:form_id>", methods=["POST"])
def delete_variant_form(lemma_id: int, form_id: int) -> ResponseReturnValue:
    """Delete a single form of a variant paradigm."""
    from flask import current_app

    if current_app.config.get("READONLY", False):
        flash("Cannot delete: running in read-only mode", "error")
        return redirect(url_for("lemmas.view_lemma_related", lemma_id=lemma_id))

    form = (
        g.db.query(VariantForm)
        .filter(VariantForm.id == form_id, VariantForm.lemma_id == lemma_id)
        .first()
    )
    if not form:
        flash("Variant form not found", "error")
        return redirect(url_for("lemmas.view_lemma_related", lemma_id=lemma_id))

    form_text = form.variant_form_text
    language_code = form.language_code
    grammatical_form = form.grammatical_form

    g.db.delete(form)
    log_translation_change(
        session=g.db,
        source=Config.OPERATION_LOG_SOURCE,
        operation_type="variant_form_delete",
        lemma_id=lemma_id,
        field_name=f"{language_code}_{grammatical_form}",
        old_value=form_text,
        new_value=None,
    )
    g.db.commit()

    flash(f'Deleted variant form: "{form_text}"', "success")
    return redirect(url_for("lemmas.view_lemma_related", lemma_id=lemma_id))


@bp.route("/<int:lemma_id>/delete-variant", methods=["POST"])
def delete_variant_paradigm(lemma_id: int) -> ResponseReturnValue:
    """Delete an entire variant paradigm (all forms of one spelling)."""
    from flask import current_app

    from storage.crud.variant_form import delete_variant

    if current_app.config.get("READONLY", False):
        flash("Cannot delete: running in read-only mode", "error")
        return redirect(url_for("lemmas.view_lemma_related", lemma_id=lemma_id))

    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    variant_key = request.form.get("variant_key", "").strip()
    lang_code = request.form.get("lang_code", "").strip()
    variant_kind = request.form.get("variant_kind", "").strip() or VARIANT_KIND_SPELLING

    if not variant_key or not lang_code:
        flash("Variant key and language are required", "error")
        return redirect(url_for("lemmas.view_lemma_related", lemma_id=lemma_id))

    deleted_count = delete_variant(
        session=g.db,
        lemma=lemma,
        variant_key=variant_key,
        language_code=lang_code,
        variant_kind=variant_kind,
    )

    if deleted_count:
        log_translation_change(
            session=g.db,
            source=Config.OPERATION_LOG_SOURCE,
            operation_type="variant_delete",
            lemma_id=lemma_id,
            field_name=f"{lang_code}_{variant_kind}",
            old_value=variant_key,
            new_value=None,
        )
        g.db.commit()
        flash(f'Deleted variant "{variant_key}" ({deleted_count} form(s))', "success")
    else:
        flash(f'Variant "{variant_key}" not found', "error")

    return redirect(url_for("lemmas.view_lemma_related", lemma_id=lemma_id))
