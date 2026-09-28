#!/usr/bin/python3

"""Routes for curriculum level metadata: names, translations, CEFR, prerequisites.

Every level that has words is listed, named or not, because the point of the
page is to find the unnamed ones. Naming and translating by LLM are queued as
workqueue tasks (``levels.name.generate`` / ``levels.name.translate``) rather
than run in the request; their results appear here once the worker has run.
"""

import json
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

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

import constants
from barsukas.config import Config
from barsukas.helpers.flash_helpers import log_and_flash_error
from storage.crud.curriculum_level import (
    delete_curriculum_level,
    get_curriculum_level,
    list_curriculum_levels,
    set_curriculum_level,
)
from storage.models.curriculum_level import CEFR_LEVELS
from storage.models.schema import Lemma
from storage.translation_helpers import get_supported_languages
from words.level_naming import default_translation_languages, level_word_counts, level_words
from workqueue.task_queue import TaskRequest, TaskType, enqueue_task, enqueue_tasks

bp = Blueprint("levels", __name__, url_prefix="/levels")

# Words previewed per row on the list page.
_SAMPLE_WORDS = 8


def _band(level: int) -> str:
    """Which curriculum band a level number falls in, for display."""
    if level <= constants.CORE_DIFFICULTY_LEVEL_MAX:
        return "core"
    if level <= constants.GENERAL_DIFFICULTY_LEVEL_MAX:
        return "named"
    return "topic"


def _readonly_redirect(target: str) -> Optional[ResponseReturnValue]:
    """Flash and redirect when Barsukas is read-only; None otherwise."""
    if current_app.config.get("READONLY", False):
        flash("Not available: running in read-only mode", "error")
        return redirect(target)
    return None


def _sample_words(level_numbers: List[int]) -> Dict[int, List[str]]:
    """The most frequent few words at each level, from one query."""
    rows = (
        g.db.query(Lemma.difficulty_level, Lemma.lemma_text)
        .filter(Lemma.difficulty_level.in_(level_numbers))
        .order_by(Lemma.frequency_rank.is_(None), Lemma.frequency_rank, Lemma.lemma_text)
        .all()
    )
    samples: Dict[int, List[str]] = defaultdict(list)
    for level, text in rows:
        if len(samples[level]) < _SAMPLE_WORDS:
            samples[level].append(text)
    return samples


def _enqueue_name(level: int, overwrite: bool, translate: bool) -> TaskRequest:
    """The task request that names (and optionally translates) one level."""
    return TaskRequest(
        task_type=TaskType.LEVELS_NAME_GENERATE,
        target_type="curriculum_level",
        target_id=level,
        payload={
            "schema_version": 1,
            "source_component": "barsukas.levels",
            "level": level,
            "overwrite": overwrite,
            "translate": translate,
        },
        dedup_key=f"{TaskType.LEVELS_NAME_GENERATE}:{level}",
    )


def _enqueue_translate(level: int, overwrite: bool) -> TaskRequest:
    """The task request that translates one level's name."""
    return TaskRequest(
        task_type=TaskType.LEVELS_NAME_TRANSLATE,
        target_type="curriculum_level",
        target_id=level,
        payload={
            "schema_version": 1,
            "source_component": "barsukas.levels",
            "level": level,
            "overwrite": overwrite,
        },
        dedup_key=f"{TaskType.LEVELS_NAME_TRANSLATE}:{level}",
    )


def _list_rows() -> Tuple[List[Dict[str, Any]], List[str]]:
    """One row per level that has words or metadata, plus the translation languages."""
    counts = level_word_counts(g.db)
    metadata = {row.level: row for row in list_curriculum_levels(g.db)}
    numbers = sorted(set(counts) | set(metadata))
    samples = _sample_words(numbers)
    languages = default_translation_languages()

    rows: List[Dict[str, Any]] = []
    for number in numbers:
        meta = metadata.get(number)
        translations = meta.get_translations() if meta else {}
        rows.append(
            {
                "level": number,
                "band": _band(number),
                "word_count": counts.get(number, 0),
                "sample": samples.get(number, []),
                "meta": meta,
                "missing_languages": [code for code in languages if code not in translations],
            }
        )
    return rows, languages


@bp.route("/")
def list_levels() -> ResponseReturnValue:
    """Every level with words or metadata; filterable to unnamed or by band."""
    rows, languages = _list_rows()
    show = request.args.get("show", "all")
    band = request.args.get("band", "")
    if show == "unnamed":
        rows = [row for row in rows if row["meta"] is None]
    elif show == "untranslated":
        rows = [row for row in rows if row["meta"] is not None and row["missing_languages"]]
    if band:
        rows = [row for row in rows if row["band"] == band]

    return render_template(
        "levels/list.html",
        rows=rows,
        show=show,
        band=band,
        languages=languages,
        unnamed_levels=[row["level"] for row in rows if row["meta"] is None and row["word_count"]],
        untranslated_levels=[
            row["level"] for row in rows if row["meta"] is not None and row["missing_languages"]
        ],
    )


@bp.route("/<int:level>")
def edit_level(level: int) -> ResponseReturnValue:
    """Edit one level's name, translations, CEFR, prerequisites and extras."""
    meta = get_curriculum_level(g.db, level)
    words = level_words(g.db, level)
    if meta is None and not words:
        flash(f"Level {level} has no words and no metadata", "warning")

    translations = meta.get_translations() if meta else {}
    languages = default_translation_languages()
    # Languages with a stored name outside the default set still get a field,
    # so saving the form cannot silently drop them.
    languages += sorted(code for code in translations if code not in languages)

    return render_template(
        "levels/edit.html",
        level=level,
        band=_band(level),
        meta=meta,
        words=words,
        translations=translations,
        languages=languages,
        language_names=get_supported_languages(),
        cefr_levels=CEFR_LEVELS,
        extra_json=json.dumps(meta.get_extra(), ensure_ascii=False, indent=2) if meta else "",
        prerequisites_text=", ".join(str(p) for p in meta.get_prerequisites()) if meta else "",
    )


@bp.route("/<int:level>", methods=["POST"])
def save_level(level: int) -> ResponseReturnValue:
    """Save the edit form."""
    target = url_for("levels.edit_level", level=level)
    blocked = _readonly_redirect(target)
    if blocked is not None:
        return blocked

    form = request.form
    try:
        prerequisites = [
            int(part) for part in form.get("prerequisites", "").replace(",", " ").split()
        ]
    except ValueError:
        flash("Prerequisites must be level numbers separated by commas", "error")
        return redirect(target)

    extra_text = form.get("extra", "").strip()
    try:
        extra = json.loads(extra_text) if extra_text else None
    except json.JSONDecodeError as error:
        flash(f"Extra is not valid JSON: {error}", "error")
        return redirect(target)
    if extra is not None and not isinstance(extra, dict):
        flash("Extra must be a JSON object", "error")
        return redirect(target)

    translations = {
        key[len("translation_") :]: value
        for key, value in form.items()
        if key.startswith("translation_")
    }

    try:
        set_curriculum_level(
            g.db,
            level,
            name=form.get("name", ""),
            cefr=form.get("cefr"),
            prerequisites=prerequisites,
            extra=extra,
            notes=form.get("notes"),
            translations=translations,
            source=Config.OPERATION_LOG_SOURCE,
        )
        g.db.commit()
    except ValueError as error:
        g.db.rollback()
        flash(str(error), "error")
        return redirect(target)

    flash(f"Saved level {level}", "success")
    return redirect(target)


@bp.route("/<int:level>/delete", methods=["POST"])
def delete_level(level: int) -> ResponseReturnValue:
    """Delete a level's metadata. Its words are untouched."""
    blocked = _readonly_redirect(url_for("levels.edit_level", level=level))
    if blocked is not None:
        return blocked
    if delete_curriculum_level(g.db, level, source=Config.OPERATION_LOG_SOURCE):
        g.db.commit()
        flash(f"Deleted the name and metadata for level {level}", "success")
    else:
        flash(f"Level {level} had no metadata", "warning")
    return redirect(url_for("levels.list_levels"))


@bp.route("/<int:level>/generate", methods=["POST"])
def generate_name(level: int) -> ResponseReturnValue:
    """Queue an LLM name for one level."""
    target = url_for("levels.edit_level", level=level)
    blocked = _readonly_redirect(target)
    if blocked is not None:
        return blocked
    request_ = _enqueue_name(
        level,
        overwrite=request.form.get("overwrite") == "on",
        translate=request.form.get("translate") == "on",
    )
    try:
        result = enqueue_task(
            g.db,
            task_type=request_.task_type,
            target_type=request_.target_type,
            target_id=request_.target_id,
            payload=request_.payload,
            dedup_key=request_.dedup_key,
        )
        if result.created:
            flash("Queued name generation. Reload this page once the task has run.", "info")
        else:
            flash("Name generation is already queued for this level.", "warning")
    except Exception as error:
        log_and_flash_error(error, "queueing level name generation")
    return redirect(target)


@bp.route("/<int:level>/translate", methods=["POST"])
def translate_name(level: int) -> ResponseReturnValue:
    """Queue LLM translations of one level's name."""
    target = url_for("levels.edit_level", level=level)
    blocked = _readonly_redirect(target)
    if blocked is not None:
        return blocked
    if get_curriculum_level(g.db, level) is None:
        flash("Give the level an English name before translating it.", "warning")
        return redirect(target)
    request_ = _enqueue_translate(level, overwrite=request.form.get("overwrite") == "on")
    try:
        result = enqueue_task(
            g.db,
            task_type=request_.task_type,
            target_type=request_.target_type,
            target_id=request_.target_id,
            payload=request_.payload,
            dedup_key=request_.dedup_key,
        )
        if result.created:
            flash("Queued translation. Reload this page once the task has run.", "info")
        else:
            flash("Translation is already queued for this level.", "warning")
    except Exception as error:
        log_and_flash_error(error, "queueing level name translation")
    return redirect(target)


def _posted_levels(field: str) -> List[int]:
    """Level numbers posted by a whole-list form, as rendered on the page."""
    return [int(value) for value in request.form.getlist(field) if value.strip().isdigit()]


@bp.route("/generate-missing", methods=["POST"])
def generate_missing() -> ResponseReturnValue:
    """Queue naming (and translation) for every unnamed level the page showed."""
    target = url_for("levels.list_levels", **request.args)
    blocked = _readonly_redirect(target)
    if blocked is not None:
        return blocked
    levels = [
        level for level in _posted_levels("level") if get_curriculum_level(g.db, level) is None
    ]
    summary = enqueue_tasks(
        g.db, [_enqueue_name(level, overwrite=False, translate=True) for level in levels]
    )
    flash(
        f"Queued naming for {summary['enqueued']} level(s); "
        f"{summary['skipped']} already queued.",
        "info",
    )
    return redirect(target)


@bp.route("/translate-missing", methods=["POST"])
def translate_missing() -> ResponseReturnValue:
    """Queue translation of missing languages for every named level the page showed."""
    target = url_for("levels.list_levels", **request.args)
    blocked = _readonly_redirect(target)
    if blocked is not None:
        return blocked
    levels = [
        level for level in _posted_levels("level") if get_curriculum_level(g.db, level) is not None
    ]
    summary = enqueue_tasks(g.db, [_enqueue_translate(level, overwrite=False) for level in levels])
    flash(
        f"Queued translation for {summary['enqueued']} level(s); "
        f"{summary['skipped']} already queued.",
        "info",
    )
    return redirect(target)
