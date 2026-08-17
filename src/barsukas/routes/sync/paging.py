#!/usr/bin/python3

"""Pagination for the sync difference lists.

The lemma translation page renders one ``<select>`` per lemma *per differing
language*; at ~2000 differing lemmas that is several thousand native select
widgets in one document, which is what makes the page crawl. Nothing about the
data requires them all to be present at once, so the list pages slice.

Paging alone would make "use release for everything" a chore of one submit per
page, so it is paired with the bulk apply in :mod:`barsukas.routes.sync.actions`:
page through to review, or submit one action against the whole list.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from flask import request

DEFAULT_PER_PAGE = 200

#: Offered in the page-size select. ``0`` means "no limit" - kept because a
#: whole-list view is genuinely useful for Ctrl-F and for small categories, and
#: hiding it would just push people back to hand-editing URLs.
PER_PAGE_CHOICES: Sequence[int] = (50, 100, 200, 500, 0)


@dataclass
class Page:
    """One slice of a difference list, plus what a pager needs to render."""

    items: List[Any]
    page: int
    per_page: int
    total: int

    @property
    def unlimited(self) -> bool:
        """Whether this page is showing the whole list."""
        return self.per_page <= 0

    @property
    def pages(self) -> int:
        """Total number of pages (always at least 1)."""
        if self.unlimited or self.total == 0:
            return 1
        return (self.total + self.per_page - 1) // self.per_page

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def first_index(self) -> int:
        """1-based index of the first item shown (0 when the list is empty)."""
        if self.total == 0:
            return 0
        if self.unlimited:
            return 1
        return (self.page - 1) * self.per_page + 1

    @property
    def last_index(self) -> int:
        """1-based index of the last item shown."""
        if self.unlimited:
            return self.total
        return min(self.page * self.per_page, self.total)

    def page_numbers(self, window: int = 3) -> List[Optional[int]]:
        """Page numbers to link, with ``None`` marking an elided run.

        Always includes the first and last page and ``window`` pages either side
        of the current one, so the pager stays a fixed width at any list size.
        """
        if self.pages <= 1:
            return [1]
        wanted = {1, self.pages}
        wanted.update(
            number
            for number in range(self.page - window, self.page + window + 1)
            if 1 <= number <= self.pages
        )
        numbers: List[Optional[int]] = []
        previous: Optional[int] = None
        for number in sorted(wanted):
            if previous is not None and number != previous + 1:
                numbers.append(None)
            numbers.append(number)
            previous = number
        return numbers


def paginate(items: Sequence[Any], *, default_per_page: int = DEFAULT_PER_PAGE) -> Page:
    """Slice ``items`` according to the request's ``page`` / ``per_page`` args.

    Out-of-range values are clamped rather than rejected: a stale bookmark
    pointing past the end of a shrunken list should show the last page, not an
    error.
    """
    per_page = _int_arg("per_page", default_per_page)
    if per_page < 0 or per_page not in PER_PAGE_CHOICES:
        per_page = default_per_page

    total = len(items)
    if per_page <= 0:
        return Page(items=list(items), page=1, per_page=0, total=total)

    last_page = max(1, (total + per_page - 1) // per_page)
    page = min(max(_int_arg("page", 1), 1), last_page)
    start = (page - 1) * per_page
    return Page(
        items=list(items[start : start + per_page]), page=page, per_page=per_page, total=total
    )


def _int_arg(name: str, fallback: int) -> int:
    """Read one integer query argument, falling back on anything unparseable."""
    try:
        return int(request.args.get(name, fallback))
    except (TypeError, ValueError):
        return fallback


def page_args(**overrides: Any) -> Dict[str, Any]:
    """Current query args (minus ``page``) with ``overrides`` applied.

    Hand this to the pager macros so whatever else is in the query string - a
    multi-valued language filter, say - survives a click on "Next" instead of
    being dropped. Repeated parameters stay lists, which ``url_for`` re-expands
    into repeated parameters.
    """
    args: Dict[str, Any] = {
        key: values if len(values) > 1 else values[0]
        for key, values in request.args.to_dict(flat=False).items()
        if key != "page"
    }
    args.update(overrides)
    return {key: value for key, value in args.items() if value not in (None, "", [])}
