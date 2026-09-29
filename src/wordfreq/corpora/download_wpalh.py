#!/usr/bin/python3

"""Download the WPA American Life Histories PDFs from the Library of Congress.

    PYTHONPATH=src python src/wordfreq/corpora/download_wpalh.py \
        --dest "/Volumes/Dorothy Day/wpalh"
    PYTHONPATH=src python src/wordfreq/corpora/download_wpalh.py --dry-run
    PYTHONPATH=src python src/wordfreq/corpora/download_wpalh.py --limit 5

The collection is "American Life Histories: Manuscripts from the Federal
Writers' Project, 1936-1940": about 2,800 interviews with ordinary Americans,
written up by WPA staff.  Its register -- people talking about their work,
families and towns -- is what no other corpus here supplies.  The writers were
federal employees, and the Library of Congress lists every item as "No known
restrictions on use or reproduction."  Items carrying any other rights
statement are skipped, not downloaded.

Files land in a scratch cache directory (``$GREENLAND_WPALH_CACHE``, else
``data/working/wpalh``), never in the repository.  Already-downloaded PDFs are
skipped unless ``--force`` is given, so an interrupted run resumes where it
stopped.  Layout::

    <cache>/meta/listing_c150_sp<N>.json   collection listing pages
    <cache>/pdf/wpalh-<shelf id>.pdf       one PDF per interview
    <cache>/manifest.json                  per-item metadata and status

There is no bulk download: LC Labs' data packages do not include this
collection.  Each item's PDF is the cheapest way to its text -- one request per
interview, where the per-page text service would take one per page (~17,000).
The PDF carries the Library's own OCR as an invisible text layer, which is
what ``pypdf`` reads back out; nothing here runs OCR.

This script makes live HTTP requests to www.loc.gov (the listing) and
tile.loc.gov (the PDFs).  The Library asks that automated clients send "no more
than 10 requests per minute" in total and reserves the right to terminate
programs that run over 24 hours; exceeding the API rate limits blocks the
client for an hour.  ``--delay`` therefore defaults to 6 seconds, which puts a
full run at about five hours, and an HTTP 429 stops the run instead of
retrying into a longer block.
"""

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests

logger = logging.getLogger(__name__)

COLLECTION_URL = "https://www.loc.gov/collections/federal-writers-project/"
LISTING_PAGE_SIZE = 150
# 10 requests per minute, the Library's stated ceiling for automated clients.
DEFAULT_DELAY_SECONDS = 6.0
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_RETRIES = 3
USER_AGENT = "greenland-wordfreq-corpus-builder/1.0 (linguistic research; contact via repo)"
MANIFEST_FILENAME = "manifest.json"
# Every item in the collection carries this statement; anything else is left
# alone rather than guessed at.
ALLOWED_RIGHTS_PREFIX = "No known restrictions"


class RateLimitedError(RuntimeError):
    """The server answered 429: stop now rather than extend the block."""


@dataclass
class LifeHistoryItem:
    """One interview as the collection listing describes it."""

    item_id: str
    shelf_id: str
    title: str
    place: str
    date: str
    contributors: List[str]
    rights: str
    pages: Optional[int]
    pdf_url: str


def default_cache_dir() -> Path:
    """Directory holding the listing, PDFs and manifest."""
    configured = os.environ.get("GREENLAND_WPALH_CACHE")
    if configured:
        return Path(configured)
    return Path("data/working/wpalh")


def pdf_dir(cache_dir: Path) -> Path:
    """Directory of downloaded PDFs."""
    return cache_dir / "pdf"


def meta_dir(cache_dir: Path) -> Path:
    """Directory of cached listing pages."""
    return cache_dir / "meta"


def pdf_path(cache_dir: Path, shelf_id: str) -> Path:
    """Path of the cached PDF for one interview."""
    return pdf_dir(cache_dir) / f"{shelf_id}.pdf"


def listing_path(cache_dir: Path, page: int) -> Path:
    """Path of one cached listing page."""
    return meta_dir(cache_dir) / f"listing_c{LISTING_PAGE_SIZE}_sp{page}.json"


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def _get(
    session: requests.Session,
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    retries: int = DEFAULT_RETRIES,
    delay: float = DEFAULT_DELAY_SECONDS,
) -> Optional[requests.Response]:
    """GET with retries on transient failures; ``None`` when it never succeeds.

    Sleeps ``delay`` after every attempt, retries included, so the request
    rate stays under the Library's ceiling however the attempts go.

    Raises:
        RateLimitedError: on HTTP 429.  The Library blocks a client for an
            hour after it exceeds a limit, and retrying only resets the clock.
    """
    for attempt in range(1, retries + 1):
        try:
            response = session.get(url, params=params, timeout=timeout)
        except requests.RequestException as error:
            logger.warning("%s: %s (attempt %d/%d)", url, error, attempt, retries)
            time.sleep(delay)
            continue
        time.sleep(delay)
        if response.status_code == 429:
            raise RateLimitedError(f"{url}: HTTP 429 (rate limited)")
        if response.status_code == 404:
            logger.warning("%s: not found", url)
            return None
        if response.status_code != 200:
            logger.warning(
                "%s: HTTP %d (attempt %d/%d)", url, response.status_code, attempt, retries
            )
            continue
        return response
    return None


def fetch_listing_page(
    session: requests.Session,
    cache_dir: Path,
    page: int,
    *,
    refresh: bool = False,
    delay: float = DEFAULT_DELAY_SECONDS,
) -> Optional[Dict[str, Any]]:
    """One page of the collection listing, from the cache when it is there."""
    path = listing_path(cache_dir, page)
    if path.exists() and not refresh:
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(cached, dict) and "results" in cached:
                return cached
        except ValueError:
            logger.warning("%s: unreadable, refetching", path)
    response = _get(
        session,
        COLLECTION_URL,
        params={"c": LISTING_PAGE_SIZE, "sp": page, "fo": "json", "at": "results,pagination"},
        delay=delay,
    )
    if response is None:
        return None
    try:
        payload = response.json()
    except ValueError as error:
        logger.warning("listing page %d: bad JSON: %s", page, error)
        return None
    if not isinstance(payload, dict) or "results" not in payload:
        logger.warning("listing page %d: no results in response", page)
        return None
    path.write_text(json.dumps(payload), encoding="utf-8")
    return dict(payload)


def parse_listing_result(result: Dict[str, Any]) -> Optional[LifeHistoryItem]:
    """The fields worth keeping from one listing entry; ``None`` without a PDF."""
    resources = result.get("resources") or [{}]
    pdf_url = resources[0].get("pdf")
    if not pdf_url:
        return None
    # ".../wpalh-07030116/wpalh-07030116.pdf" -> "wpalh-07030116"
    shelf_id = pdf_url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".pdf")
    item = result.get("item") or {}
    places = item.get("created_published") or []
    pages = resources[0].get("segments")
    return LifeHistoryItem(
        item_id=str(result.get("id") or ""),
        shelf_id=shelf_id,
        title=str(item.get("title") or result.get("title") or ""),
        place=str(places[0]) if places else "",
        date=str(result.get("date") or ""),
        contributors=[str(name) for name in item.get("contributors") or []],
        rights=str(item.get("rights") or ""),
        pages=int(pages) if isinstance(pages, int) else None,
        pdf_url=str(pdf_url),
    )


def list_collection(
    session: requests.Session,
    cache_dir: Path,
    *,
    refresh: bool = False,
    delay: float = DEFAULT_DELAY_SECONDS,
) -> Tuple[List[LifeHistoryItem], int]:
    """Every item in the collection, deduplicated by shelf id.

    Returns:
        ``(items, without_pdf)``: the items that have a PDF, and how many
        listing entries had none.
    """
    first = fetch_listing_page(session, cache_dir, 1, refresh=refresh, delay=delay)
    if not first:
        return [], 0
    pagination = first.get("pagination") or {}
    total_pages = int(pagination.get("total") or 1)
    logger.info("Collection: %s items over %d listing pages", pagination.get("of"), total_pages)

    items: Dict[str, LifeHistoryItem] = {}
    without_pdf = 0
    for page in range(1, total_pages + 1):
        payload = (
            first
            if page == 1
            else fetch_listing_page(session, cache_dir, page, refresh=refresh, delay=delay)
        )
        if not payload:
            logger.warning("listing page %d: unavailable, its items are skipped", page)
            continue
        for result in payload.get("results") or []:
            parsed = parse_listing_result(result)
            if parsed is None:
                without_pdf += 1
                logger.debug("no PDF: %s", result.get("id"))
                continue
            items.setdefault(parsed.shelf_id, parsed)
    return sorted(items.values(), key=lambda item: item.shelf_id), without_pdf


def download_pdf(
    session: requests.Session,
    item: LifeHistoryItem,
    cache_dir: Path,
    *,
    force: bool = False,
    delay: float = DEFAULT_DELAY_SECONDS,
) -> str:
    """Download one PDF, returning ``"cached"``, ``"downloaded"`` or ``"failed"``.

    Written to a temporary name and renamed into place, so an interrupted
    download never leaves a truncated file that a later run would take as
    cached.
    """
    path = pdf_path(cache_dir, item.shelf_id)
    if path.exists() and not force:
        return "cached"
    response = _get(session, item.pdf_url, delay=delay)
    if response is None:
        return "failed"
    if not response.content.startswith(b"%PDF"):
        logger.warning("%s: response is not a PDF, discarding", item.pdf_url)
        return "failed"
    partial = path.with_name(path.name + ".part")
    partial.write_bytes(response.content)
    partial.replace(path)
    return "downloaded"


def write_manifest(cache_dir: Path, entries: Dict[str, Dict[str, Any]]) -> None:
    """Merge per-item metadata and download status into the manifest."""
    path = cache_dir / MANIFEST_FILENAME
    existing: Dict[str, Any] = {"items": {}}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            pass
    items = existing.get("items") or {}
    items.update(entries)
    path.write_text(json.dumps({"items": items}, indent=1, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help=f"Cache directory (default: {default_cache_dir()})",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY_SECONDS,
        help=f"Seconds between requests (default: {DEFAULT_DELAY_SECONDS})",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Download at most this many new PDFs"
    )
    parser.add_argument(
        "--refresh-listing",
        action="store_true",
        help="Refetch the collection listing instead of using the cached pages",
    )
    parser.add_argument(
        "--force", action="store_true", help="Re-download PDFs already in the cache"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch the listing and report what would be downloaded",
    )
    parser.add_argument("--verbose", action="store_true", help="Log every item")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if args.delay < DEFAULT_DELAY_SECONDS:
        logger.warning(
            "--delay %.1f is faster than the Library's 10 requests/minute guideline",
            args.delay,
        )

    cache_dir: Path = args.dest or default_cache_dir()
    pdf_dir(cache_dir).mkdir(parents=True, exist_ok=True)
    meta_dir(cache_dir).mkdir(parents=True, exist_ok=True)
    session = _session()

    try:
        items, without_pdf = list_collection(
            session, cache_dir, refresh=args.refresh_listing, delay=args.delay
        )
    except RateLimitedError as error:
        logger.error("%s; stopping. The block lasts an hour.", error)
        return 1
    if not items:
        logger.error("The collection listing could not be read")
        return 1

    allowed = [item for item in items if item.rights.startswith(ALLOWED_RIGHTS_PREFIX)]
    restricted = len(items) - len(allowed)
    pending = [
        item for item in allowed if args.force or not pdf_path(cache_dir, item.shelf_id).exists()
    ]
    known_pages = [item.pages for item in allowed if item.pages]
    logger.info(
        "%d items with a PDF (%d listing entries without one); %d skipped for rights; "
        "%d already cached; %d to download",
        len(items),
        without_pdf,
        restricted,
        len(allowed) - len(pending),
        len(pending),
    )
    if known_pages:
        logger.info(
            "%d pages across %d items with a page count", sum(known_pages), len(known_pages)
        )
    if args.limit is not None:
        pending = pending[: args.limit]
    logger.info(
        "Estimated time for %d downloads: %.1f hours",
        len(pending),
        len(pending) * args.delay / 3600,
    )
    if args.dry_run:
        return 0

    counts = {"cached": 0, "downloaded": 0, "failed": 0}
    manifest: Dict[str, Dict[str, Any]] = {}
    exit_code = 0
    try:
        for index, item in enumerate(pending, start=1):
            status = download_pdf(session, item, cache_dir, force=args.force, delay=args.delay)
            counts[status] += 1
            logger.debug("%-10s %s %s", status, item.shelf_id, item.title)
            entry = asdict(item)
            entry["status"] = status
            manifest[item.shelf_id] = entry
            if index % 25 == 0:
                write_manifest(cache_dir, manifest)
                logger.info(
                    "[%d/%d] downloaded %d, failed %d",
                    index,
                    len(pending),
                    counts["downloaded"],
                    counts["failed"],
                )
    except RateLimitedError as error:
        logger.error("%s; stopping. Re-run after an hour to resume.", error)
        exit_code = 1
    except KeyboardInterrupt:
        logger.warning("Interrupted; re-run to resume")
        exit_code = 130

    # Already-cached items still get their metadata recorded.
    for item in allowed:
        if item.shelf_id not in manifest and pdf_path(cache_dir, item.shelf_id).exists():
            entry = asdict(item)
            entry["status"] = "cached"
            manifest[item.shelf_id] = entry
    write_manifest(cache_dir, manifest)
    logger.info(
        "downloaded %d, cached %d, failed %d",
        counts["downloaded"],
        counts["cached"],
        counts["failed"],
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
