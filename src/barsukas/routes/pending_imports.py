#!/usr/bin/python3

"""Routes for viewing pending imports.

MIRRORED: routes annotated with ``@mirrored_facade`` have a typed Python
wrapper in the root-level ``api/`` package (``api/batch_operations.py``).
Edits to a mirrored route's path, query params, or response shape MUST be
made in the matching facade in the same commit. See ``api/AGENTS.md``.
"""

import json
import logging
from typing import Any, Dict, List, Sequence, cast

from barsukas.config import Config
from barsukas.routes._mirror import mirrored_facade
from words.pending_imports.approval import (
    approve_pending_import,
    delete_pending_import,
    reject_pending_import,
)
from words.pending_imports.classification import classify_pending_import, suggest_target_kind
from words.pending_imports.sentence_links import sentence_ids_waiting_on
from words.pending_imports.synonym_screening import (
    ACCEPTED_STATUS,
    ACTIVE_STATUS,
    has_active_strong_synonym_candidate,
    ignore_synonym_candidates,
    run_synonym_screening,
)
from workqueue.task_queue import TaskType, enqueue_task
from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue
from sqlalchemy.orm import Query

from storage.backend.config import DataSourceConfig
from storage.crud.derivative_form import add_derivative_form
from storage.crud.word_token import add_word_token
from storage.models.imports import (
    PENDING_IMPORT_TARGET_KIND_LABELS,
    PENDING_IMPORT_TARGET_KINDS,
    TARGET_KIND_LEMMA,
    TARGET_KIND_NAME,
    PendingImport,
    PendingImportSynonymCandidate,
)
from storage.models.name_entity import NAME_KINDS
from storage.models.schema import DerivativeForm, Lemma

bp = Blueprint("pending_imports", __name__, url_prefix="/pending-imports")
logger = logging.getLogger(__name__)


def _json_list(value: str) -> List[str]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, str)]


def _serialize_synonym_candidate(candidate: PendingImportSynonymCandidate) -> Dict[str, Any]:
    lemma_data = None
    if candidate.lemma is not None:
        lemma_data = {
            "id": candidate.lemma.id,
            "guid": candidate.lemma.guid,
            "lemma_text": candidate.lemma.lemma_text,
            "definition_text": candidate.lemma.definition_text,
            "pos_type": candidate.lemma.pos_type,
            "pos_subtype": candidate.lemma.pos_subtype,
        }
    return {
        "id": candidate.id,
        "candidate_text": candidate.candidate_text,
        "lemma": lemma_data,
        "same_pos": candidate.same_pos,
        "llm_synonym_category": candidate.llm_synonym_category,
        "llm_synonym_score": candidate.llm_synonym_score,
        "matched_translation_count": candidate.matched_translation_count,
        "matched_translation_languages": _json_list(candidate.matched_translation_languages),
        "explanation": candidate.explanation,
        "is_strong": candidate.is_strong,
        "status": candidate.status,
    }


def _active_synonym_candidates_for_pending(
    pending_import_id: int,
) -> List[PendingImportSynonymCandidate]:
    return cast(
        List[PendingImportSynonymCandidate],
        g.db.query(PendingImportSynonymCandidate)
        .filter(
            PendingImportSynonymCandidate.pending_import_id == pending_import_id,
            PendingImportSynonymCandidate.status == ACTIVE_STATUS,
        )
        .order_by(
            PendingImportSynonymCandidate.is_strong.desc(),
            PendingImportSynonymCandidate.matched_translation_count.desc(),
            PendingImportSynonymCandidate.llm_synonym_score.desc().nullslast(),
            PendingImportSynonymCandidate.id,
        )
        .all(),
    )


def _build_filtered_query() -> Query[Any]:
    """Build a filtered query for pending imports based on request args."""
    search = request.args.get("search", "").strip()
    pos_type_filter = request.args.get("pos_type", "").strip()
    pos_subtype_filter = request.args.get("pos_subtype", "").strip()
    source_filter = request.args.get("source", "").strip()
    language_filter = request.args.get("language", "").strip()
    target_kind_filter = request.args.get("target_kind", "").strip()

    query = g.db.query(PendingImport)

    if search:
        query = query.filter(
            (PendingImport.english_word.ilike(f"%{search}%"))
            | (PendingImport.definition.ilike(f"%{search}%"))
            | (PendingImport.disambiguation_translation.ilike(f"%{search}%"))
        )

    if pos_type_filter:
        query = query.filter(PendingImport.pos_type == pos_type_filter)

    if pos_subtype_filter:
        query = query.filter(PendingImport.pos_subtype == pos_subtype_filter)

    if source_filter:
        query = query.filter(PendingImport.source == source_filter)

    if language_filter:
        query = query.filter(PendingImport.disambiguation_language == language_filter)

    if target_kind_filter:
        query = query.filter(PendingImport.target_kind == target_kind_filter)

    return cast(Query[Any], query.order_by(PendingImport.added_at.desc()))


@bp.route("/")
def list_pending_imports() -> ResponseReturnValue:
    """List pending imports with pagination and filtering."""
    page = request.args.get("page", 1, type=int)

    query = _build_filtered_query()

    # Paginate
    total = query.count()
    imports = query.limit(Config.ITEMS_PER_PAGE).offset((page - 1) * Config.ITEMS_PER_PAGE).all()
    import_ids = [pending_import.id for pending_import in imports]
    strong_candidate_counts: Dict[int, int] = {
        pending_import_id: 0 for pending_import_id in import_ids
    }
    candidate_counts: Dict[int, int] = {pending_import_id: 0 for pending_import_id in import_ids}
    if import_ids:
        rows = (
            g.db.query(
                PendingImportSynonymCandidate.pending_import_id,
                PendingImportSynonymCandidate.is_strong,
            )
            .filter(
                PendingImportSynonymCandidate.pending_import_id.in_(import_ids),
                PendingImportSynonymCandidate.status == ACTIVE_STATUS,
            )
            .all()
        )
        for pending_import_id, is_strong in rows:
            candidate_counts[pending_import_id] = candidate_counts.get(pending_import_id, 0) + 1
            if is_strong:
                strong_candidate_counts[pending_import_id] = (
                    strong_candidate_counts.get(pending_import_id, 0) + 1
                )

    # Get unique values for filter dropdowns
    pos_types = (
        g.db.query(PendingImport.pos_type)
        .distinct()
        .filter(PendingImport.pos_type.isnot(None))
        .order_by(PendingImport.pos_type)
        .all()
    )
    pos_types = [p[0] for p in pos_types if p[0]]

    pos_subtypes = (
        g.db.query(PendingImport.pos_subtype)
        .distinct()
        .filter(PendingImport.pos_subtype.isnot(None))
        .order_by(PendingImport.pos_subtype)
        .all()
    )
    pos_subtypes = [p[0] for p in pos_subtypes if p[0]]

    sources = (
        g.db.query(PendingImport.source)
        .distinct()
        .filter(PendingImport.source.isnot(None))
        .order_by(PendingImport.source)
        .all()
    )
    sources = [s[0] for s in sources if s[0]]

    languages = (
        g.db.query(PendingImport.disambiguation_language)
        .distinct()
        .order_by(PendingImport.disambiguation_language)
        .all()
    )
    languages = [lang[0] for lang in languages if lang[0]]

    # Calculate pagination
    search = request.args.get("search", "").strip()
    pos_type_filter = request.args.get("pos_type", "").strip()
    pos_subtype_filter = request.args.get("pos_subtype", "").strip()
    source_filter = request.args.get("source", "").strip()
    language_filter = request.args.get("language", "").strip()
    target_kind_filter = request.args.get("target_kind", "").strip()
    total_pages = (total + Config.ITEMS_PER_PAGE - 1) // Config.ITEMS_PER_PAGE

    return render_template(
        "pending_imports/list.html",
        imports=imports,
        page=page,
        total_pages=total_pages,
        total=total,
        search=search,
        pos_type_filter=pos_type_filter,
        pos_subtype_filter=pos_subtype_filter,
        source_filter=source_filter,
        language_filter=language_filter,
        pos_types=pos_types,
        pos_subtypes=pos_subtypes,
        sources=sources,
        languages=languages,
        candidate_counts=candidate_counts,
        strong_candidate_counts=strong_candidate_counts,
        target_kind_filter=target_kind_filter,
        target_kinds=PENDING_IMPORT_TARGET_KINDS,
        target_kind_labels=PENDING_IMPORT_TARGET_KIND_LABELS,
    )


def _requeue_waiting_sentences(session: Any, sentence_ids: Sequence[int]) -> None:
    """Re-run the import workflow for sentences unblocked by an approval.

    Best-effort: a queueing failure must not undo an approval that already
    succeeded, so problems are logged rather than raised.
    """
    for sentence_id in sentence_ids:
        try:
            enqueue_task(
                session,
                task_type=TaskType.SENTENCES_IMPORT,
                target_type="sentence",
                target_id=sentence_id,
                payload={"sentence_id": sentence_id},
                dedup_key=f"{TaskType.SENTENCES_IMPORT}:{sentence_id}:0",
            )
        except Exception as exc:
            logger.warning("Could not re-queue sentence %s after approval: %s", sentence_id, exc)

    if sentence_ids:
        flash(
            f"Re-queued {len(sentence_ids)} sentence(s) that were waiting on this word.",
            "info",
        )


@bp.route("/<int:pending_import_id>/approve", methods=["POST"])
def approve(pending_import_id: int) -> ResponseReturnValue:
    """Approve a pending import entry and import it into lemmas."""
    if current_app.config.get("READONLY", False):
        flash("Cannot modify data in read-only mode", "error")
        return redirect(request.referrer or url_for("pending_imports.list_pending_imports"))

    try:
        model_name = str(current_app.config.get("DEFAULT_LLM_MODEL", "gpt-5.4-mini"))
        debug = bool(current_app.config.get("DEBUG", False))
        base_config = cast(DataSourceConfig, current_app.backend_config)  # type: ignore[attr-defined]
        data_source_config = base_config.with_model(model_name, debug=debug)
        # Read before approving: a successful approval deletes the pending row,
        # which is what the hints point at.
        waiting_sentence_ids = sentence_ids_waiting_on(g.db, pending_import_id)
        result = approve_pending_import(
            session=g.db,
            pending_import_id=pending_import_id,
            data_source_config=data_source_config,
            model=model_name,
            debug=debug,
        )
        if result.get("success"):
            flash(result.get("message", f"Approved pending import #{pending_import_id}"), "success")
            _requeue_waiting_sentences(g.db, waiting_sentence_ids)
            new_lemma_id = result.get("lemma_id")
            if new_lemma_id:
                try:
                    enqueue_task(
                        g.db,
                        task_type=TaskType.ADD_MISSING_TRANSLATIONS,
                        target_type="lemma",
                        target_id=new_lemma_id,
                        payload={"lemma_id": new_lemma_id},
                        dedup_key=f"{TaskType.ADD_MISSING_TRANSLATIONS}:{new_lemma_id}",
                    )
                    flash("Queued translation generation for all tier 1/2 languages.", "info")
                except Exception as enqueue_exc:
                    logger.warning(
                        "Could not enqueue translations for lemma %s: %s", new_lemma_id, enqueue_exc
                    )
        else:
            flash(result.get("error", "Failed to approve pending import"), "error")
    except Exception as exc:
        g.db.rollback()
        flash(f"Error approving pending import: {exc}", "error")

    return redirect(url_for("pending_imports.list_pending_imports"))


@bp.route("/<int:pending_import_id>/create-anyway", methods=["POST"])
def create_anyway(pending_import_id: int) -> ResponseReturnValue:
    """Ignore active synonym candidates so normal approval can continue."""
    if current_app.config.get("READONLY", False):
        flash("Cannot modify data in read-only mode", "error")
        return redirect(request.referrer or url_for("pending_imports.list_pending_imports"))

    pending = g.db.query(PendingImport).filter(PendingImport.id == pending_import_id).first()
    if not pending:
        abort(404)

    ignored_count = ignore_synonym_candidates(g.db, pending_import_id)
    g.db.commit()
    flash(f"Ignored {ignored_count} synonym candidate(s). Normal approval is now enabled.", "info")
    return redirect(url_for("pending_imports.detail", pending_import_id=pending_import_id))


@bp.route(
    "/<int:pending_import_id>/use-synonym/<int:candidate_id>",
    methods=["POST"],
)
def use_synonym(pending_import_id: int, candidate_id: int) -> ResponseReturnValue:
    """Attach the pending English word as a synonym form on an existing lemma."""
    if current_app.config.get("READONLY", False):
        flash("Cannot modify data in read-only mode", "error")
        return redirect(request.referrer or url_for("pending_imports.list_pending_imports"))

    pending = g.db.query(PendingImport).filter(PendingImport.id == pending_import_id).first()
    if not pending:
        abort(404)

    candidate = (
        g.db.query(PendingImportSynonymCandidate)
        .filter(
            PendingImportSynonymCandidate.id == candidate_id,
            PendingImportSynonymCandidate.pending_import_id == pending_import_id,
        )
        .first()
    )
    if not candidate:
        abort(404)
    if candidate.lemma_id is None:
        flash("Cannot use this candidate because it is not linked to an existing lemma.", "error")
        return redirect(url_for("pending_imports.detail", pending_import_id=pending_import_id))

    lemma = g.db.query(Lemma).filter(Lemma.id == candidate.lemma_id).first()
    if lemma is None:
        flash("Cannot use this candidate because the linked lemma no longer exists.", "error")
        return redirect(url_for("pending_imports.detail", pending_import_id=pending_import_id))

    try:
        pending_word = pending.english_word
        word_token = add_word_token(g.db, pending.english_word, "en")
        existing_form = (
            g.db.query(DerivativeForm)
            .filter(
                DerivativeForm.lemma_id == lemma.id,
                DerivativeForm.language_code == "en",
                DerivativeForm.derivative_form_text == pending.english_word,
                DerivativeForm.grammatical_form == "synonym",
            )
            .first()
        )
        if existing_form is None:
            add_derivative_form(
                g.db,
                lemma,
                pending.english_word,
                "en",
                "synonym",
                word_token=word_token,
                is_base_form=False,
                verified=False,
                notes=f"Accepted from pending import #{pending.id}",
            )
        candidate.status = ACCEPTED_STATUS
        # The word became a synonym form of this lemma, so every sentence
        # waiting on the pending row is pointed at that lemma before the row
        # (and its links) go away.
        delete_pending_import(g.db, pending, lemma_id=lemma.id)
        g.db.commit()
        flash(
            f"Added '{pending_word}' as an English synonym for {lemma.lemma_text}.",
            "success",
        )
    except Exception as exc:
        g.db.rollback()
        flash(f"Error accepting synonym candidate: {exc}", "error")
        return redirect(url_for("pending_imports.detail", pending_import_id=pending_import_id))

    return redirect(url_for("pending_imports.list_pending_imports"))


@bp.route("/<int:pending_import_id>/reject", methods=["POST"])
def reject(pending_import_id: int) -> ResponseReturnValue:
    """Reject a pending import entry and remove it from pending list."""
    if current_app.config.get("READONLY", False):
        flash("Cannot modify data in read-only mode", "error")
        return redirect(request.referrer or url_for("pending_imports.list_pending_imports"))

    try:
        result = reject_pending_import(
            session=g.db,
            pending_import_id=pending_import_id,
            reason="barsukas_manual_rejection",
            add_to_exclusions=True,
        )
        if result.get("success"):
            flash(result.get("message", f"Rejected pending import #{pending_import_id}"), "success")
        else:
            flash(result.get("error", "Failed to reject pending import"), "error")
    except Exception as exc:
        g.db.rollback()
        flash(f"Error rejecting pending import: {exc}", "error")

    return redirect(url_for("pending_imports.list_pending_imports"))


@bp.route("/<int:pending_import_id>/detail")
def detail(pending_import_id: int) -> ResponseReturnValue:
    """Show detail/status page for a single pending import."""
    pending = g.db.query(PendingImport).filter(PendingImport.id == pending_import_id).first()
    if not pending:
        abort(404)
    synonym_candidates = [
        _serialize_synonym_candidate(candidate)
        for candidate in _active_synonym_candidates_for_pending(pending_import_id)
    ]
    has_strong_synonym_candidate = any(candidate["is_strong"] for candidate in synonym_candidates)
    suggestion = suggest_target_kind(
        g.db,
        pending.english_word,
        example_sentence=pending.example_sentence,
        pos_type=pending.pos_type,
    )
    return render_template(
        "pending_imports/detail.html",
        item=pending,
        synonym_candidates=synonym_candidates,
        has_strong_synonym_candidate=has_strong_synonym_candidate,
        target_kinds=PENDING_IMPORT_TARGET_KINDS,
        target_kind_labels=PENDING_IMPORT_TARGET_KIND_LABELS,
        name_kinds=NAME_KINDS,
        suggestion=suggestion,
        waiting_sentence_ids=sentence_ids_waiting_on(g.db, pending_import_id),
    )


@bp.route("/<int:pending_import_id>/stage", methods=["POST"])
def stage(pending_import_id: int) -> ResponseReturnValue:
    """AJAX endpoint: query LLM and store pos_subtype/definition back into PendingImport."""
    if current_app.config.get("READONLY", False):
        return jsonify({"success": False, "error": "Cannot modify data in read-only mode"}), 403

    pending = g.db.query(PendingImport).filter(PendingImport.id == pending_import_id).first()
    if not pending:
        return jsonify({"success": False, "error": "Pending import not found"}), 404

    model_name = str(current_app.config.get("DEFAULT_LLM_MODEL", "gpt-5.4-mini"))
    debug = bool(current_app.config.get("DEBUG", False))
    base_config = cast(DataSourceConfig, current_app.backend_config)  # type: ignore[attr-defined]
    data_source_config = base_config.with_model(model_name, debug=debug)

    try:
        from wordfreq.translation.client import LinguisticClient

        # Accept an updated example_sentence from the request and save it before querying
        body = request.get_json(silent=True) or {}
        example_sentence = body.get("example_sentence") or None
        if example_sentence and example_sentence != pending.example_sentence:
            pending.example_sentence = example_sentence
            g.db.flush()

        client = LinguisticClient(config=data_source_config)

        # What the term should become is decided before its definitions are
        # looked up: asking for the senses of "George" is a wasted call, and
        # the answer would be nonsense if it came back at all.
        suggestion = classify_pending_import(g.db, pending, client.client, model=model_name)
        if suggestion.target_kind != TARGET_KIND_LEMMA:
            g.db.commit()
            return jsonify(
                {
                    "success": True,
                    "target_kind": pending.target_kind,
                    "name_kind": pending.name_kind,
                    "concept_type": pending.concept_type,
                    "classification_reason": suggestion.reason,
                    "definitions": [],
                    "synonym_candidates": [],
                    "has_strong_synonym_candidate": False,
                }
            )

        definitions_list, llm_success = client.query_definitions(
            pending.english_word, example_sentence=pending.example_sentence
        )

        if not llm_success or not definitions_list:
            return jsonify(
                {
                    "success": False,
                    "error": f"LLM returned no definitions for '{pending.english_word}'",
                }
            )

        # Filter to matching pos_type if the pending import has one
        if pending.pos_type:
            matching = [d for d in definitions_list if d.get("pos") == pending.pos_type]
            if matching:
                definitions_list = matching

        # Use the first matching definition to populate the stored fields
        first = definitions_list[0]
        pending.pos_type = first.get("pos") or pending.pos_type
        pending.pos_subtype = first.get("pos_subtype") or pending.pos_subtype
        if first.get("definition"):
            pending.definition = first["definition"]
        synonym_candidates = run_synonym_screening(
            g.db,
            pending,
            client.client,
            model=model_name,
        )
        g.db.commit()

        return jsonify(
            {
                "success": True,
                "target_kind": pending.target_kind,
                "name_kind": pending.name_kind,
                "concept_type": pending.concept_type,
                "classification_reason": suggestion.reason,
                "definitions": definitions_list,
                "synonym_candidates": [
                    _serialize_synonym_candidate(candidate) for candidate in synonym_candidates
                ],
                "has_strong_synonym_candidate": has_active_strong_synonym_candidate(
                    g.db, pending_import_id
                ),
            }
        )

    except Exception as exc:
        g.db.rollback()
        logger.exception("Error staging pending import %d", pending_import_id)
        return jsonify({"success": False, "error": str(exc)}), 500


@bp.route("/<int:pending_import_id>/set-kind", methods=["POST"])
def set_kind(pending_import_id: int) -> ResponseReturnValue:
    """Set what this term becomes on approval: a lemma, a name, or a concept.

    An ordinary form submit, not AJAX: this is a decision a reviewer makes and
    then acts on, so it belongs in the page's history.
    """
    if current_app.config.get("READONLY", False):
        flash("Cannot modify data in read-only mode", "error")
        return redirect(request.referrer or url_for("pending_imports.list_pending_imports"))

    pending = g.db.query(PendingImport).filter(PendingImport.id == pending_import_id).first()
    if not pending:
        abort(404)

    target_kind = request.form.get("target_kind", "").strip()
    if target_kind not in PENDING_IMPORT_TARGET_KINDS:
        flash(f"Unknown target kind {target_kind!r}", "error")
        return redirect(url_for("pending_imports.detail", pending_import_id=pending_import_id))

    pending.target_kind = target_kind

    name_kind = request.form.get("name_kind", "").strip()
    if target_kind == TARGET_KIND_NAME and name_kind in NAME_KINDS:
        pending.name_kind = name_kind

    concept_type = request.form.get("concept_type", "").strip()
    if concept_type:
        pending.concept_type = concept_type

    g.db.commit()
    flash(
        f"'{pending.english_word}' will be approved as a "
        f"{PENDING_IMPORT_TARGET_KIND_LABELS.get(target_kind, target_kind)}.",
        "success",
    )
    return redirect(url_for("pending_imports.detail", pending_import_id=pending_import_id))


@bp.route("/api/duplicates")
@mirrored_facade("/pending-imports/api/duplicates", "GET")
def api_duplicates() -> ResponseReturnValue:
    """JSON API: find pending imports that are duplicates of existing lemmas.

    A duplicate is either:
    - A direct match: an existing lemma with the same lemma_text and pos_type.
    - A form match: the pending english_word appears as a DerivativeForm
      (language_code='en') of an existing lemma with the same pos_type.

    Only pending imports destined to become lemmas, and only those where
    definition == english_word (no real definition yet), are checked: a name or
    a concept is not a duplicate of a lemma that happens to be spelled like it,
    and staged imports with real definitions need human review regardless.

    Returns {"data": [...]} where each item has pending import fields plus
    "match_type" ("direct" or "form"), "matched_lemma_guid", "matched_lemma_text".
    """
    from storage.models.schema import DerivativeForm
    from storage.models import Lemma

    # Only check imports that have not yet been staged (definition = english_word)
    pending_list = (
        g.db.query(PendingImport)
        .filter(
            PendingImport.definition == PendingImport.english_word,
            PendingImport.target_kind == TARGET_KIND_LEMMA,
        )
        .order_by(PendingImport.added_at.desc())
        .all()
    )

    results = []

    for item in pending_list:
        word_lower = item.english_word.lower()
        pos = item.pos_type

        # 1. Direct lemma match
        direct_query = g.db.query(Lemma).filter(Lemma.lemma_text.ilike(word_lower))
        if pos:
            direct_query = direct_query.filter(Lemma.pos_type == pos)
        direct_match = direct_query.first()
        if direct_match:
            results.append(
                {
                    "id": item.id,
                    "english_word": item.english_word,
                    "pos_type": item.pos_type,
                    "source": item.source,
                    "added_at": item.added_at.isoformat() if item.added_at else None,
                    "match_type": "direct",
                    "matched_lemma_guid": direct_match.guid,
                    "matched_lemma_text": direct_match.lemma_text,
                    "matched_pos_type": direct_match.pos_type,
                }
            )
            continue

        # 2. Derivative form match (e.g. "telling" → lemma "tell")
        form_query = (
            g.db.query(DerivativeForm, Lemma)
            .join(Lemma, DerivativeForm.lemma_id == Lemma.id)
            .filter(
                DerivativeForm.derivative_form_text.ilike(word_lower),
                DerivativeForm.language_code == "en",
            )
        )
        if pos:
            form_query = form_query.filter(Lemma.pos_type == pos)
        form_match = form_query.first()
        if form_match:
            _form, matched_lemma = form_match
            results.append(
                {
                    "id": item.id,
                    "english_word": item.english_word,
                    "pos_type": item.pos_type,
                    "source": item.source,
                    "added_at": item.added_at.isoformat() if item.added_at else None,
                    "match_type": "form",
                    "matched_lemma_guid": matched_lemma.guid,
                    "matched_lemma_text": matched_lemma.lemma_text,
                    "matched_pos_type": matched_lemma.pos_type,
                }
            )

    return jsonify(
        {"data": results, "metadata": {"total": len(results), "checked": len(pending_list)}}
    )


@bp.route("/api/list")
@mirrored_facade("/pending-imports/api/list", "GET")
def api_list() -> ResponseReturnValue:
    """JSON API: list pending imports with optional filtering.

    Supports the same query parameters as the HTML list view:
    search, pos_type, pos_subtype, source, language, page.
    Returns {"data": [...], "metadata": {"total": N, "page": P, "total_pages": T}}.
    """
    page = request.args.get("page", 1, type=int)
    query = _build_filtered_query()
    total = query.count()
    imports = query.limit(Config.ITEMS_PER_PAGE).offset((page - 1) * Config.ITEMS_PER_PAGE).all()
    total_pages = (total + Config.ITEMS_PER_PAGE - 1) // Config.ITEMS_PER_PAGE

    data = [
        {
            "id": item.id,
            "english_word": item.english_word,
            "definition": item.definition,
            "disambiguation_translation": item.disambiguation_translation,
            "disambiguation_language": item.disambiguation_language,
            "target_kind": item.target_kind,
            "name_kind": item.name_kind,
            "concept_type": item.concept_type,
            "pos_type": item.pos_type,
            "pos_subtype": item.pos_subtype,
            "example_sentence": item.example_sentence,
            "source": item.source,
            "frequency_rank": item.frequency_rank,
            "notes": item.notes,
            "synonym_candidate_count": len(_active_synonym_candidates_for_pending(item.id)),
            "has_strong_synonym_candidate": has_active_strong_synonym_candidate(g.db, item.id),
            "added_at": item.added_at.isoformat() if item.added_at else None,
        }
        for item in imports
    ]
    return jsonify(
        {
            "data": data,
            "metadata": {"total": total, "page": page, "total_pages": total_pages},
        }
    )


@bp.route("/export.txt")
def export_text() -> Response:
    """Export filtered pending imports as a tab-separated text file."""
    query = _build_filtered_query()
    imports = query.all()

    lines = ["Word\tDefinition\tPOS"]
    for item in imports:
        pos = item.pos_type or ""
        if item.pos_subtype:
            pos += f"/{item.pos_subtype}"
        lines.append(f"{item.english_word}\t{item.definition}\t{pos}")

    return Response(
        "\n".join(lines) + "\n",
        mimetype="text/plain; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=pending_imports.txt"},
    )
