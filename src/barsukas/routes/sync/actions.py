#!/usr/bin/python3

"""Form parsing and result reporting shared by the ``/sync`` blueprints.

Every "apply" route in the sync system reads the same two form shapes and
reports the same four numbers, so both live here rather than being retyped per
blueprint.

Form shapes
-----------

``action_{row_id}``
    One choice per row: ``skip``, ``use_db`` or ``use_release``. Used by the
    difficulty, level and text-change pages.

``action_{row_id}_{language_code}``
    One choice per row *and language*. Language codes contain hyphens
    (``zh-tw``) but never underscores, so the split is on the first underscore.

Bulk scope
----------

The list pages are paginated, which would otherwise make "use release for
everything" a chore of one submit per page. A bulk submit instead sends
:data:`BULK_ACTION_FIELD` with no per-row fields, and the route re-derives the
full difference list server-side and applies that one action to all of it. The
count the user confirmed against is echoed back in
:data:`BULK_EXPECTED_FIELD` so a list that changed under them is rejected
rather than silently applied to a different set of rows.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from flask import current_app, flash, request

logger = logging.getLogger(__name__)

ACTION_PREFIX = "action_"

#: The three per-row choices. "skip" is the default and does nothing.
SKIP = "skip"
USE_DB = "use_db"
USE_RELEASE = "use_release"
APPLICABLE_ACTIONS: Tuple[str, ...] = (USE_DB, USE_RELEASE)

BULK_ACTION_FIELD = "bulk_action"
BULK_EXPECTED_FIELD = "bulk_expected_count"


def is_readonly() -> bool:
    """Whether the app is running against a read-only database."""
    return bool(current_app.config.get("READONLY", False))


def parse_row_actions(form: Optional[Any] = None) -> Dict[str, str]:
    """Parse ``action_{row_id}`` fields into ``{row_id: action}``.

    Rows left on "skip" are included, so callers can count them.
    """
    source = request.form if form is None else form
    return {
        key[len(ACTION_PREFIX) :]: value
        for key, value in source.items()
        if key.startswith(ACTION_PREFIX)
    }


def parse_language_actions(form: Optional[Any] = None) -> Dict[str, Dict[str, str]]:
    """Parse ``action_{row_id}_{language_code}`` into ``{row_id: {lang: action}}``."""
    source = request.form if form is None else form
    actions: Dict[str, Dict[str, str]] = {}
    for key, value in source.items():
        if not key.startswith(ACTION_PREFIX):
            continue
        remainder = key[len(ACTION_PREFIX) :]
        separator = remainder.find("_")
        if separator == -1:
            continue
        actions.setdefault(remainder[:separator], {})[remainder[separator + 1 :]] = value
    return actions


@dataclass
class BulkRequest:
    """A submitted "apply this to everything" request."""

    action: str
    expected_count: int


def parse_bulk_request(form: Optional[Any] = None) -> Optional[BulkRequest]:
    """Return the bulk request on this submit, or None for a per-row submit."""
    source = request.form if form is None else form
    action = source.get(BULK_ACTION_FIELD, "").strip()
    if action not in APPLICABLE_ACTIONS:
        return None
    try:
        expected = int(source.get(BULK_EXPECTED_FIELD, "0"))
    except ValueError:
        expected = 0
    return BulkRequest(action=action, expected_count=expected)


def bulk_actions_for(
    bulk: BulkRequest, row_ids: Iterable[Any], *, total: int
) -> Optional[Dict[str, str]]:
    """Expand a bulk request into per-row actions, or None if the list moved.

    ``total`` is the number of differences the route just recomputed. When it
    disagrees with what the page showed, the submit is refused: the user
    confirmed a number, and applying to a different set of rows than the one
    they were looking at is exactly the surprise a bulk button must not spring.
    """
    if bulk.expected_count and bulk.expected_count != total:
        flash(
            f"The list changed since the page was loaded "
            f"({bulk.expected_count} shown, {total} now). Nothing was applied - "
            "reload and try again.",
            "warning",
        )
        return None
    return {str(row_id): bulk.action for row_id in row_ids}


@dataclass
class SyncOutcome:
    """Running totals for one apply request, and the flash messages for them."""

    #: What was synced, singular, for the messages ("lemma", "translation").
    noun: str = "item"
    updated_db: int = 0
    updated_release: int = 0
    imported: int = 0
    deleted: int = 0
    exported: int = 0
    skipped: int = 0
    errors: int = 0
    #: Extra lines appended to the success flash, e.g. "with 4 grammar fact(s)".
    details: List[str] = field(default_factory=list)

    def record_error(self, message: str) -> None:
        """Log a per-row failure and count it."""
        logger.error(message)
        self.errors += 1

    @property
    def changed_database(self) -> bool:
        """Whether anything in this request wrote to the database."""
        return bool(self.updated_db or self.imported or self.deleted)

    def flash_summary(self) -> None:
        """Flash one message per non-zero total, in a fixed order."""
        plural = f"{self.noun}(s)"
        for count, template in (
            (self.imported, f"Imported {{}} {plural}"),
            (self.updated_db, f"Updated {{}} {plural} in database"),
            (self.updated_release, f"Updated {{}} {plural} in release files"),
            (self.exported, f"Exported {{}} {plural} to release files"),
            (self.deleted, f"Deleted {{}} {plural}"),
        ):
            if count:
                message = template.format(count)
                if self.details:
                    message += " (" + "; ".join(self.details) + ")"
                flash(message, "success")
        if self.skipped:
            flash(f"Skipped {self.skipped} {plural}", "info")
        if self.errors:
            flash(f"Errors: {self.errors}", "warning")

    def commit(self, session: Any) -> None:
        """Commit the session, converting a failure into a flashed error.

        Zeroes the database-side counters on failure so ``flash_summary`` cannot
        claim rows were updated when the transaction rolled back.
        """
        if not self.changed_database:
            return
        try:
            session.commit()
        except Exception as commit_error:  # noqa: BLE001 - surfaced to the user
            session.rollback()
            logger.error(f"Commit error: {commit_error}")
            flash(f"Error committing changes: {commit_error}", "error")
            self.updated_db = 0
            self.imported = 0
            self.deleted = 0
            self.errors += 1
