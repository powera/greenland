#!/usr/bin/python3

"""Walking the emoji catalog, deciding one glyph at a time.

The review is driven from the *emoji* side rather than the lemma side: because
an emoji belongs to at most one lemma, walking the catalog once decides every
glyph exactly once and terminates, whereas walking the ~50k lemmas would ask
"does this word have an emoji?" almost always to answer "no". See
:mod:`words.emoji_catalog`.

Each glyph gets one of three outcomes, all of which are progress and none of
which show it again. Only the assignments reach ``data/release``; the
dismissals are local to the database (see :mod:`words.emoji_catalog`):

``assign``
    A lemma depicts it. The glyph is attached to that lemma.
``no_match``
    Nothing depicts it, or only by a stretch. Dismissed.
``missing_lemma``
    One clear concept, but no word for it yet. Stages a pending import and
    parks the glyph against it; ``delete_pending_import`` attaches the glyph
    when that term is approved, or releases it back to ``undecided`` if the
    term is rejected.
"""

from typing import Dict, List, Optional

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

from barsukas.config import Config
from storage.models.emoji import (
    EMOJI_STATUS_ASSIGNED,
    EMOJI_STATUS_MISSING_LEMMA,
    EMOJI_STATUS_NO_MATCH,
    EMOJI_STATUS_UNDECIDED,
    Emoji,
)
from storage.models.schema import Lemma
from storage.queries.lemma import build_lemma_search_query
from words.emoji import (
    ASSIGNMENT_GUIDANCE,
    EmojiConflictError,
    assign_emoji,
    emoji_values,
    mark_no_match,
    normalize_emoji_input,
    stage_lemma_for_emoji,
    status_counts,
)
from words.emoji_catalog import CatalogEntry, catalog_by_value, load_catalog

bp = Blueprint("emoji_review", __name__, url_prefix="/emoji-review")

# How many lemma candidates to offer per search term.
CANDIDATE_LIMIT = 8


def _decided_values() -> Dict[str, str]:
    """Every glyph that already has a decision, mapped to its status.

    ``undecided`` rows are excluded: a row may exist without a decision having
    been made (``get_or_create_emoji`` creates one on first touch), and those
    glyphs are still owed a review.
    """
    rows = g.db.query(Emoji.value, Emoji.status).filter(Emoji.status != EMOJI_STATUS_UNDECIDED)
    return {value: status for value, status in rows}


def _next_entry(after: Optional[str] = None, at: Optional[str] = None) -> Optional[CatalogEntry]:
    """The catalog entry to review now.

    ``at`` holds the walk on one specific glyph: searching for a lemma, or
    arriving from the overview, must not advance to a different emoji. It wins
    over ``after``, and is honoured even for a glyph that already has a
    decision, so an assignment can be revisited and changed.

    ``after`` resumes the walk past a glyph the reviewer skipped, so skipping
    moves forward instead of handing back the same glyph. A skip records
    nothing, so the glyph reappears on the next pass through the catalog --
    which is the point: it is deferred, not dismissed.
    """
    catalog = load_catalog()

    if at:
        entry = catalog_by_value().get(at)
        if entry is not None:
            return entry

    decided = _decided_values()

    start = 0
    if after:
        for index, entry in enumerate(catalog):
            if entry.value == after:
                start = index + 1
                break

    for entry in catalog[start:]:
        if entry.value not in decided:
            return entry
    # Wrapped past the end: fall back to the first undecided glyph overall, so
    # a skip near the end of the catalog does not report the walk as finished.
    for entry in catalog:
        if entry.value not in decided:
            return entry
    return None


def _candidates(entry: CatalogEntry) -> List[Lemma]:
    """Lemmas that might depict the glyph, seeded from its Unicode name.

    ``search_terms`` turns "DOG FACE" into ["dog face", "dog"]; each is run
    through the ordinary lemma search so the results match what the reviewer
    would get by typing the word themselves. Deduplicated by id, first term
    first, because the full name is the more specific match.
    """
    seen: Dict[int, Lemma] = {}
    for term in entry.search_terms:
        for lemma in build_lemma_search_query(g.db, search=term).limit(CANDIDATE_LIMIT).all():
            seen.setdefault(int(lemma.id), lemma)
    return list(seen.values())


@bp.route("/")
def index() -> ResponseReturnValue:
    """Show the next undecided glyph, with candidate lemmas to attach it to."""
    entry = _next_entry(
        after=request.args.get("after") or None,
        at=request.args.get("at") or None,
    )
    counts = status_counts(g.db)
    catalog_total = len(load_catalog())

    if entry is None:
        return render_template(
            "emoji_review/done.html",
            counts=counts,
            catalog_total=catalog_total,
        )

    search = request.args.get("search", "").strip()
    if search:
        candidates = build_lemma_search_query(g.db, search=search).limit(CANDIDATE_LIMIT).all()
    else:
        candidates = _candidates(entry)

    decided_count = sum(
        counts.get(status, 0)
        for status in (EMOJI_STATUS_ASSIGNED, EMOJI_STATUS_NO_MATCH, EMOJI_STATUS_MISSING_LEMMA)
    )

    # The row for the glyph on screen, when it already has one. A glyph reached
    # from the overview may be decided already, and the page says so rather
    # than presenting it as untouched.
    current = g.db.query(Emoji).filter(Emoji.value == entry.value).one_or_none()

    return render_template(
        "emoji_review/index.html",
        entry=entry,
        candidates=candidates,
        search=search,
        counts=counts,
        decided_count=decided_count,
        catalog_total=catalog_total,
        guidance=ASSIGNMENT_GUIDANCE,
        current=current,
    )


@bp.route("/overview")
def overview() -> ResponseReturnValue:
    """The whole catalog at a glance, every glyph clickable through to review.

    The walk decides glyphs in catalog order and never goes back; this is the
    way to reach one directly -- to change an assignment, to revisit a
    dismissal, or just to see what has been done. Filters narrow by status and
    by Unicode block, which is what makes 1700 glyphs navigable.
    """
    status_filter = request.args.get("status", "").strip()
    block_filter = request.args.get("block", "").strip()

    rows = {row.value: row for row in g.db.query(Emoji)}
    counts = status_counts(g.db)
    catalog = load_catalog()

    # A glyph with no row yet reads as undecided: the catalog is the authority
    # on what exists, and rows are created lazily on first touch.
    entries: List[Dict[str, object]] = []
    for entry in catalog:
        row = rows.get(entry.value)
        status = row.status if row is not None else EMOJI_STATUS_UNDECIDED
        if status_filter and status != status_filter:
            continue
        if block_filter and entry.block != block_filter:
            continue
        lemma = row.lemma if row is not None and status == EMOJI_STATUS_ASSIGNED else None
        entries.append({"entry": entry, "status": status, "lemma": lemma})

    blocks = sorted({entry.block for entry in catalog})

    return render_template(
        "emoji_review/overview.html",
        entries=entries,
        blocks=blocks,
        counts=counts,
        catalog_total=len(catalog),
        status_filter=status_filter,
        block_filter=block_filter,
        statuses=(
            EMOJI_STATUS_ASSIGNED,
            EMOJI_STATUS_UNDECIDED,
            EMOJI_STATUS_NO_MATCH,
            EMOJI_STATUS_MISSING_LEMMA,
        ),
    )


def _after_decision() -> ResponseReturnValue:
    """Where to go once a decision is recorded.

    A reviewer who reached the glyph from the overview is sent back to it,
    keeping their filters; one walking the catalog continues the walk.
    """
    if request.form.get("return_to") == "overview":
        return redirect(
            url_for(
                "emoji_review.overview",
                status=request.form.get("status_filter") or None,
                block=request.form.get("block_filter") or None,
            )
        )
    return redirect(url_for("emoji_review.index"))


@bp.route("/decide", methods=["POST"])
def decide() -> ResponseReturnValue:
    """Record one decision and move to the next glyph.

    An ordinary form submit, so the browser's back button and the flash
    messages behave the way they do everywhere else in Barsukas.
    """
    if current_app.config.get("READONLY", False):
        flash("Cannot review: running in read-only mode", "error")
        return redirect(url_for("emoji_review.index"))

    value = request.form.get("value", "")
    action = request.form.get("action", "")

    if not value or value not in catalog_by_value():
        flash("Unknown emoji.", "error")
        return redirect(url_for("emoji_review.index"))

    # Skip records nothing; the glyph is offered again on a later pass. The
    # cursor moves past it so the next page is a different glyph.
    if action == "skip":
        return redirect(url_for("emoji_review.index", after=value))

    if action == "no_match":
        mark_no_match(g.db, value, notes=request.form.get("notes", "").strip() or None)
        g.db.commit()
        flash(f"Dismissed {value}.", "success")
        return _after_decision()

    if action == "assign":
        lemma_id = request.form.get("lemma_id", "").strip()
        if not lemma_id.isdigit():
            flash("Pick a lemma to attach the emoji to.", "error")
            return redirect(url_for("emoji_review.index"))

        lemma = g.db.query(Lemma).get(int(lemma_id))
        if lemma is None:
            flash("That lemma no longer exists.", "error")
            return redirect(url_for("emoji_review.index"))

        # Assignment replaces the lemma's whole emoji list, so the glyphs it
        # already holds are carried through and the new one appended -- an
        # emoji review must not silently drop an emoji set on the edit page.
        existing = emoji_values(lemma)
        if value not in existing:
            existing.append(value)

        try:
            assign_emoji(g.db, lemma, normalize_emoji_input(" ".join(existing)))
        except EmojiConflictError as conflict:
            g.db.rollback()
            flash(str(conflict), "error")
            return redirect(url_for("emoji_review.index"))

        g.db.commit()
        flash(f"Attached {value} to {lemma.lemma_text}.", "success")
        return _after_decision()

    if action == "missing_lemma":
        word = request.form.get("english_word", "").strip()
        definition = request.form.get("definition", "").strip()
        if not word or not definition:
            flash("A staged word needs both a word and a definition.", "error")
            return redirect(url_for("emoji_review.index"))

        stage_lemma_for_emoji(
            g.db,
            value,
            english_word=word,
            definition=definition,
            source=Config.OPERATION_LOG_SOURCE,
            notes=request.form.get("notes", "").strip() or None,
        )
        g.db.commit()
        flash(
            f"Staged '{word}' for import; {value} attaches when it is approved.",
            "success",
        )
        return _after_decision()

    flash("Unknown action.", "error")
    return redirect(url_for("emoji_review.index"))
