#!/usr/bin/python3

"""Routes for agent operations (voras, vilkas, etc)."""

import logging
import traceback
from typing import Optional

from barsukas.config import Config
from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

import constants
from agents.lokys import LokysAgent
from agents.papuga import PapugaAgent
from agents.voras.agent import VorasAgent
from barsukas.helpers.flash_helpers import flash_and_log, log_and_flash_error
from workqueue.task_queue import TaskType, enqueue_task
from storage.backend.config import BackendType, DataSourceConfig
from storage.models.schema import DerivativeForm, Lemma
from storage.translation_helpers import get_supported_languages

bp = Blueprint("agents", __name__, url_prefix="/agents")
logger = logging.getLogger(__name__)


@bp.route("/check-translations/<int:lemma_id>", methods=["POST"])
def check_translations(lemma_id: int) -> ResponseReturnValue:
    """Check translations for a lemma using the voras agent."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    # Get language code from form (optional - if not provided, check all)
    lang_code = request.form.get("lang_code")

    try:
        # Initialize voras agent
        config = DataSourceConfig(
            backend_type=BackendType.SQLITE,
            sqlite_path=Config.DB_PATH,
            model=constants.DEFAULT_MODEL,
            debug=Config.DEBUG,
        )
        agent = VorasAgent(config=config)

        # Gather translations for this word
        from storage.translation_helpers import LANGUAGE_FIELDS

        translations = {}
        for lc in LANGUAGE_FIELDS.keys():
            translation = agent.get_translation(g.db, lemma, lc)
            if translation and translation.strip():
                translations[lc] = translation

        if not translations:
            flash("No translations found to check", "warning")
            return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

        # Use the LLM validator to check all translations at once
        from wordfreq.tools.llm_validators import validate_all_translations_for_word

        validation_results = validate_all_translations_for_word(
            lemma.lemma_text, translations, lemma.pos_type, agent.config.model
        )

        # Format results for display
        issues = []
        all_good = True
        for lc, result in validation_results.items():
            has_issues = not result["is_correct"] or not result["is_lemma_form"]
            if has_issues and result["confidence"] >= 0.7:
                all_good = False
                issues.append(
                    {
                        "language_code": lc,
                        "language_name": get_supported_languages()[lc],
                        "current": translations[lc],
                        "suggested": result["suggested_translation"],
                        "is_correct": result["is_correct"],
                        "is_lemma_form": result["is_lemma_form"],
                        "issues": result["issues"],
                        "confidence": result["confidence"],
                    }
                )

        if all_good:
            flash("All translations look good!", "success")
        else:
            # Store issues in session or pass as query param
            # For now, we'll flash a summary
            flash(f"Found {len(issues)} translation issues. Check the results below.", "warning")
            # Redirect to a results page or back to lemma view with issues
            return render_template(
                "agents/translation_check_results.html",
                lemma=lemma,
                issues=issues,
                all_good=all_good,
            )

    except Exception as e:
        log_and_flash_error(e, "checking translations")

    return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))


@bp.route("/add-missing-translations/<int:lemma_id>", methods=["POST"])
def add_missing_translations(lemma_id: int) -> ResponseReturnValue:
    """Add missing translations for a lemma using the voras agent."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    try:
        result = enqueue_task(
            g.db,
            task_type=TaskType.ADD_MISSING_TRANSLATIONS,
            target_type="lemma",
            target_id=lemma_id,
            payload={
                "schema_version": 1,
                "lemma_id": lemma_id,
                "source_component": "barsukas",
            },
            dedup_key=f"{TaskType.ADD_MISSING_TRANSLATIONS}:{lemma_id}",
        )
        if result.created:
            flash(
                "Queued missing translation generation. Results will be applied soon.",
                "info",
            )
        else:
            flash("Translation generation already in progress for this lemma.", "warning")
    except Exception as e:
        log_and_flash_error(e, "adding missing translations")

    return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))


@bp.route("/check-pronunciations/<int:lemma_id>", methods=["POST"])
def check_pronunciations(lemma_id: int) -> ResponseReturnValue:
    """Check pronunciations for a lemma's derivative forms using the PAPUGA agent."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    try:
        # Get all derivative forms for this lemma that have pronunciations
        forms_with_pronunciations = (
            g.db.query(DerivativeForm)
            .filter(
                DerivativeForm.lemma_id == lemma_id,
                (
                    (DerivativeForm.ipa_pronunciation.isnot(None))
                    | (DerivativeForm.phonetic_pronunciation.isnot(None))
                ),
            )
            .all()
        )

        if not forms_with_pronunciations:
            flash("No pronunciations found to check", "warning")
            return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

        # Initialize PAPUGA agent
        config = DataSourceConfig(
            backend_type=BackendType.SQLITE,
            sqlite_path=Config.DB_PATH,
            model=constants.DEFAULT_MODEL,
            debug=Config.DEBUG,
        )
        agent = PapugaAgent(config=config)

        # Check pronunciations (using dry_run=False to actually validate)
        from storage.models.schema import Sentence, SentenceTranslation, SentenceWord
        from wordfreq.tools.llm_validators import validate_pronunciation

        issues = []
        for form in forms_with_pronunciations:
            # Get example sentence for context - find sentences that use the lemma
            example_translation = (
                g.db.query(SentenceTranslation)
                .join(Sentence)
                .join(SentenceWord)
                .filter(
                    SentenceWord.lemma_id == lemma_id,
                    SentenceTranslation.language_code == "en",  # Get English version for context
                )
                .first()
            )
            example_text = example_translation.translation_text if example_translation else None

            result = validate_pronunciation(
                word=form.derivative_form_text,
                ipa_pronunciation=form.ipa_pronunciation,
                phonetic_pronunciation=form.phonetic_pronunciation,
                pos_type=lemma.pos_type,
                example_sentence=example_text,
                definition=lemma.definition_text,
                model=constants.DEFAULT_MODEL,
            )

            if result["needs_update"] and result["confidence"] >= 0.7:
                issues.append(
                    {
                        "form_id": form.id,
                        "form_text": form.derivative_form_text,
                        "grammatical_form": form.grammatical_form,
                        "current_ipa": form.ipa_pronunciation,
                        "current_phonetic": form.phonetic_pronunciation,
                        "suggested_ipa": result["suggested_ipa"],
                        "suggested_phonetic": result["suggested_phonetic"],
                        "issues": result["issues"],
                        "confidence": result["confidence"],
                    }
                )

        if not issues:
            flash("All pronunciations look good!", "success")
        else:
            flash(f"Found {len(issues)} pronunciation issues", "warning")
            return render_template(
                "agents/pronunciation_check_results.html", lemma=lemma, issues=issues
            )

    except Exception as e:
        log_and_flash_error(e, "checking pronunciations")

    return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))


@bp.route("/generate-pronunciations/<int:lemma_id>", methods=["POST"])
def generate_pronunciations(lemma_id: int) -> ResponseReturnValue:
    """Generate missing pronunciations for a lemma's derivative forms using the PAPUGA agent."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    # Get language code from form (default to English)
    lang_code = request.form.get("lang_code", "en")

    try:
        result = enqueue_task(
            g.db,
            task_type=TaskType.GENERATE_PRONUNCIATIONS,
            target_type="lemma",
            target_id=lemma_id,
            payload={
                "schema_version": 1,
                "lemma_id": lemma_id,
                "language_code": lang_code,
                "source_component": "barsukas",
            },
            dedup_key=f"{TaskType.GENERATE_PRONUNCIATIONS}:{lemma_id}:{lang_code}",
        )
        if result.created:
            flash(
                f"Queued pronunciation generation for {lang_code}. A worker will process it shortly.",
                "info",
            )
        else:
            flash(
                "Pronunciation generation already in progress for this lemma/language.", "warning"
            )
    except Exception as e:
        log_and_flash_error(e, "generating pronunciations")

    return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))


@bp.route("/generate-forms/<int:lemma_id>", methods=["POST"])
def generate_forms(lemma_id: int) -> ResponseReturnValue:
    """Generate missing grammatical forms for a lemma using the VILKAS agent."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    if not lemma.guid:
        flash_and_log("Lemma is missing a GUID, cannot request form generation", "error")
        return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

    # Get language code and pos_type from form
    lang_code = request.form.get("lang_code", "lt")
    pos_type = lemma.pos_type

    try:
        result = enqueue_task(
            g.db,
            task_type=TaskType.GENERATE_FORMS,
            target_type="lemma",
            target_id=lemma_id,
            payload={
                "schema_version": 1,
                "lemma_id": lemma_id,
                "language_code": lang_code,
                "source_component": "barsukas",
            },
            dedup_key=f"{TaskType.GENERATE_FORMS}:{lemma_id}:{lang_code}",
        )
        if result.created:
            flash(
                f"Queued {lang_code} form generation. A worker will store results soon.",
                "info",
            )
        else:
            flash("Form generation already queued for this lemma/language.", "warning")
    except Exception as e:
        log_and_flash_error(e, "generating forms")

    return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))


@bp.route("/generate-synonyms/<int:lemma_id>", methods=["POST"])
def generate_synonyms(lemma_id: int) -> ResponseReturnValue:
    """Generate synonyms and alternative forms for a lemma using the ŠERNAS agent."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    # Get language code from form
    lang_code = request.form.get("lang_code", "en")

    try:
        result = enqueue_task(
            g.db,
            task_type=TaskType.GENERATE_SYNONYMS,
            target_type="lemma",
            target_id=lemma_id,
            payload={
                "schema_version": 1,
                "lemma_id": lemma_id,
                "language_code": lang_code,
                "source_component": "barsukas",
            },
            dedup_key=f"{TaskType.GENERATE_SYNONYMS}:{lemma_id}:{lang_code}",
        )
        if result.created:
            flash(
                "Queued synonym generation. Check back after the worker finishes writing results.",
                "info",
            )
        else:
            flash("Synonym generation already queued for this lemma/language.", "warning")
    except Exception as e:
        log_and_flash_error(e, "generating synonyms")

    return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))


@bp.route("/check-definition/<int:lemma_id>", methods=["POST"])
def check_definition(lemma_id: int) -> ResponseReturnValue:
    """Check/improve the definition of a lemma using the LOKYS agent."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    try:
        # Initialize LOKYS agent
        config = DataSourceConfig(
            backend_type=BackendType.SQLITE,
            sqlite_path=Config.DB_PATH,
            model=constants.DEFAULT_MODEL,
            debug=Config.DEBUG,
        )
        agent = LokysAgent(config=config)

        # Use the agent's helper method for cleaner code
        result = agent.check_single_definition(lemma, session=g.db)

        if result["is_valid"] and result["confidence"] >= 0.7:
            flash("Definition looks good!", "success")
        else:
            # Show issues and suggested improvement
            return render_template(
                "agents/definition_check_results.html", lemma=lemma, result=result
            )

    except Exception as e:
        log_and_flash_error(e, "checking definition")

    return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))


@bp.route("/apply-definition/<int:lemma_id>", methods=["POST"])
def apply_definition(lemma_id: int) -> ResponseReturnValue:
    """Apply a suggested definition improvement."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    new_definition = request.form.get("new_definition")
    if not new_definition:
        flash("No new definition provided", "error")
        return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

    try:
        old_definition = lemma.definition_text
        lemma.definition_text = new_definition
        g.db.commit()

        # Log the change
        from storage.crud.operation_log import log_operation

        log_operation(
            g.db,
            source="barsukas-web-interface",
            operation_type="definition_update",
            fact={
                "lemma_id": lemma_id,
                "lemma_text": lemma.lemma_text,
                "old_definition": old_definition,
                "new_definition": new_definition,
            },
            lemma_id=lemma_id,
        )

        flash("Definition updated successfully!", "success")
    except Exception as e:
        g.db.rollback()
        log_and_flash_error(e, "updating definition")

    return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))


@bp.route("/check-disambiguation/<int:lemma_id>", methods=["POST"])
def check_disambiguation(lemma_id: int) -> ResponseReturnValue:
    """Check if a lemma needs disambiguation (parentheticals) using the LOKYS agent."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    try:
        # Initialize LOKYS agent
        config = DataSourceConfig(
            backend_type=BackendType.SQLITE,
            sqlite_path=Config.DB_PATH,
            model=constants.DEFAULT_MODEL,
            debug=Config.DEBUG,
        )
        agent = LokysAgent(config=config)

        # Use the agent's helper method for cleaner code
        result = agent.check_single_disambiguation(lemma, session=g.db)

        # Handle different cases based on result
        if not result["needs_disambiguation"]:
            if result["reason"] == "no_duplicates":
                flash(
                    f'No other lemmas found with lemma_text "{lemma.lemma_text}" - disambiguation not needed',
                    "info",
                )
            elif result["reason"] == "translations_identical":
                flash(
                    f'Found {result["duplicate_count"]} lemmas with "{lemma.lemma_text}", but translations are the same - may be duplicates',
                    "warning",
                )
            elif result["reason"] == "already_disambiguated":
                flash(f'This lemma already has disambiguation: "{lemma.lemma_text}"', "success")
            return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

        # Check if already has parentheticals
        if result["has_parenthetical"]:
            flash(f'This lemma already has disambiguation: "{lemma.lemma_text}"', "success")
            return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

        if result.get("reason") == "polysemy_detected":
            suggestion = result.get("llm_suggestions", {}).get("suggested_disambiguation")
            if suggestion:
                flash(
                    f'⚠️ This lemma appears polysemous. Consider "{lemma.lemma_text} ({suggestion})" for this sense.',
                    "warning",
                )
            else:
                flash(
                    f'⚠️ This lemma appears polysemous and may need disambiguation (e.g., "{lemma.lemma_text} (sense)").',
                    "warning",
                )
            return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

        # Show LLM suggestions if available
        llm_result = result["llm_suggestions"]
        if llm_result["success"] and llm_result["suggestions"]:
            return render_template(
                "agents/disambiguation_suggestions.html",
                lemma=lemma,
                duplicates=result["duplicates"],
                suggestions=llm_result["suggestions"],
                lemma_text=lemma.lemma_text,
            )
        else:
            flash(
                f'⚠️ This lemma needs disambiguation! Found {result["duplicate_count"]} different meanings for "{lemma.lemma_text}" with different translations',
                "warning",
            )
            flash(
                f'Consider adding parentheticals like: "{lemma.lemma_text} (animal)", "{lemma.lemma_text} (computer)", etc.',
                "info",
            )

    except Exception as e:
        log_and_flash_error(e, "checking disambiguation")

    return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))


@bp.route("/apply-disambiguation/<int:lemma_id>", methods=["POST"])
def apply_disambiguation(lemma_id: int) -> ResponseReturnValue:
    """Apply an AI-suggested disambiguation to a lemma."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    new_lemma_text = request.form.get("new_lemma_text")
    return_to_suggestions = request.form.get("return_to_suggestions") == "true"
    original_lemma_id = request.form.get("original_lemma_id", type=int)

    if not new_lemma_text:
        flash("No disambiguation provided", "error")
        return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

    try:
        old_lemma_text = lemma.lemma_text
        lemma.lemma_text = new_lemma_text
        g.db.commit()

        # Log the change
        from storage.crud.operation_log import log_translation_change

        log_translation_change(
            g.db,
            source="barsukas-web-interface",
            operation_type="lemma_text_update",
            lemma_id=lemma_id,
            old_lemma_text=old_lemma_text,
            new_lemma_text=new_lemma_text,
            guid=lemma.guid,
            change_source="ai_disambiguation_suggestion",
        )

        flash(f'✓ Updated GUID {lemma.guid}: "{old_lemma_text}" → "{new_lemma_text}"', "success")
    except Exception as e:
        g.db.rollback()
        log_and_flash_error(e, "applying disambiguation")

    # Stay on suggestions page if requested, otherwise go to the updated lemma
    if return_to_suggestions and original_lemma_id:
        # Re-run the check to show updated suggestions page
        return redirect(url_for("agents.check_disambiguation", lemma_id=original_lemma_id))

    return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))


@bp.route("/generate-sentences/<int:lemma_id>", methods=["POST"])
def generate_sentences(lemma_id: int) -> ResponseReturnValue:
    """Generate example sentences for a lemma using the Buivolas agent."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    # Get parameters from form
    num_sentences = int(request.form.get("num_sentences", 3))
    generation_mode = request.form.get("generation_mode", "llm")
    max_vocabulary_level = int(request.form.get("max_vocabulary_level", 7))

    try:
        # Import Buivolas agent for sentence creation
        from sentences.generation import SentenceGenerationService
        from storage.models.schema import Sentence

        # Initialize agent
        config = DataSourceConfig(
            backend_type=BackendType.SQLITE,
            sqlite_path=Config.DB_PATH,
            model=constants.DEFAULT_MODEL,
            debug=Config.DEBUG,
        )
        agent = SentenceGenerationService(config=config)

        # Generate sentences based on mode
        if generation_mode == "guided":
            result = agent.generate_guided_sentences_for_lemma(
                lemma=lemma,
                num_sentences=num_sentences,
                max_vocabulary_level=max_vocabulary_level,
            )
        else:
            # Default to LLM mode
            result = agent.generate_llm_sentences_for_lemma(
                lemma=lemma,
                num_sentences=num_sentences,
                difficulty_context=lemma.difficulty_level,
            )

        if not result.get("success"):
            flash_and_log(
                f'Failed to generate sentences: {result.get("error", "Unknown error")}', "error"
            )
            return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

        # Store the generated sentences
        sentences_data = result.get("sentences", [])
        if not sentences_data:
            flash("No sentences were generated", "warning")
            return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

        # Use the appropriate store method based on mode
        if generation_mode == "guided":
            store_result = agent.store_guided_sentences(
                sentences_data=sentences_data, source_lemma=lemma, session=g.db
            )
        else:
            store_result = agent.store_llm_sentences(
                sentences_data=sentences_data, source_lemma=lemma, session=g.db
            )

        if store_result["stored"] > 0:
            flash(
                f'Successfully generated and stored {store_result["stored"]} sentence(s) using {generation_mode} mode!',
                "success",
            )

            # Get the newly created sentences using the IDs returned from store_sentences
            sentence_ids = store_result.get("sentence_ids", [])
            if sentence_ids:
                sentences = g.db.query(Sentence).filter(Sentence.id.in_(sentence_ids)).all()
            else:
                sentences = []

            # Show the results
            return render_template(
                "agents/sentence_generation_results.html",
                lemma=lemma,
                sentences=sentences,
                generated_count=store_result["stored"],
            )
        else:
            flash_and_log("Failed to store generated sentences", "error")
            if store_result.get("errors"):
                for error in store_result["errors"][:3]:  # Show first 3 errors
                    flash(f"Error: {error}", "error")

    except Exception as e:
        log_and_flash_error(e, "generating sentences")

    return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))


@bp.route("/generate-grammar-fact/<int:lemma_id>", methods=["POST"])
def generate_grammar_fact(lemma_id: int) -> ResponseReturnValue:
    """Generate a grammar fact for a lemma using the LAPE agent (queued via task worker)."""
    from workqueue.handlers.lape import SUPPORTED_FACT_TYPES, validate_grammar_fact_request
    from storage.crud.grammar_fact import get_grammar_fact_value

    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    # Get parameters from form
    fact_type = request.form.get("fact_type", "measure_words")
    language_code = request.form.get("language_code", "zh")

    try:
        # Validate fact type is supported
        if fact_type not in SUPPORTED_FACT_TYPES:
            flash(f"Unsupported fact type: {fact_type}", "error")
            return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

        # Check if fact already exists
        existing_fact = get_grammar_fact_value(g.db, lemma_id, language_code, fact_type)
        if existing_fact:
            flash(f"This lemma already has {fact_type}: {existing_fact}", "info")
            return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

        # Validate request (POS type, language support, translation exists)
        is_valid, error, _ = validate_grammar_fact_request(lemma, fact_type, language_code, g.db)
        if not is_valid:
            flash(error or "Validation failed", "warning")
            return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

        # Enqueue grammar fact generation task
        result = enqueue_task(
            g.db,
            task_type=TaskType.WORDS_GRAMMAR_FACTS,
            target_type="lemma",
            target_id=lemma_id,
            payload={
                "schema_version": 1,
                "lemma_id": lemma_id,
                "fact_type": fact_type,
                "language_code": language_code,
                "source_component": "barsukas",
            },
            dedup_key=f"{TaskType.WORDS_GRAMMAR_FACTS}:{lemma_id}:{language_code}:{fact_type}",
        )

        if result.created:
            flash(
                f"Queued {fact_type} generation for {language_code}. A worker will process it shortly.",
                "info",
            )
        else:
            flash(
                f"Grammar fact generation already in progress for this lemma.",
                "warning",
            )

    except Exception as e:
        g.db.rollback()
        log_and_flash_error(e, "queuing grammar fact generation")

    return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))


@bp.route("/add-grammar-fact/<int:lemma_id>", methods=["POST"])
def add_grammar_fact_manual(lemma_id: int) -> ResponseReturnValue:
    """Add or update a grammar fact manually from the lemma page."""
    from storage.config.grammar_fact_registry import is_release_grammar_fact_type
    from storage.crud.grammar_fact import add_grammar_fact
    from storage.models.grammar_fact import GrammarFact

    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    language_code = (request.form.get("language_code") or "").strip()
    fact_type = (request.form.get("fact_type") or "").strip()
    fact_value = (request.form.get("fact_value") or "").strip()
    notes = (request.form.get("notes") or "").strip() or None

    if not language_code or not fact_type or not fact_value:
        flash("Language, fact type, and value are required", "warning")
        return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

    if fact_type.startswith("verb_form_") and lemma.pos_type != "verb":
        flash("verb_form_* overrides can only be added to verbs", "warning")
        return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

    existing = (
        g.db.query(GrammarFact)
        .filter(
            GrammarFact.lemma_id == lemma_id,
            GrammarFact.language_code == language_code,
            GrammarFact.fact_type == fact_type,
        )
        .first()
    )
    if existing:
        existing.fact_value = fact_value
        existing.notes = notes
        g.db.commit()
        flash(f"Updated grammar fact {language_code}:{fact_type}", "success")
    else:
        result = add_grammar_fact(
            g.db,
            lemma_id=lemma_id,
            language_code=language_code,
            fact_type=fact_type,
            fact_value=fact_value,
            notes=notes,
            verified=False,
        )
        if result:
            flash(f"Added grammar fact {language_code}:{fact_type}", "success")
        else:
            flash("Could not add grammar fact", "error")

    if is_release_grammar_fact_type(language_code, fact_type):
        flash("This grammar fact is eligible for release sync.", "info")

    return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))


@bp.route("/view-sentences/<int:lemma_id>")
def view_sentences(lemma_id: int) -> ResponseReturnValue:
    """View all sentences that use a specific lemma."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    try:
        # Query sentences that use this lemma (from either sentence_words or sentence_word_hints)
        from sqlalchemy import or_
        from sqlalchemy.orm import joinedload

        from storage.models.schema import (
            Sentence,
            SentenceWordHint,
            SentenceWord,
        )

        sentences = (
            g.db.query(Sentence)
            .outerjoin(SentenceWord)
            .outerjoin(SentenceWordHint)
            .filter(
                or_(
                    SentenceWord.lemma_id == lemma_id,
                    SentenceWordHint.lemma_id == lemma_id,
                )
            )
            .filter(Sentence.rejected == False)
            .options(
                joinedload(Sentence.translations),
                joinedload(Sentence.words),
                joinedload(Sentence.word_hints),
            )
            .order_by(Sentence.id.desc())
            .all()
        )

        return render_template("agents/view_sentences.html", lemma=lemma, sentences=sentences)

    except Exception as e:
        log_and_flash_error(e, "viewing sentences")
        return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))


@bp.route("/check-translation-disambiguation/<int:lemma_id>/<lang_code>", methods=["POST"])
def check_translation_disambiguation(lemma_id: int, lang_code: str) -> ResponseReturnValue:
    """Find lemmas sharing the same translation in lang_code and suggest disambiguations."""
    from storage.models.schema import LemmaTranslation
    from storage.translation_helpers import (
        LANGUAGE_NAMES,
        get_all_translations,
    )

    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    language_name = LANGUAGE_NAMES.get(lang_code, lang_code)

    # Get this lemma's translation in the target language
    this_trans = (
        g.db.query(LemmaTranslation)
        .filter(
            LemmaTranslation.lemma_id == lemma_id,
            LemmaTranslation.language_code == lang_code,
        )
        .first()
    )
    if not this_trans or not this_trans.translation:
        flash(f"No {language_name} translation set for this lemma", "error")
        return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

    translation_word = this_trans.translation.strip()

    # Find all other lemmas with the same translation in this language
    matching_rows = (
        g.db.query(LemmaTranslation)
        .filter(
            LemmaTranslation.language_code == lang_code,
            LemmaTranslation.translation == translation_word,
        )
        .all()
    )

    if len(matching_rows) < 2:
        flash(
            f'No other lemmas share the {language_name} translation "{translation_word}" '
            f"- disambiguation not needed",
            "info",
        )
        return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

    # Load the matching lemmas
    matching_lemma_ids = [row.lemma_id for row in matching_rows]
    matching_lemmas = (
        g.db.query(Lemma).filter(Lemma.id.in_(matching_lemma_ids), Lemma.guid.isnot(None)).all()
    )

    if len(matching_lemmas) < 2:
        flash(
            f'No other active lemmas share the {language_name} translation "{translation_word}"',
            "info",
        )
        return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

    # Build disambiguation info for each lemma
    disambiguation_row_lookup = {row.lemma_id: row for row in matching_rows}
    meanings = []
    lemma_lookup = {}
    for ml in matching_lemmas:
        lemma_lookup[ml.guid] = ml
        all_trans = get_all_translations(g.db, ml)
        other_translations = {
            lc: t for lc, t in all_trans.items() if t and lc not in ("en", lang_code)
        }
        meanings.append(
            {
                "guid": ml.guid,
                "english_word": ml.lemma_text,
                "definition": ml.definition_text or "",
                "other_translations": other_translations,
            }
        )

    # Call LLM
    try:
        from wordfreq.tools.llm_validators import suggest_translation_disambiguation

        llm_result = suggest_translation_disambiguation(
            translation_word=translation_word,
            target_language=language_name,
            target_lang_code=lang_code,
            meanings=meanings,
        )
    except Exception as e:
        log_and_flash_error(e, "generating translation disambiguation suggestions")
        return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

    if not llm_result.get("success") or not llm_result.get("suggestions"):
        flash(
            f'Found {len(matching_lemmas)} lemmas sharing "{translation_word}" in {language_name}, '
            f"but could not generate suggestions. Try setting disambiguation manually.",
            "warning",
        )
        return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

    return render_template(
        "agents/translation_disambiguation_suggestions.html",
        lemma=lemma,
        lang_code=lang_code,
        language_name=language_name,
        translation_word=translation_word,
        matching_lemmas=matching_lemmas,
        suggestions=llm_result["suggestions"],
        disambiguation_row_lookup=disambiguation_row_lookup,
    )


@bp.route(
    "/apply-translation-disambiguation/<int:lemma_id>/<lang_code>",
    methods=["POST"],
)
def apply_translation_disambiguation(lemma_id: int, lang_code: str) -> ResponseReturnValue:
    """Apply an AI-suggested translation disambiguation."""
    from storage.models.schema import LemmaTranslation
    from storage.translation_helpers import LANGUAGE_NAMES

    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    new_disambiguation = request.form.get("disambiguation", "").strip()
    return_to_lemma_id = request.form.get("return_to_lemma_id", type=int)

    if not new_disambiguation:
        flash("No disambiguation provided", "error")
        return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

    language_name = LANGUAGE_NAMES.get(lang_code, lang_code)

    try:
        trans_obj = (
            g.db.query(LemmaTranslation)
            .filter(
                LemmaTranslation.lemma_id == lemma_id,
                LemmaTranslation.language_code == lang_code,
            )
            .first()
        )

        if not trans_obj:
            flash(f"No {language_name} translation found for this lemma", "error")
            return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

        old_disambiguation = trans_obj.disambiguation
        trans_obj.disambiguation = new_disambiguation
        g.db.commit()

        flash(
            f'Set {language_name} disambiguation for "{lemma.lemma_text}" '
            f'({lemma.guid}): "{new_disambiguation}"',
            "success",
        )

    except Exception as e:
        g.db.rollback()
        log_and_flash_error(e, "applying translation disambiguation")

    # Return to the original lemma that triggered the check
    target_lemma_id = return_to_lemma_id or lemma_id
    return redirect(
        url_for(
            "agents.check_translation_disambiguation",
            lemma_id=target_lemma_id,
            lang_code=lang_code,
        )
    )
