#!/usr/bin/python3

"""Download the Project Gutenberg books making up a corpus.

    PYTHONPATH=src python src/wordfreq/corpora/download_gutenberg.py --corpus 19th_books
    PYTHONPATH=src python src/wordfreq/corpora/download_gutenberg.py --corpus all --delay 2
    PYTHONPATH=src python src/wordfreq/corpora/download_gutenberg.py --ids 1342 84 --dest /tmp/books

Texts land in a scratch cache directory (``$GREENLAND_GUTENBERG_CACHE``, or a
directory under the system temp dir), never in the repository: they are bulky
inputs to the corpus JSON files, not artifacts worth keeping. Already-downloaded
files are skipped unless ``--force`` is given, so a re-run costs nothing.

This script makes live HTTP requests to gutenberg.org. It sleeps ``--delay``
seconds between requests to stay a polite client of a donated-bandwidth
archive; do not lower it much.
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests

import constants
from wordfreq.corpora.book_lists import BOOK_LISTS, GutenbergBook, find_book, get_book_list
from wordfreq.corpora.gutenberg_text import extract_title

logger = logging.getLogger(__name__)

DEFAULT_MIRROR = "https://www.gutenberg.org"
DEFAULT_DELAY_SECONDS = 1.5
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_RETRIES = 3
USER_AGENT = "greenland-wordfreq-corpus-builder/1.0 (linguistic research; contact via repo)"
MANIFEST_FILENAME = "manifest.json"

# Catalogue metadata API, used only by --verify. It returns a few KB of JSON
# per book and never any book text.
METADATA_API = "https://gutendex.com/books"
METADATA_BATCH_SIZE = 30

# Gutenberg exposes plain text at several paths depending on the book's age.
URL_TEMPLATES = (
    "{mirror}/cache/epub/{book_id}/pg{book_id}.txt",
    "{mirror}/files/{book_id}/{book_id}-0.txt",
    "{mirror}/files/{book_id}/{book_id}.txt",
    "{mirror}/ebooks/{book_id}.txt.utf-8",
)

# A real book file always mentions Project Gutenberg; an error page will not.
SANITY_MARKER = "project gutenberg"
MIN_REASONABLE_BYTES = 5000


def default_cache_dir() -> Path:
    """Directory holding downloaded books.

    Defaults to ``data/working/gutenberg`` in the repo, which is gitignored and
    survives reboots.  Gutenberg rate-limits downloads, so re-fetching a book
    because a scratch directory was cleared is worth avoiding.
    """
    configured = os.environ.get("GREENLAND_GUTENBERG_CACHE")
    if configured:
        return Path(configured)
    return Path(constants.GUTENBERG_CACHE_DIR)


def text_path(cache_dir: Path, book_id: int) -> Path:
    """Path of the cached plain-text file for ``book_id``."""
    return cache_dir / f"{book_id}.txt"


def load_manifest(cache_dir: Path) -> Dict[str, Any]:
    """Read the download manifest, returning an empty one if absent."""
    manifest_path = cache_dir / MANIFEST_FILENAME
    if not manifest_path.exists():
        return {"books": {}}
    try:
        with open(manifest_path, "r", encoding="utf-8") as handle:
            loaded: Dict[str, Any] = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        logger.warning("Could not read manifest %s: %s", manifest_path, error)
        return {"books": {}}
    loaded.setdefault("books", {})
    return loaded


def save_manifest(cache_dir: Path, manifest: Dict[str, Any]) -> None:
    """Write the download manifest back to the cache directory."""
    manifest_path = cache_dir / MANIFEST_FILENAME
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def fetch_book_text(
    book_id: int,
    *,
    mirror: str = DEFAULT_MIRROR,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    retries: int = DEFAULT_RETRIES,
    session: Optional[requests.Session] = None,
) -> Optional[tuple[str, str]]:
    """Fetch one book's plain text.

    Tries each known Gutenberg text URL in turn, retrying transient failures
    with exponential backoff.

    Args:
        book_id: Gutenberg ebook number.
        mirror: Base URL to fetch from.
        timeout: Per-request timeout in seconds.
        retries: Attempts per URL before moving to the next one.
        session: Optional requests session to reuse.

    Returns:
        ``(text, url)`` on success, ``None`` if every URL failed.
    """
    http = session or requests.Session()
    headers = {"User-Agent": USER_AGENT}

    for template in URL_TEMPLATES:
        url = template.format(mirror=mirror.rstrip("/"), book_id=book_id)
        for attempt in range(1, retries + 1):
            try:
                response = http.get(url, headers=headers, timeout=timeout)
            except requests.RequestException as error:
                logger.warning("  %s: %s (attempt %d)", url, error, attempt)
                time.sleep(2**attempt)
                continue

            if response.status_code == 404:
                break
            if response.status_code != 200:
                logger.warning("  %s: HTTP %d (attempt %d)", url, response.status_code, attempt)
                time.sleep(2**attempt)
                continue

            response.encoding = response.encoding or "utf-8"
            text = response.text
            if len(text) < MIN_REASONABLE_BYTES or SANITY_MARKER not in text[:4000].lower():
                logger.warning("  %s: response does not look like a Gutenberg text", url)
                break
            return text, url

    return None


def download_book(
    book: GutenbergBook,
    cache_dir: Path,
    manifest: Dict[str, Any],
    *,
    mirror: str = DEFAULT_MIRROR,
    force: bool = False,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    session: Optional[requests.Session] = None,
) -> str:
    """Download one book into the cache.

    Returns:
        ``"cached"``, ``"downloaded"`` or ``"failed"``.
    """
    destination = text_path(cache_dir, book.gutenberg_id)
    if destination.exists() and not force:
        logger.info("  %s: cached", book.title)
        return "cached"

    fetched = fetch_book_text(book.gutenberg_id, mirror=mirror, timeout=timeout, session=session)
    if fetched is None:
        logger.error("  %s (#%d): download failed", book.title, book.gutenberg_id)
        return "failed"

    text, url = fetched
    destination.write_text(text, encoding="utf-8")

    found_title = extract_title(text)
    if found_title and not _titles_agree(found_title, book.title):
        logger.warning(
            "  #%d title mismatch: expected %r, file says %r",
            book.gutenberg_id,
            book.title,
            found_title,
        )

    manifest["books"][str(book.gutenberg_id)] = {
        "gutenberg_id": book.gutenberg_id,
        "title": book.title,
        "author": book.author,
        "year": book.year,
        "slug": book.slug,
        "url": url,
        "bytes": len(text.encode("utf-8")),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "file_title": found_title,
        "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    logger.info("  %s: %d KB from %s", book.title, len(text) // 1024, url)
    return "downloaded"


def _titles_agree(found: str, expected: str) -> bool:
    """Loose comparison of a file's ``Title:`` header with the expected title."""

    def simplify(value: str) -> str:
        return "".join(char.lower() for char in value if char.isalnum())

    simple_found = simplify(found)
    simple_expected = simplify(expected)
    if not simple_found or not simple_expected:
        return True
    shorter, longer = sorted((simple_found, simple_expected), key=len)
    return shorter[: max(12, len(shorter) // 2)] in longer


def verify_book_ids(
    books: Sequence[GutenbergBook],
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    session: Optional[requests.Session] = None,
) -> List[Tuple[GutenbergBook, str, Optional[str]]]:
    """Check each book's ID against the Gutenberg catalogue.

    Downloads catalogue metadata only - a few KB per book, no book text - so
    this is the cheap way to confirm a hand-written book list points at the
    books it claims. Use it on any ID listed in
    ``book_lists.UNVERIFIED_IDS``.

    Args:
        books: Books to check.
        timeout: Per-request timeout in seconds.
        session: Optional requests session to reuse.

    Returns:
        One ``(book, status, catalogue_title)`` per book, where status is
        ``"ok"``, ``"mismatch"``, ``"not-found"`` or ``"error"``.
    """
    http = session or requests.Session()
    headers = {"User-Agent": USER_AGENT}
    results: List[Tuple[GutenbergBook, str, Optional[str]]] = []

    for start in range(0, len(books), METADATA_BATCH_SIZE):
        batch = list(books[start : start + METADATA_BATCH_SIZE])
        ids = ",".join(str(book.gutenberg_id) for book in batch)
        catalogue: Dict[int, str] = {}
        try:
            response = http.get(METADATA_API, params={"ids": ids}, headers=headers, timeout=timeout)
            response.raise_for_status()
            for entry in response.json().get("results", []):
                catalogue[int(entry["id"])] = str(entry.get("title", ""))
        except (requests.RequestException, ValueError, KeyError) as error:
            logger.error("Metadata lookup failed for %s: %s", ids, error)
            results.extend((book, "error", None) for book in batch)
            continue

        for book in batch:
            found = catalogue.get(book.gutenberg_id)
            if found is None:
                results.append((book, "not-found", None))
            elif _titles_agree(found, book.title):
                results.append((book, "ok", found))
            else:
                results.append((book, "mismatch", found))

    return results


def print_verification(results: Sequence[Tuple[GutenbergBook, str, Optional[str]]]) -> int:
    """Print a verification table. Returns the number of problems found."""
    problems = 0
    for book, status, found in results:
        if status == "ok":
            marker = "ok      "
        else:
            marker = status.upper().ljust(8)
            problems += 1
        detail = f"  catalogue says: {found!r}" if status == "mismatch" else ""
        print(f"  {marker} {book.gutenberg_id:>6}  {book.title[:52]:<54}{detail}")
    print(f"\n  {len(results) - problems} of {len(results)} IDs confirmed")
    if problems:
        print("  Fix the entries above in book_lists.py, then clear them from UNVERIFIED_IDS.")
    return problems


def resolve_books(corpus: Optional[str], ids: Optional[Sequence[int]]) -> List[GutenbergBook]:
    """Resolve the CLI selection into a list of books to download."""
    if ids:
        books: List[GutenbergBook] = []
        for book_id in ids:
            known = find_book(book_id)
            books.append(known or GutenbergBook(book_id, f"Gutenberg {book_id}", ""))
        return books

    if corpus == "all":
        combined: List[GutenbergBook] = []
        seen: set[int] = set()
        for book_list in BOOK_LISTS.values():
            for book in book_list.books:
                if book.gutenberg_id not in seen:
                    seen.add(book.gutenberg_id)
                    combined.append(book)
        return combined

    if corpus is None:
        return []
    return list(get_book_list(corpus).books)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        choices=sorted(BOOK_LISTS) + ["all"],
        help="Corpus whose book list should be downloaded",
    )
    parser.add_argument(
        "--ids",
        type=int,
        nargs="+",
        help="Explicit Gutenberg ebook IDs (overrides --corpus)",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help=f"Cache directory (default: {default_cache_dir()})",
    )
    parser.add_argument("--mirror", default=DEFAULT_MIRROR, help="Gutenberg base URL")
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY_SECONDS,
        help=f"Seconds to wait between downloads (default: {DEFAULT_DELAY_SECONDS})",
    )
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="Per-request timeout"
    )
    parser.add_argument("--force", action="store_true", help="Re-download cached books")
    parser.add_argument("--limit", type=int, help="Stop after this many books")
    parser.add_argument(
        "--dry-run", action="store_true", help="List what would be downloaded and exit"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Check IDs against Gutenberg catalogue metadata and exit "
        "(no book text is downloaded)",
    )
    parser.add_argument("--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    if not args.corpus and not args.ids:
        parser.error("one of --corpus or --ids is required")

    books = resolve_books(args.corpus, args.ids)
    if args.limit:
        books = books[: args.limit]
    if not books:
        logger.error("Nothing to download")
        return 1

    cache_dir = args.dest or default_cache_dir()

    if args.verify:
        print(f"Checking {len(books)} ID(s) against the Gutenberg catalogue:")
        return 1 if print_verification(verify_book_ids(books, timeout=args.timeout)) else 0

    if args.dry_run:
        print(f"Would download {len(books)} book(s) into {cache_dir}:")
        for book in books:
            state = "cached" if text_path(cache_dir, book.gutenberg_id).exists() else "missing"
            print(f"  {book.gutenberg_id:>6}  {book.title[:60]:<62} [{state}]")
        return 0

    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(cache_dir)
    session = requests.Session()

    counts = {"cached": 0, "downloaded": 0, "failed": 0}
    failures: List[GutenbergBook] = []
    for index, book in enumerate(books, start=1):
        logger.info("[%d/%d] #%d %s", index, len(books), book.gutenberg_id, book.title)
        outcome = download_book(
            book,
            cache_dir,
            manifest,
            mirror=args.mirror,
            force=args.force,
            timeout=args.timeout,
            session=session,
        )
        counts[outcome] += 1
        if outcome == "failed":
            failures.append(book)
        if outcome == "downloaded" and index < len(books):
            time.sleep(args.delay)

    save_manifest(cache_dir, manifest)

    print(f"\nCache directory: {cache_dir}")
    print(f"  downloaded: {counts['downloaded']}")
    print(f"  cached:     {counts['cached']}")
    print(f"  failed:     {counts['failed']}")
    for book in failures:
        print(f"    FAILED #{book.gutenberg_id} {book.title}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
