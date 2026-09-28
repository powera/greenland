#!/usr/bin/python3

"""Download the pinned OpenStax book sources from GitHub.

    PYTHONPATH=src python src/wordfreq/corpora/download_openstax.py --corpus all
    PYTHONPATH=src python src/wordfreq/corpora/download_openstax.py --corpus openstax_science --dry-run

Each book's repository (``openstax/osbooks-<name>``) is checked out at the
commit ``openstax_books`` pins it to, into ``$GREENLAND_OPENSTAX_CACHE``, else
``data/working/openstax`` (gitignored).

Only the text is fetched.  The repositories are mostly images -- Anatomy and
Physiology is ~400MB of JPEGs -- so each checkout fetches the one pinned
commit (``--depth 1``) without file contents (``--filter=blob:none``), then a
sparse checkout pulls down just the collection files and each module's
``index.cnxml``.  The whole cache is ~130MB, ~100MB of it XML.

The license declared by each book's collection file is checked after
checkout, and a book that does not declare CC BY 4.0 at its pin fails the run
(see ``openstax_books`` for why the pins exist).

A repository already at its pinned commit is left alone, so a re-run costs
nothing.  This script makes live requests to github.com through ``git``.
"""

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Sequence

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from wordfreq.corpora.openstax_books import (
    REQUIRED_LICENSE_URL,
    OpenStaxBook,
    corpus_choices,
    get_books,
    repo_pins,
)

logger = logging.getLogger(__name__)

GITHUB_BASE = "https://github.com/openstax"

# The collection files (the table of contents) and each module's CNXML.  Media,
# the book's style files and anything else in the repository is not fetched.
SPARSE_PATTERNS = ("/collections/", "/modules/*/index.cnxml")


def default_cache_dir() -> Path:
    """Directory holding the book checkouts."""
    configured = os.environ.get("GREENLAND_OPENSTAX_CACHE")
    if configured:
        return Path(configured)
    return Path("data/working/openstax")


def repo_dir(cache_dir: Path, repo: str) -> Path:
    """Checkout directory of one repository."""
    return cache_dir / repo


def collection_path(cache_dir: Path, book: OpenStaxBook) -> Path:
    """Path of a book's collection file in its checkout."""
    return repo_dir(cache_dir, book.repo) / "collections" / book.collection


def module_path(cache_dir: Path, book: OpenStaxBook, module_id: str) -> Path:
    """Path of one module's CNXML in a book's checkout."""
    return repo_dir(cache_dir, book.repo) / "modules" / module_id / "index.cnxml"


def _git(directory: Path, *args: str) -> str:
    """Run one git command in ``directory`` and return its stdout."""
    result = subprocess.run(
        ["git", "-C", str(directory), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def checked_out_commit(directory: Path) -> str:
    """The commit a checkout is at, or ``""`` if it is not a checkout yet."""
    if not (directory / ".git").exists():
        return ""
    try:
        return _git(directory, "rev-parse", "HEAD")
    except subprocess.CalledProcessError:
        return ""


def checkout_pinned(directory: Path, repo: str, commit: str) -> None:
    """Fetch one commit of ``repo`` into ``directory`` and check its text out."""
    if not (directory / ".git").exists():
        directory.mkdir(parents=True, exist_ok=True)
        _git(directory, "init", "-q")
        _git(directory, "remote", "add", "origin", f"{GITHUB_BASE}/{repo}.git")
    _git(directory, "fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", commit)
    _git(directory, "sparse-checkout", "set", "--no-cone", *SPARSE_PATTERNS)
    _git(directory, "-c", "advice.detachedHead=false", "checkout", "-q", "--detach", commit)


def license_problems(cache_dir: Path, books: Sequence[OpenStaxBook]) -> List[str]:
    """One message per book whose checkout does not declare CC BY 4.0."""
    problems: List[str] = []
    for book in books:
        path = collection_path(cache_dir, book)
        if not path.exists():
            problems.append(f"{book.slug}: {path} is missing")
            continue
        header = path.read_text(encoding="utf-8")[:4000]
        if REQUIRED_LICENSE_URL not in header:
            problems.append(f"{book.slug}: {path.name} does not declare CC BY 4.0")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        choices=corpus_choices(),
        default="all",
        help="Which corpus's books to download (default: all)",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help=f"Cache directory (default: {default_cache_dir()})",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report what would happen, touching nothing"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    cache_dir: Path = args.dest or default_cache_dir()
    books = get_books(args.corpus)
    pins = repo_pins(books)

    for repo, commit in sorted(pins.items()):
        directory = repo_dir(cache_dir, repo)
        if checked_out_commit(directory) == commit:
            logger.info("%s: already at %s", repo, commit[:10])
            continue
        if args.dry_run:
            print(f"Would check out {repo} at {commit[:10]} into {directory}")
            continue
        logger.info("%s: fetching %s", repo, commit[:10])
        try:
            checkout_pinned(directory, repo, commit)
        except subprocess.CalledProcessError as error:
            logger.error("%s: git failed: %s", repo, (error.stderr or "").strip())
            return 1

    if args.dry_run:
        return 0

    problems = license_problems(cache_dir, books)
    for problem in problems:
        logger.error(problem)
    if problems:
        return 1
    logger.info("%d books in %d repositories, all CC BY 4.0", len(books), len(pins))
    return 0


if __name__ == "__main__":
    sys.exit(main())
