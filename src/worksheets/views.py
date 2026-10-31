"""Server-rendered Barsukas forms for previewing and downloading worksheets."""

from flask import Blueprint, g, render_template, request, send_file
from flask.typing import ResponseReturnValue
from io import BytesIO

from storage.models.schema import Lemma
from worksheets.activities.matching import build_matching
from worksheets.activities.spelling import build_spelling
from worksheets.sources import select_words

bp = Blueprint("worksheets", __name__, url_prefix="/worksheets", template_folder="templates")


@bp.route("/", methods=["GET", "POST"])
def index() -> ResponseReturnValue:
    """Preview a reproducible selection before downloading either PDF."""
    values = request.form if request.method == "POST" else request.args
    settings = {
        "activity": values.get("activity", "missing"),
        "clue_type": values.get("clue_type", "definition"),
        "count": values.get("count", "10"),
        "seed": values.get("seed", "1"),
        "category": values.get("category", ""),
        "page_size": values.get("page_size", "letter"),
    }
    categories = sorted(
        {row[0] for row in g.db.query(Lemma.pos_subtype).distinct().all() if row[0]}
    )
    worksheet = None
    error = None
    status = 200
    if request.method == "POST":
        try:
            count = int(settings["count"])
            seed = int(settings["seed"])
            if not 2 <= count <= 20:
                raise ValueError("Choose between 2 and 20 questions.")
            if settings["activity"] not in {"missing", "scramble", "matching"}:
                raise ValueError("Unknown activity.")
            if settings["clue_type"] not in {"definition", "emoji"}:
                raise ValueError("Unknown clue type.")
            if settings["page_size"] not in {"letter", "a4"}:
                raise ValueError("Unknown paper size.")
            if settings["category"] and settings["category"] not in categories:
                raise ValueError("Unknown category.")
            action = values.get("action", "preview")
            if action not in {"preview", "student", "answers"}:
                raise ValueError("Unknown worksheet action.")
            words = select_words(g.db, count, settings["clue_type"], seed, settings["category"])
            worksheet = (
                build_matching(words, settings["clue_type"], seed)
                if settings["activity"] == "matching"
                else build_spelling(words, settings["activity"], settings["clue_type"], seed)
            )
            if action != "preview":
                from worksheets.rendering.pdf import render_pdf

                pdf = render_pdf(worksheet, settings["page_size"], answers=action == "answers")
                return send_file(
                    BytesIO(pdf),
                    mimetype="application/pdf",
                    as_attachment=True,
                    download_name=f"english-{settings['activity']}-{action}.pdf",
                )
        except ValueError as failure:
            error = str(failure)
            status = 400
    return (
        render_template(
            "worksheets/index.html",
            settings=settings,
            categories=categories,
            worksheet=worksheet,
            error=error,
        ),
        status,
    )
