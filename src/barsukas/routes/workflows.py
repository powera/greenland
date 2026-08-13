#!/usr/bin/python3

"""Per-item workflow views: one lemma or one sentence, stage by stage.

The AI Agents launcher answers "run this agent over everything that needs it".
These pages answer the other question: "this one word -- or this one sentence --
what still has to happen to it, and what do I click to make it happen?"

Both flows derive their stages by reading the data rather than from a stored
status. Nothing needs backfilling, the view is correct for rows created by any
path, and a stage that is undone by a later edit simply reopens.

The sentence flow's stage predicates live in ``sentences.import_workflow``,
where the ``sentences.import`` task also reads them, so the page and the worker
cannot disagree about what is done. The lemma flow's predicates are inline
here: they exist to drive this page, and no worker consults them yet. If they
grow a second consumer they should move into a module of their own, mirroring
the sentence side.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue
from sqlalchemy import func

from sentences.import_workflow import (
    STAGE_ORDER,
    SentenceImportSpec,
    SentenceImportStage,
    evaluate_all,
    next_incomplete_stage,
)
from storage.models.grammar_fact import GrammarFact
from storage.models.schema import (
    SYNONYM_GRAMMATICAL_FORMS,
    DerivativeForm,
    Lemma,
    LemmaTranslation,
    Sentence,
    SentenceTranslation,
    SentenceWord,
    SentenceWordHint,
)
from storage.models.imports import PendingImport
from workqueue.task_queue import TaskType, enqueue_task

bp = Blueprint("workflows", __name__, url_prefix="/workflows")
logger = logging.getLogger(__name__)

# Languages a lemma is expected to reach before it counts as translated. Kept
# short deliberately: this drives a progress indicator, not an export gate.
LEMMA_CORE_LANGUAGES: List[str] = ["lt", "es", "fr", "zh"]

# Plain-language descriptions of each sentence stage's completion test, shown
# beside the stage so the page explains itself without reading the source.
SENTENCE_STAGE_HELP: Dict[str, Dict[str, str]] = {
    "ingest": {
        "title": "Ingested",
        "test": "The sentence exists and has at least one translation to work from.",
    },
    "translate": {
        "title": "Translated",
        "test": "Every target language has a translation.",
    },
    "decompose": {
        "title": "Decomposed",
        "test": "Every decompose language is broken into per-word rows.",
    },
    "annotate": {
        "title": "Dependencies annotated",
        "test": "Every word carries a Universal Dependencies relation. Skipped unless requested.",
    },
    "link": {
        "title": "Words linked to lemmas",
        "test": "Every word that should have a lemma has one. Grammatical words are exempt.",
    },
    "stage": {
        "title": "Missing words staged",
        "test": "Every unlinked word has a pending import waiting for approval.",
    },
    "promote": {
        "title": "Staged words promoted",
        "test": "No pending import is still blocking this sentence.",
    },
    "idioms": {
        "title": "Idioms detected",
        "test": "Deferred. Needs a sentence-to-idiom link and multi-word staging.",
    },
    "finalize": {
        "title": "Finalized",
        "test": "The stored difficulty level matches the linked lemmas.",
    },
}


@dataclass
class WorkflowStep:
    """One stage of a flow, as the template needs it."""

    key: str
    title: str
    test: str
    complete: bool
    blocked_reason: Optional[str] = None
    detail: Optional[Dict[str, Any]] = None
    action_label: Optional[str] = None
    action_endpoint: Optional[str] = None
    deferred: bool = False

    @property
    def status(self) -> str:
        if self.deferred:
            return "deferred"
        if self.complete:
            return "complete"
        if self.blocked_reason:
            return "blocked"
        return "pending"


# ---------------------------------------------------------------------- #
# Lemma flow                                                              #
# ---------------------------------------------------------------------- #


def _lemma_steps(session: Any, lemma: Lemma) -> List[WorkflowStep]:
    """Derive one lemma's stage list from what is in the database.

    Ordered to match the batch pipeline on the AI Agents page, so the two
    describe the same journey at different scales.
    """
    translations = {
        str(row[0])
        for row in session.query(LemmaTranslation.language_code)
        .filter(LemmaTranslation.lemma_id == lemma.id)
        .all()
        if row[0]
    }
    missing_languages = [code for code in LEMMA_CORE_LANGUAGES if code not in translations]

    form_count = (
        session.query(func.count(DerivativeForm.id))
        .filter(DerivativeForm.lemma_id == lemma.id)
        .scalar()
        or 0
    )

    forms_missing_pronunciation = (
        session.query(func.count(DerivativeForm.id))
        .filter(
            DerivativeForm.lemma_id == lemma.id,
            DerivativeForm.ipa_pronunciation.is_(None),
        )
        .scalar()
        or 0
    )

    synonym_count = (
        session.query(func.count(DerivativeForm.id))
        .filter(
            DerivativeForm.lemma_id == lemma.id,
            DerivativeForm.grammatical_form.in_(sorted(SYNONYM_GRAMMATICAL_FORMS)),
        )
        .scalar()
        or 0
    )

    grammar_fact_count = (
        session.query(func.count(GrammarFact.id)).filter(GrammarFact.lemma_id == lemma.id).scalar()
        or 0
    )

    sentence_count = (
        session.query(func.count(func.distinct(SentenceWord.sentence_id)))
        .filter(SentenceWord.lemma_id == lemma.id)
        .scalar()
        or 0
    )

    return [
        WorkflowStep(
            key="validate",
            title="Validated",
            test="The lemma has a definition and a part of speech.",
            complete=bool(lemma.definition_text and lemma.pos_type),
            detail={"pos_type": lemma.pos_type, "guid": lemma.guid},
        ),
        WorkflowStep(
            key="translations",
            title="Translated",
            test=f"Has a translation in each of: {', '.join(LEMMA_CORE_LANGUAGES)}.",
            complete=not missing_languages,
            detail={"missing_languages": missing_languages, "have": sorted(translations)},
            action_label="Generate translations",
            action_endpoint=TaskType.WORDS_TRANSLATIONS,
        ),
        WorkflowStep(
            key="forms",
            title="Word forms generated",
            test="Has at least one derivative form.",
            complete=form_count > 0,
            detail={"form_count": int(form_count)},
            action_label="Generate forms",
            action_endpoint=TaskType.WORDS_FORMS,
        ),
        WorkflowStep(
            key="pronunciations",
            title="Pronunciations generated",
            test="Every derivative form has an IPA pronunciation.",
            complete=form_count > 0 and forms_missing_pronunciation == 0,
            blocked_reason="no forms to pronounce yet" if form_count == 0 else None,
            detail={"missing": int(forms_missing_pronunciation)},
            action_label="Generate pronunciations",
            action_endpoint=TaskType.WORDS_PRONUNCIATIONS,
        ),
        WorkflowStep(
            key="synonyms",
            title="Synonyms generated",
            test="Has at least one synonym-type derivative form.",
            complete=synonym_count > 0,
            detail={"synonym_count": int(synonym_count)},
            action_label="Generate synonyms",
            action_endpoint=TaskType.WORDS_SYNONYMS,
        ),
        WorkflowStep(
            key="grammar_facts",
            title="Grammar facts generated",
            test=(
                "Has at least one grammar fact. Only positive assertions are stored, "
                "so a word with ordinary grammar legitimately has none."
            ),
            complete=grammar_fact_count > 0,
            detail={"fact_count": int(grammar_fact_count)},
            action_label="Generate grammar facts",
            action_endpoint=TaskType.WORDS_GRAMMAR_FACTS,
        ),
        WorkflowStep(
            key="sentences",
            title="Example sentences",
            test="At least one sentence uses this lemma.",
            complete=sentence_count > 0,
            detail={"sentence_count": int(sentence_count)},
        ),
    ]


@bp.route("/lemma")
def lemma_workflow() -> ResponseReturnValue:
    """Per-lemma workflow. Shows one lemma's stages, or a search prompt."""
    lemma_id = request.args.get("lemma_id", type=int)
    query_text = (request.args.get("q") or "").strip()

    lemma: Optional[Lemma] = None
    matches: List[Lemma] = []

    if lemma_id:
        lemma = g.db.get(Lemma, lemma_id)
        if lemma is None:
            flash(f"Lemma {lemma_id} not found", "error")
    elif query_text:
        matches = (
            g.db.query(Lemma)
            .filter(Lemma.lemma_text.ilike(f"%{query_text}%"))
            .order_by(Lemma.lemma_text)
            .limit(25)
            .all()
        )
        if len(matches) == 1:
            lemma = matches[0]
            matches = []
        elif not matches:
            flash(f"No lemma matched {query_text!r}", "info")

    steps = _lemma_steps(g.db, lemma) if lemma is not None else []
    return render_template(
        "workflows/lemma.html",
        lemma=lemma,
        matches=matches,
        query_text=query_text,
        steps=steps,
    )


@bp.route("/lemma/<int:lemma_id>/run/<task_type>", methods=["POST"])
def run_lemma_task(lemma_id: int, task_type: str) -> ResponseReturnValue:
    """Queue one pipeline task for one lemma."""
    if current_app.config.get("READONLY", False):
        flash("Cannot modify data in read-only mode", "error")
        return redirect(url_for("workflows.lemma_workflow", lemma_id=lemma_id))

    allowed = {
        TaskType.WORDS_TRANSLATIONS,
        TaskType.WORDS_FORMS,
        TaskType.WORDS_PRONUNCIATIONS,
        TaskType.WORDS_SYNONYMS,
        TaskType.WORDS_GRAMMAR_FACTS,
    }
    if task_type not in allowed:
        flash(f"Unknown task {task_type}", "error")
        return redirect(url_for("workflows.lemma_workflow", lemma_id=lemma_id))

    lemma = g.db.get(Lemma, lemma_id)
    if lemma is None:
        flash(f"Lemma {lemma_id} not found", "error")
        return redirect(url_for("workflows.lemma_workflow"))

    try:
        enqueue_task(
            g.db,
            task_type=task_type,
            target_type="lemma",
            target_id=lemma_id,
            payload={"lemma_id": lemma_id},
            dedup_key=f"{task_type}:{lemma_id}",
        )
        g.db.commit()
        flash(f"Queued {task_type} for {lemma.lemma_text}.", "success")
    except Exception as exc:
        g.db.rollback()
        flash(f"Could not queue {task_type}: {exc}", "error")

    return redirect(url_for("workflows.lemma_workflow", lemma_id=lemma_id))


# ---------------------------------------------------------------------- #
# Sentence flow                                                           #
# ---------------------------------------------------------------------- #


def _sentence_steps(session: Any, sentence_id: int, spec: SentenceImportSpec) -> List[WorkflowStep]:
    """Turn the shared stage predicates into template rows."""
    steps: List[WorkflowStep] = []
    for status in evaluate_all(session, sentence_id, spec=spec):
        help_text = SENTENCE_STAGE_HELP.get(status.stage.value, {})
        steps.append(
            WorkflowStep(
                key=status.stage.value,
                title=help_text.get("title", status.stage.value.title()),
                test=help_text.get("test", ""),
                complete=status.complete,
                blocked_reason=status.blocked_reason,
                detail=status.detail,
                deferred=status.stage is SentenceImportStage.IDIOMS,
            )
        )
    return steps


def _sentence_display_text(session: Any, sentence_id: int) -> str:
    """Best available text for a sentence: English if present, else anything."""
    rows = (
        session.query(SentenceTranslation.language_code, SentenceTranslation.translation_text)
        .filter(SentenceTranslation.sentence_id == sentence_id)
        .all()
    )
    by_language = {str(row[0]): str(row[1]) for row in rows if row[1]}
    if "en" in by_language:
        return by_language["en"]
    return next(iter(by_language.values()), "")


@bp.route("/sentence")
def sentence_workflow() -> ResponseReturnValue:
    """Sentence import flow: how to start one, the stages, and what is in flight."""
    spec = SentenceImportSpec()

    # Sentences worth showing: those with staged words still outstanding, plus
    # the most recent imports. Anything fully complete drops off on its own.
    blocked_ids = [
        int(row[0])
        for row in g.db.query(SentenceWordHint.sentence_id)
        .filter(SentenceWordHint.pending_import_id.isnot(None))
        .distinct()
        .limit(50)
        .all()
        if row[0] is not None
    ]
    recent_ids = [
        int(row[0]) for row in g.db.query(Sentence.id).order_by(Sentence.id.desc()).limit(25).all()
    ]

    seen: set[int] = set()
    rows: List[Dict[str, Any]] = []
    for sentence_id in [*blocked_ids, *recent_ids]:
        if sentence_id in seen:
            continue
        seen.add(sentence_id)

        stage = next_incomplete_stage(g.db, sentence_id, spec=spec)
        if stage is None:
            continue

        sentence = g.db.get(Sentence, sentence_id)
        if sentence is None:
            continue

        outstanding = (
            g.db.query(func.count(SentenceWordHint.id))
            .filter(
                SentenceWordHint.sentence_id == sentence_id,
                SentenceWordHint.pending_import_id.isnot(None),
            )
            .scalar()
            or 0
        )
        rows.append(
            {
                "id": sentence_id,
                "guid": sentence.guid,
                "text": _sentence_display_text(g.db, sentence_id),
                "stage": stage.value,
                "stage_title": SENTENCE_STAGE_HELP.get(stage.value, {}).get("title", stage.value),
                "outstanding": int(outstanding),
            }
        )
        if len(rows) >= 25:
            break

    stage_help = [
        {
            "key": stage.value,
            "title": SENTENCE_STAGE_HELP.get(stage.value, {}).get("title", stage.value),
            "test": SENTENCE_STAGE_HELP.get(stage.value, {}).get("test", ""),
            "deferred": stage is SentenceImportStage.IDIOMS,
        }
        for stage in STAGE_ORDER
    ]

    return render_template(
        "workflows/sentence.html",
        stage_help=stage_help,
        in_flight=rows,
        default_spec=spec,
    )


@bp.route("/sentence/start", methods=["POST"])
def start_sentence_import() -> ResponseReturnValue:
    """Split pasted text into sentences and queue an import for each."""
    if current_app.config.get("READONLY", False):
        flash("Cannot modify data in read-only mode", "error")
        return redirect(url_for("workflows.sentence_workflow"))

    text = (request.form.get("text") or "").strip()
    if not text:
        flash("Paste some text to import.", "error")
        return redirect(url_for("workflows.sentence_workflow"))

    document_language = (request.form.get("document_language") or "en").strip().lower()
    source_name = (request.form.get("source_name") or "").strip() or "pasted text"
    auto_promote = bool(request.form.get("auto_promote"))
    annotate = bool(request.form.get("annotate_dependencies"))

    limit_raw = request.form.get("limit", type=int)
    limit = limit_raw if limit_raw and limit_raw > 0 else None

    payload: Dict[str, Any] = {
        "text": text,
        "document_language": document_language,
        "source_name": source_name,
        "auto_promote": auto_promote,
        "annotate_dependencies": annotate,
    }
    if limit is not None:
        payload["limit"] = limit

    try:
        enqueue_task(
            g.db,
            task_type=TaskType.SENTENCES_IMPORT_DOCUMENT,
            target_type=None,
            target_id=None,
            payload=payload,
        )
        g.db.commit()
        flash(
            f"Queued {source_name!r} for import. Sentences appear below as the worker splits them.",
            "success",
        )
    except Exception as exc:
        g.db.rollback()
        flash(f"Could not queue the import: {exc}", "error")

    return redirect(url_for("workflows.sentence_workflow"))


@bp.route("/sentence/<int:sentence_id>")
def sentence_detail(sentence_id: int) -> ResponseReturnValue:
    """One sentence's stages, with its outstanding pending imports."""
    sentence = g.db.get(Sentence, sentence_id)
    if sentence is None:
        flash(f"Sentence {sentence_id} not found", "error")
        return redirect(url_for("workflows.sentence_workflow"))

    spec = SentenceImportSpec()
    steps = _sentence_steps(g.db, sentence_id, spec=spec)

    pending_ids = [
        int(row[0])
        for row in g.db.query(SentenceWordHint.pending_import_id)
        .filter(
            SentenceWordHint.sentence_id == sentence_id,
            SentenceWordHint.pending_import_id.isnot(None),
        )
        .all()
        if row[0] is not None
    ]
    pendings = (
        g.db.query(PendingImport).filter(PendingImport.id.in_(pending_ids)).all()
        if pending_ids
        else []
    )

    translations = (
        g.db.query(SentenceTranslation)
        .filter(SentenceTranslation.sentence_id == sentence_id)
        .order_by(SentenceTranslation.language_code)
        .all()
    )

    return render_template(
        "workflows/sentence_detail.html",
        sentence=sentence,
        display_text=_sentence_display_text(g.db, sentence_id),
        steps=steps,
        pendings=pendings,
        translations=translations,
    )


@bp.route("/sentence/<int:sentence_id>/run", methods=["POST"])
def run_sentence_import(sentence_id: int) -> ResponseReturnValue:
    """Queue the import workflow for one sentence."""
    if current_app.config.get("READONLY", False):
        flash("Cannot modify data in read-only mode", "error")
        return redirect(url_for("workflows.sentence_detail", sentence_id=sentence_id))

    if g.db.get(Sentence, sentence_id) is None:
        flash(f"Sentence {sentence_id} not found", "error")
        return redirect(url_for("workflows.sentence_workflow"))

    auto_promote = bool(request.form.get("auto_promote"))
    try:
        result = enqueue_task(
            g.db,
            task_type=TaskType.SENTENCES_IMPORT,
            target_type="sentence",
            target_id=sentence_id,
            payload={"sentence_id": sentence_id, "auto_promote": auto_promote},
            dedup_key=f"{TaskType.SENTENCES_IMPORT}:{sentence_id}:0",
        )
        g.db.commit()
        # enqueue_task dedups against pending and running tasks, so a second
        # click is harmless -- but say so rather than implying it queued twice.
        if result.created:
            flash(f"Queued import for sentence {sentence_id}.", "success")
        else:
            flash("An import for this sentence is already waiting or running.", "info")
    except Exception as exc:
        g.db.rollback()
        flash(f"Could not queue the import: {exc}", "error")

    return redirect(url_for("workflows.sentence_detail", sentence_id=sentence_id))
