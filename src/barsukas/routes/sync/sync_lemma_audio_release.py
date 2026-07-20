#!/usr/bin/python3

"""Routes for syncing lemma audio between release files and the DB.

Lemma audio metadata (not the mp3 bytes) lives beside the lemma release records::

    data/release/lemmas/{pos_dir}/{pos_subtype}/audio.jsonl

Each line is one GUID with an ``audio`` array of per-(language, voice) records
carrying the S3 URLs and review status. Only audio in an approved status is
exported. Lemma audio is a bulk mirror keyed on ``(guid, language_code,
voice_name, grammatical_form)``, so instead of a per-word editing workflow this
page shows an itemized diff and lets a sync be scoped: to the whole tree, to
individual ``{pos_dir}/{pos_subtype}`` categories, or (on import) to hand-picked
rows. Sentence audio is synced separately via ``sync_sentence_release``.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

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

from storage.migrate import (
    LemmaAudioCategory,
    LemmaAudioKey,
    export_lemma_audio_release_from_session,
    import_lemma_audio_release_into_session,
    parse_lemma_audio_category_slug,
    parse_lemma_audio_key_token,
    summarize_lemma_audio_release_diff,
)

if TYPE_CHECKING:
    from barsukas.app import BarsukasFlask

logger = logging.getLogger(__name__)

bp = Blueprint("sync_lemma_audio_release", __name__, url_prefix="/sync/lemma-audio")

DEFAULT_RELEASE_DIR = (
    Path(__file__).parent.parent.parent.parent.parent / "data" / "release" / "lemmas"
)


def _get_release_dir() -> Path:
    return DEFAULT_RELEASE_DIR


def _selected_categories(form_key: str = "category") -> Optional[List[LemmaAudioCategory]]:
    """Parse the submitted category slugs, or None when the whole tree is meant.

    Unparseable slugs are dropped rather than silently widening the scope; an
    all-invalid selection yields an empty list, which the callers treat as
    "nothing to do" instead of "everything".
    """
    slugs = request.form.getlist(form_key)
    if not slugs:
        return None
    categories: List[LemmaAudioCategory] = []
    for slug in slugs:
        category = parse_lemma_audio_category_slug(slug)
        if category is None:
            logger.warning(f"Ignoring malformed lemma-audio category slug: {slug!r}")
            continue
        categories.append(category)
    return categories


def _selected_keys() -> Optional[List[LemmaAudioKey]]:
    """Parse the submitted per-row keys, or None when no row selection was made."""
    tokens = request.form.getlist("key")
    if not tokens:
        return None
    keys: List[LemmaAudioKey] = []
    for token in tokens:
        key = parse_lemma_audio_key_token(token)
        if key is None:
            logger.warning(f"Ignoring malformed lemma-audio key token: {token!r}")
            continue
        keys.append(key)
    return keys


@bp.route("/")
def index() -> ResponseReturnValue:
    """Landing page: itemized diff plus scoped Import / Export actions."""
    release_dir = _get_release_dir()
    scope = _get_scope_from_query()
    diff = summarize_lemma_audio_release_diff(g.db, str(release_dir), categories=scope)
    return render_template(
        "sync_lemma_audio_release/index.html",
        release_dir=str(release_dir),
        diff=diff,
        scope_slug=request.args.get("category", ""),
    )


def _get_scope_from_query() -> Optional[List[LemmaAudioCategory]]:
    """Optional ``?category=nouns/food`` filter for narrowing the diff view."""
    slug = request.args.get("category", "").strip()
    if not slug:
        return None
    category = parse_lemma_audio_category_slug(slug)
    if category is None:
        return None
    return [category]


@bp.route("/import", methods=["POST"])
def import_release() -> ResponseReturnValue:
    """Sync approved lemma audio from the release files into the database."""
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_lemma_audio_release.index"))

    release_dir = _get_release_dir()
    prune = request.form.get("prune") == "on"
    categories = _selected_categories()
    keys = _selected_keys()

    if categories is not None and not categories:
        flash("No valid categories selected; nothing was imported.", "error")
        return redirect(url_for("sync_lemma_audio_release.index"))
    if keys is not None and not keys:
        flash("No valid rows selected; nothing was imported.", "error")
        return redirect(url_for("sync_lemma_audio_release.index"))

    try:
        stats = import_lemma_audio_release_into_session(
            g.db, str(release_dir), prune=prune, categories=categories, keys=keys
        )
    except Exception as e:  # noqa: BLE001 - surface the failure to the user
        g.db.rollback()
        logger.error(f"Lemma audio import failed: {e}")
        flash(f"Import failed: {e}", "error")
        return redirect(url_for("sync_lemma_audio_release.index"))

    message = (
        f"Imported {_scope_label(categories, keys)}: {stats.added} added, "
        f"{stats.updated} updated, {stats.unchanged} unchanged"
    )
    if prune:
        message += f", {stats.pruned} pruned"
    flash(message + ".", "success")
    return redirect(url_for("sync_lemma_audio_release.index"))


def _scope_label(
    categories: Optional[List[LemmaAudioCategory]], keys: Optional[List[LemmaAudioKey]] = None
) -> str:
    """Human-readable description of what a sync was scoped to, for flash messages."""
    if keys is not None:
        return f"{len(keys)} selected row(s)"
    if categories is None:
        return "all lemma audio"
    if len(categories) == 1:
        from storage.migrate import lemma_audio_category_slug

        return lemma_audio_category_slug(categories[0])
    return f"{len(categories)} categories"


@bp.route("/export", methods=["POST"])
def export_release() -> ResponseReturnValue:
    """Export approved lemma audio from the database to the release files."""
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_lemma_audio_release.index"))

    release_dir = _get_release_dir()
    categories = _selected_categories()

    if categories is not None and not categories:
        flash("No valid categories selected; nothing was exported.", "error")
        return redirect(url_for("sync_lemma_audio_release.index"))

    try:
        stats = export_lemma_audio_release_from_session(
            g.db, str(release_dir), categories=categories
        )
    except Exception as e:  # noqa: BLE001 - surface the failure to the user
        logger.error(f"Lemma audio export failed: {e}")
        flash(f"Export failed: {e}", "error")
        return redirect(url_for("sync_lemma_audio_release.index"))

    flash(
        f"Exported {_scope_label(categories)}: {stats.audio_rows} audio row(s) across "
        f"{stats.guids} GUID(s) in {stats.categories} categor"
        f"{'y' if stats.categories == 1 else 'ies'}.",
        "success",
    )
    return redirect(url_for("sync_lemma_audio_release.index"))
