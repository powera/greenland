#!/usr/bin/python3

"""Approving or rejecting the staged rows of the POS subtype review.

Reads the TSVs that ``src/quality/subtype_review.py`` writes, one per subtype,
from the working directory ``subtype_review/``.  Submitting a subtype applies
the approved rows (each move logs its own ``type_subtype_change``), writes one
summary operation log carrying the reviewer's notes, deletes the TSV and its
run log, and appends the subtype to ``subtype_review/complete.txt``, which
``run_nouns.sh`` reads to skip it on a rerun.  Rejected rows are not recorded
anywhere else: clearing the TSV is the rejection.  Rows marked "ignore" are
written back to the TSV unchanged, and the subtype is not marked complete
while any remain.

A slice page (``/<subtype>/to/<target>``) applies or rejects the checked moves
from one subtype to one target, and removes just those rows from the TSV; the
other rows stay in the file untouched.  A word page (``/<subtype>/word/<guid>``)
moves one row's sense to any subtype, or rejects it.  A TSV emptied this way is
still marked complete through the subtype page.
"""

import csv
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

from flask import Blueprint, abort, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from barsukas.helpers.flash_helpers import flash_and_log
from quality.subtype_review import APPLY_YES, apply_rows, describe_subtype
from storage.crud.operation_log import log_operation
from storage.models.guid_prefixes import classifiable_subtypes, subtype_groups

bp = Blueprint("subtype_review", __name__, url_prefix="/subtype-review")

REVIEW_ROOT = Path(__file__).resolve().parents[4] / "subtype_review"
TSV_DIR = REVIEW_ROOT / "nouns-max499"
COMPLETE_FILE = REVIEW_ROOT / "complete.txt"
POS_TYPE = "noun"


def _read_table(tsv_path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    """The column names and every row of a review TSV, approved or not."""
    with tsv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def _read_rows(tsv_path: Path) -> List[Dict[str, str]]:
    """Every row of a review TSV, approved or not."""
    return _read_table(tsv_path)[1]


def _write_rows(tsv_path: Path, fieldnames: List[str], rows: List[Dict[str, str]]) -> None:
    """Rewrite a review TSV with ``rows``, keeping its column order."""
    with tsv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


#: Second-opinion verdicts that leave the row for a person: the review page
#: pre-selects "ignore" for them rather than approve or reject.
HOLD_VERDICTS = frozenset({"no_fit", "ambiguous", "gestalt"})


def _move_target(row: Dict[str, str]) -> str:
    """Where approving ``row`` moves it: the second opinion's subtype when it
    named a different one ("other"), else the first pass's suggestion."""
    if row.get("second_verdict") == "other" and row.get("second_subtype"):
        return row["second_subtype"]
    return row.get("suggested_subtype", "")


def _as_move(row: Dict[str, str]) -> Dict[str, str]:
    """``row`` as :func:`apply_rows` should see it, aimed at :func:`_move_target`."""
    return {**row, "suggested_subtype": _move_target(row)}


def _is_malformed(row: Dict[str, str]) -> bool:
    """Whether ``row`` is a move with no destination: the first pass named the
    current subtype (or no real one), and the parser blanked the suggestion."""
    return row.get("verdict") == "move" and not row.get("suggested_subtype")


def _is_slice_row(row: Dict[str, str], target: str) -> bool:
    """Whether ``row`` is a move to ``target``."""
    return row.get("verdict") == "move" and bool(target) and _move_target(row) == target


def _tsv_path(subtype: str) -> Path:
    """The TSV for ``subtype``, or 404 if there is none (guards the URL part)."""
    available = {path.stem: path for path in TSV_DIR.glob("*.tsv")}
    if subtype not in available:
        abort(404)
    return available[subtype]


def _mark_complete(subtype: str, notes: str) -> None:
    """Append ``subtype`` to the complete list, with the notes as a comment."""
    comment = " ".join(notes.split())
    line = f"{subtype}  # {comment}" if comment else subtype
    with COMPLETE_FILE.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


@bp.route("/")
def index() -> ResponseReturnValue:
    """Every subtype with a TSV still waiting for review, by supertype, most flags
    first, and every target subtype with the moves heading into it."""
    group_of = _group_of()
    groups: Dict[str, Dict[str, Any]] = {}
    incoming: Counter[str] = Counter()
    for tsv_path in TSV_DIR.glob("*.tsv"):
        rows = _read_rows(tsv_path)
        group = group_of.get(tsv_path.stem, "Ungrouped")
        entry = groups.setdefault(group, {"group": group, "count": 0, "subtypes": []})
        entry["count"] += len(rows)
        entry["subtypes"].append({"subtype": tsv_path.stem, "count": len(rows)})
        incoming.update(
            _move_target(row) for row in rows if row.get("verdict") == "move" and _move_target(row)
        )
    pending: List[Dict[str, Any]] = sorted(
        groups.values(), key=lambda item: (-item["count"], item["group"])
    )
    for entry in pending:
        entry["subtypes"].sort(key=lambda item: (-item["count"], item["subtype"]))
    complete_count = 0
    if COMPLETE_FILE.exists():
        complete_count = sum(
            1
            for line in COMPLETE_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    return render_template(
        "subtype_review/index.html",
        pending=pending,
        incoming=sorted(incoming.items(), key=lambda item: (-item[1], item[0])),
        complete_count=complete_count,
        tsv_dir=TSV_DIR,
    )


def _incoming_rows(target: str) -> List[Dict[str, str]]:
    """Every move into ``target`` across all the TSVs, by source subtype then word."""
    rows = [
        row
        for tsv_path in sorted(TSV_DIR.glob("*.tsv"))
        for row in _read_rows(tsv_path)
        if _is_slice_row(row, target)
    ]
    return sorted(rows, key=lambda row: (row.get("current_subtype", ""), row.get("word", "")))


@bp.route("/into/<target>")
def review_incoming(target: str) -> ResponseReturnValue:
    """Every move into ``target``, from any subtype, to apply or reject together."""
    if target not in classifiable_subtypes(POS_TYPE):
        abort(404)
    return render_template(
        "subtype_review/into.html",
        target=target,
        target_description=describe_subtype(POS_TYPE, target),
        rows=_incoming_rows(target),
    )


@bp.route("/into/<target>", methods=["POST"])
def submit_incoming(target: str) -> ResponseReturnValue:
    """Apply or reject the checked moves into ``target``; drop them from their TSVs.

    Unchecked rows, and a checked row that cannot be applied, stay in their TSV.
    """
    if target not in classifiable_subtypes(POS_TYPE):
        abort(404)
    _act_on_checked(
        f"moves into {target}", _incoming_rows(target), {"scope": "into", "target": target}
    )
    if _incoming_rows(target):
        return redirect(url_for("subtype_review.review_incoming", target=target))
    return redirect(url_for("subtype_review.index"))


def _act_on_checked(label: str, candidates: List[Dict[str, str]], scope: Dict[str, str]) -> None:
    """Apply or reject the checked rows among ``candidates``, from the posted form.

    ``candidates`` are the rows the page showed, possibly from several TSVs;
    each acted-on row is removed from its own TSV (its ``current_subtype``).
    Unchecked rows, and a checked row that cannot be applied, stay put.  An
    apply writes one operation log with the notes and ``scope``; a reject is
    recorded only by the row leaving its TSV.  Flashes the outcome.
    """
    action = request.form.get("action")
    notes = (request.form.get("notes") or "").strip()
    picked_guids = set(request.form.getlist("pick"))
    picked = [row for row in candidates if row.get("guid") in picked_guids]

    if str(len(candidates)) != request.form.get("expected_count"):
        flash_and_log(
            f"{label} changed since the page was loaded ({len(candidates)} rows now); "
            "nothing done",
            "error",
        )
        return
    if not picked:
        flash_and_log(f"{label}: no rows were checked; nothing done", "warning")
        return

    if action == "apply":
        result = apply_rows(g.db, [_as_move(row) for row in picked])
        log_operation(
            g.db,
            operation_type="subtype_review_checked_applied",
            source="barsukas-subtype-review",
            entity_type="pos_subtype",
            details={
                "pos_type": POS_TYPE,
                **scope,
                "notes": notes,
                "moved": [
                    {
                        "word": move.word,
                        "old_subtype": move.old_subtype,
                        "new_subtype": move.new_subtype,
                        "old_guid": move.old_guid,
                        "new_guid": move.new_guid,
                    }
                    for move in result.applied
                ],
                "skipped": list(result.skipped),
            },
        )
        g.db.commit()
        done_guids = {move.old_guid for move in result.applied}
        flash_and_log(f"{label}: moved {len(result.applied)}", "success")
        if result.skipped:
            flash_and_log(
                f"{len(result.skipped)} row(s) could not be applied and stay in their TSV: "
                + "; ".join(result.skipped),
                "warning",
            )
    elif action == "reject":
        done_guids = {row["guid"] for row in picked}
        flash_and_log(f"{label}: rejected {len(picked)}", "success")
    else:
        abort(400)

    for source in sorted({row.get("current_subtype", "") for row in picked}):
        tsv_path = _tsv_path(source)
        fieldnames, rows = _read_table(tsv_path)
        _write_rows(tsv_path, fieldnames, [row for row in rows if row["guid"] not in done_guids])


def _group_of() -> Dict[str, str]:
    """Each noun subtype's supertype, as the Word Categories page groups them."""
    return {
        subtype: group
        for group, subtypes in subtype_groups(POS_TYPE).items()
        for subtype in subtypes
    }


def _group_rows(group: str) -> List[Dict[str, str]]:
    """Every flagged row whose current subtype is in ``group``.

    Moves that stay inside the group come first, then moves out of it, then
    flags with no move; each part by target, then word.
    """
    group_of = _group_of()
    rows = [
        row
        for tsv_path in sorted(TSV_DIR.glob("*.tsv"))
        if group_of.get(tsv_path.stem) == group
        for row in _read_rows(tsv_path)
    ]
    for row in rows:
        target = _move_target(row)
        row["target"] = target
        if row.get("verdict") != "move" or not target:
            row["placement"] = "no move"
        elif group_of.get(target) == group:
            row["placement"] = "within"
        else:
            row["placement"] = "out"
    order = {"within": 0, "out": 1, "no move": 2}
    return sorted(
        rows,
        key=lambda row: (
            order[row["placement"]],
            row["target"],
            row.get("word", ""),
        ),
    )


@bp.route("/group/<group>")
def review_group(group: str) -> ResponseReturnValue:
    """Every flagged row from one supertype's subtypes, to apply or reject together."""
    if group not in subtype_groups(POS_TYPE):
        abort(404)
    rows = _group_rows(group)
    return render_template(
        "subtype_review/group.html",
        group=group,
        rows=rows,
        movable_count=sum(1 for row in rows if row["placement"] != "no move"),
    )


@bp.route("/group/<group>", methods=["POST"])
def submit_group(group: str) -> ResponseReturnValue:
    """Apply or reject the checked moves of one supertype; drop them from their TSVs."""
    if group not in subtype_groups(POS_TYPE):
        abort(404)
    movable = [row for row in _group_rows(group) if row["placement"] != "no move"]
    _act_on_checked(group, movable, {"scope": "group", "group": group})
    return redirect(url_for("subtype_review.review_group", group=group))


@bp.route("/<subtype>")
def review(subtype: str) -> ResponseReturnValue:
    """The flagged rows of one subtype, each with an approve/reject choice."""
    rows = _read_rows(_tsv_path(subtype))
    for row in rows:
        row["target"] = _move_target(row)
        second = row.get("second_verdict", "")
        row["malformed"] = "yes" if _is_malformed(row) else ""
        if row["malformed"]:
            row["default_decision"] = ""
        elif second in HOLD_VERDICTS:
            row["default_decision"] = "ignore"
        elif (
            row.get("verdict") == "move"
            and second != "keep"
            and (row.get("apply") or "").strip().casefold() in APPLY_YES
        ):
            row["default_decision"] = "approve"
        else:
            row["default_decision"] = "reject"
    targets = Counter(
        row["target"] for row in rows if row.get("verdict") == "move" and row["target"]
    )
    return render_template(
        "subtype_review/review.html",
        subtype=subtype,
        description=describe_subtype(POS_TYPE, subtype),
        rows=rows,
        targets=sorted(targets.items(), key=lambda item: (-item[1], item[0])),
    )


@bp.route("/<subtype>/to/<target>")
def review_slice(subtype: str, target: str) -> ResponseReturnValue:
    """Every move from ``subtype`` to ``target``, to apply or reject together."""
    rows = [row for row in _read_rows(_tsv_path(subtype)) if _is_slice_row(row, target)]
    return render_template(
        "subtype_review/slice.html",
        subtype=subtype,
        target=target,
        description=describe_subtype(POS_TYPE, subtype),
        target_description=describe_subtype(POS_TYPE, target),
        rows=rows,
    )


@bp.route("/<subtype>/to/<target>", methods=["POST"])
def submit_slice(subtype: str, target: str) -> ResponseReturnValue:
    """Apply or reject the checked moves to ``target``; drop them from the TSV.

    Unchecked rows, and a checked row that cannot be applied, stay in the TSV.
    """
    tsv_path = _tsv_path(subtype)
    fieldnames, rows = _read_table(tsv_path)
    slice_rows = [row for row in rows if _is_slice_row(row, target)]
    action = request.form.get("action")
    notes = (request.form.get("notes") or "").strip()
    picked_guids = set(request.form.getlist("pick"))
    picked = [row for row in slice_rows if row.get("guid") in picked_guids]

    if str(len(slice_rows)) != request.form.get("expected_count"):
        flash_and_log(
            f"{subtype} -> {target} changed since the page was loaded "
            f"({len(slice_rows)} rows now); nothing done",
            "error",
        )
        return redirect(url_for("subtype_review.review_slice", subtype=subtype, target=target))
    if not picked:
        flash_and_log(f"{subtype} -> {target}: no rows were checked; nothing done", "warning")
        return redirect(url_for("subtype_review.review_slice", subtype=subtype, target=target))

    if action == "apply":
        result = apply_rows(g.db, [_as_move(row) for row in picked])
        log_operation(
            g.db,
            operation_type="subtype_review_slice_applied",
            source="barsukas-subtype-review",
            entity_type="pos_subtype",
            details={
                "pos_type": POS_TYPE,
                "subtype": subtype,
                "target": target,
                "notes": notes,
                "moved": [
                    {"word": move.word, "old_guid": move.old_guid, "new_guid": move.new_guid}
                    for move in result.applied
                ],
                "skipped": list(result.skipped),
            },
        )
        g.db.commit()
        done_guids = {move.old_guid for move in result.applied}
        flash_and_log(f"{subtype} -> {target}: moved {len(result.applied)}", "success")
        if result.skipped:
            flash_and_log(
                f"{len(result.skipped)} row(s) could not be applied and stay in the TSV: "
                + "; ".join(result.skipped),
                "warning",
            )
    elif action == "reject":
        done_guids = {row["guid"] for row in picked}
        flash_and_log(f"{subtype} -> {target}: rejected {len(picked)}", "success")
    else:
        abort(400)

    remaining = [
        row for row in rows if not (_is_slice_row(row, target) and row["guid"] in done_guids)
    ]
    _write_rows(tsv_path, fieldnames, remaining)
    if any(_is_slice_row(row, target) for row in remaining):
        return redirect(url_for("subtype_review.review_slice", subtype=subtype, target=target))
    return redirect(url_for("subtype_review.review", subtype=subtype))


def _find_row(rows: List[Dict[str, str]], guid: str) -> Dict[str, str]:
    """The TSV row for ``guid``, or 404."""
    for row in rows:
        if row.get("guid") == guid:
            return row
    abort(404)


@bp.route("/<subtype>/word/<guid>")
def review_word(subtype: str, guid: str) -> ResponseReturnValue:
    """One flagged row, with every subtype offered as its destination."""
    row = _find_row(_read_rows(_tsv_path(subtype)), guid)
    return render_template(
        "subtype_review/word.html",
        subtype=subtype,
        description=describe_subtype(POS_TYPE, subtype),
        row=row,
        choices=[choice for choice in classifiable_subtypes(POS_TYPE) if choice != subtype],
    )


@bp.route("/<subtype>/word/<guid>", methods=["POST"])
def submit_word(subtype: str, guid: str) -> ResponseReturnValue:
    """Move one row's sense to the chosen subtype, or reject it; drop it from the TSV.

    The chosen subtype replaces the suggestion, and a flag-only row is treated
    as a move, so any flagged row can be sent anywhere.
    """
    tsv_path = _tsv_path(subtype)
    fieldnames, rows = _read_table(tsv_path)
    row = _find_row(rows, guid)
    action = request.form.get("action")

    if action == "move":
        chosen = request.form.get("target_subtype") or ""
        notes = (request.form.get("notes") or "").strip()
        result = apply_rows(g.db, [{**row, "suggested_subtype": chosen, "verdict": "move"}])
        if result.skipped:
            flash_and_log(f"{row['word']}: not moved, {result.skipped[0]}", "error")
            return redirect(url_for("subtype_review.review_word", subtype=subtype, guid=guid))
        move = result.applied[0]
        log_operation(
            g.db,
            operation_type="subtype_review_word_moved",
            source="barsukas-subtype-review",
            entity_type="pos_subtype",
            details={
                "pos_type": POS_TYPE,
                "subtype": subtype,
                "word": move.word,
                "suggested_subtype": row.get("suggested_subtype", ""),
                "new_subtype": chosen,
                "old_guid": move.old_guid,
                "new_guid": move.new_guid,
                "notes": notes,
            },
        )
        g.db.commit()
        flash_and_log(f"{move.word}: {subtype} -> {chosen} ({move.new_guid})", "success")
    elif action == "reject":
        flash_and_log(f"{row['word']}: rejected, stays {subtype}", "success")
    else:
        abort(400)

    _write_rows(tsv_path, fieldnames, [other for other in rows if other is not row])
    return redirect(url_for("subtype_review.review", subtype=subtype))


@bp.route("/<subtype>", methods=["POST"])
def submit(subtype: str) -> ResponseReturnValue:
    """Apply the approved rows, log the review, clear the TSV, mark complete.

    Ignored rows are written back to the TSV as they were, and the subtype is
    marked complete only when no row was ignored.  Malformed rows (a move with
    no destination) are skipped: not applied, not counted as rejected, and
    listed under ``malformed`` in the operation log.
    """
    tsv_path = _tsv_path(subtype)
    fieldnames, rows = _read_table(tsv_path)
    notes = (request.form.get("notes") or "").strip()

    decisions = [request.form.get(f"decision_{index}") for index in range(len(rows))]
    malformed = [row for row in rows if _is_malformed(row)]
    approved = [
        row
        for row, decision in zip(rows, decisions)
        if decision == "approve" and row.get("verdict") == "move" and row not in malformed
    ]
    ignored = [
        row
        for row, decision in zip(rows, decisions)
        if decision == "ignore" and row not in malformed
    ]
    rejected_words = [
        row.get("word", "")
        for row in rows
        if row not in approved and row not in ignored and row not in malformed
    ]

    result = apply_rows(g.db, [_as_move(row) for row in approved])
    log_operation(
        g.db,
        operation_type="subtype_review_completed",
        source="barsukas-subtype-review",
        entity_type="pos_subtype",
        details={
            "pos_type": POS_TYPE,
            "subtype": subtype,
            "notes": notes,
            "moved": [
                {
                    "word": move.word,
                    "new_subtype": move.new_subtype,
                    "old_guid": move.old_guid,
                    "new_guid": move.new_guid,
                }
                for move in result.applied
            ],
            "rejected": rejected_words,
            "ignored": [row.get("word", "") for row in ignored],
            "malformed": [
                {"word": row.get("word", ""), "guid": row.get("guid", "")} for row in malformed
            ],
            "skipped": list(result.skipped),
        },
    )
    g.db.commit()

    if ignored:
        _write_rows(tsv_path, fieldnames, ignored)
        flash_and_log(
            f"{subtype}: moved {len(result.applied)}, rejected {len(rejected_words)}; "
            f"{len(ignored)} ignored row(s) left in the TSV, not marked complete",
            "success",
        )
    else:
        tsv_path.unlink()
        tsv_path.with_suffix(".log").unlink(missing_ok=True)
        _mark_complete(subtype, notes)
        flash_and_log(
            f"{subtype}: moved {len(result.applied)}, rejected {len(rejected_words)}; "
            "marked complete",
            "success",
        )
    if result.skipped:
        flash_and_log(
            f"{subtype}: {len(result.skipped)} approved row(s) could not be applied: "
            + "; ".join(result.skipped),
            "warning",
        )
    return redirect(url_for("subtype_review.index"))
