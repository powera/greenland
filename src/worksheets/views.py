"""Server-rendered Barsukas forms for previewing and downloading worksheets."""

from io import BytesIO
from typing import Optional

from flask import Blueprint, g, render_template, request, send_file
from flask.typing import ResponseReturnValue
from sqlalchemy.orm import Session

from storage.models.schema import Lemma
from worksheets.activities.families import build_families
from worksheets.activities.matching import build_matching
from worksheets.activities.spelling import build_spelling
from worksheets.activities.word_forms import build_word_forms
from worksheets.models import Worksheet
from worksheets.sources import (
    CONTENT_FLAGS,
    CONTENT_POLICIES,
    FORM_KINDS,
    YLE_TIERS,
    SelectionFilters,
    select_families,
    select_rhyme_pairs,
    select_synonym_pairs,
    select_word_forms,
    select_words,
)

bp = Blueprint("worksheets", __name__, url_prefix="/worksheets", template_folder="templates")

# (value, label) in display order; grouped in the template by the first element.
ACTIVITY_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "Spelling and meaning",
        (
            ("missing", "Spelling: missing letters"),
            ("scramble", "Spelling: scramble"),
            ("matching", "Match words to clues"),
        ),
    ),
    (
        "Word forms",
        (
            ("plural", "Plurals (nouns)"),
            ("past", "Past tense (verbs)"),
            ("past_participle", "Past participles (verbs)"),
            ("principal_parts", "Past tense and past participle (verbs)"),
            ("comparison", "Comparing: -er/-est, more/most (adjectives)"),
        ),
    ),
    (
        "Word relationships",
        (
            ("families", "Word families"),
            ("synonyms", "Match synonyms"),
            ("rhymes", "Match rhyming words"),
        ),
    ),
)
ACTIVITIES: frozenset[str] = frozenset(
    value for _, options in ACTIVITY_GROUPS for value, _ in options
)


def _parse_rank(raw: str) -> Optional[int]:
    if not raw.strip():
        return None
    rank = int(raw)
    if rank < 1:
        raise ValueError("Maximum frequency rank must be positive.")
    return rank


def build_worksheet(
    session: Session,
    activity: str,
    count: int,
    seed: int,
    clue_type: str,
    filters: SelectionFilters,
    irregular_only: bool,
) -> Worksheet:
    """Select content for an activity and build its renderer-independent worksheet."""
    if activity in FORM_KINDS:
        entries = select_word_forms(session, count, activity, seed, filters, irregular_only)
        return build_word_forms(entries, activity)
    if activity == "families":
        return build_families(select_families(session, count, seed, filters), seed)
    if activity == "synonyms":
        return build_matching(select_synonym_pairs(session, count, seed, filters), "synonym", seed)
    if activity == "rhymes":
        return build_matching(select_rhyme_pairs(session, count, seed, filters), "rhyme", seed)
    words = select_words(session, count, clue_type, seed, filters)
    if activity == "matching":
        return build_matching(words, clue_type, seed)
    return build_spelling(words, activity, clue_type, seed)


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
        "yle_tier": values.get("yle_tier", ""),
        "max_rank": values.get("max_rank", ""),
        "irregular_only": values.get("irregular_only", ""),
        "content_policy": values.get("content_policy", "exclude_flagged"),
        "page_size": values.get("page_size", "letter"),
    }
    allowed_flags = values.getlist("allowed_flags")
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
            if settings["activity"] not in ACTIVITIES:
                raise ValueError("Unknown activity.")
            if settings["clue_type"] not in {"definition", "emoji"}:
                raise ValueError("Unknown clue type.")
            if settings["page_size"] not in {"letter", "a4"}:
                raise ValueError("Unknown paper size.")
            if settings["category"] and settings["category"] not in categories:
                raise ValueError("Unknown category.")
            if settings["yle_tier"] and settings["yle_tier"] not in YLE_TIERS:
                raise ValueError("Unknown Cambridge YLE tier.")
            action = values.get("action", "preview")
            if action not in {"preview", "student", "answers"}:
                raise ValueError("Unknown worksheet action.")
            if settings["content_policy"] not in CONTENT_POLICIES:
                raise ValueError("Unknown content policy.")
            if not set(allowed_flags) <= set(CONTENT_FLAGS):
                raise ValueError("Unknown content flag.")
            filters = SelectionFilters(
                settings["category"],
                settings["yle_tier"],
                _parse_rank(settings["max_rank"]),
                settings["content_policy"],
                frozenset(allowed_flags),
            )
            worksheet = build_worksheet(
                g.db,
                settings["activity"],
                count,
                seed,
                settings["clue_type"],
                filters,
                bool(settings["irregular_only"]),
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
            activity_groups=ACTIVITY_GROUPS,
            yle_tiers=YLE_TIERS,
            content_flags=CONTENT_FLAGS,
            allowed_flags=allowed_flags,
            worksheet=worksheet,
            error=error,
        ),
        status,
    )
