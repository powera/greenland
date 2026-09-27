#!/usr/bin/python3

"""Download the Europarl source release and extract its session files.

    PYTHONPATH=src python src/wordfreq/corpora/download_europarl.py
    PYTHONPATH=src python src/wordfreq/corpora/download_europarl.py --languages en lt
    PYTHONPATH=src python src/wordfreq/corpora/download_europarl.py --archive ~/Downloads/europarl.tgz

Europarl is published as one tarball holding every language (about 1.5GB),
not one file per language, so this is a single large download rather than
the thousands of small requests ``download_scotus`` makes.  The archive lands
in the cache directory (``$GREENLAND_EUROPARL_CACHE``, else
``data/working/europarl``), and the requested languages are extracted beside it
as ``txt/<lang>/ep-*.txt`` -- the layout :mod:`wordfreq.corpora.europarl_text`
reads.

The download resumes: an interrupted transfer leaves ``europarl.tgz.part``,
and the next run asks the server for the remaining bytes.  An archive already
in place is not downloaded again, and extraction skips files already cached
unless ``--force`` is given, so a re-run to add a language costs no network.
``--archive`` points at a copy fetched by hand and skips the download.

Only English is needed for the corpus.  The other languages are the same
debates, sentence-parallel, which is why ``--languages`` exists: Lithuanian
and the rest are a source of translated example sentences later.

This script makes one live HTTP request to statmt.org (unless ``--archive``).
"""

import argparse
import json
import logging
import os
import sys
import tarfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests

logger = logging.getLogger(__name__)

EUROPARL_VERSION = "v7"
EUROPARL_URL = "https://www.statmt.org/europarl/v7/europarl.tgz"
ARCHIVE_FILENAME = "europarl.tgz"
MANIFEST_FILENAME = "manifest.json"
DEFAULT_TIMEOUT_SECONDS = 120
CHUNK_BYTES = 1 << 20
PROGRESS_EVERY_BYTES = 100 << 20
USER_AGENT = "greenland-wordfreq-corpus-builder/1.0 (linguistic research; contact via repo)"


def default_cache_dir() -> Path:
    """Directory holding the archive and the extracted session files."""
    configured = os.environ.get("GREENLAND_EUROPARL_CACHE")
    if configured:
        return Path(configured)
    return Path("data/working/europarl")


def download_archive(
    url: str, destination: Path, *, timeout: int = DEFAULT_TIMEOUT_SECONDS
) -> bool:
    """Download ``url`` to ``destination``, resuming a previous partial transfer.

    Returns:
        True when ``destination`` holds the complete archive.
    """
    partial = destination.with_name(destination.name + ".part")
    offset = partial.stat().st_size if partial.exists() else 0
    headers = {"User-Agent": USER_AGENT}
    if offset:
        headers["Range"] = f"bytes={offset}-"
        logger.info("resuming %s at %.1f MB", partial.name, offset / (1 << 20))

    try:
        response = requests.get(url, headers=headers, stream=True, timeout=timeout)
    except requests.RequestException as error:
        logger.error("%s: %s", url, error)
        return False

    with response:
        if response.status_code == 416:
            # The partial file already holds every byte.
            partial.rename(destination)
            return True
        if response.status_code == 200 and offset:
            logger.warning("server ignored the range request; restarting from zero")
            offset = 0
        elif response.status_code not in (200, 206):
            logger.error("%s: HTTP %d", url, response.status_code)
            return False

        length = response.headers.get("Content-Length")
        total = offset + int(length) if length and length.isdigit() else None
        if total:
            logger.info("archive: %.1f MB", total / (1 << 20))

        written = offset
        next_report = written + PROGRESS_EVERY_BYTES
        try:
            with open(partial, "ab" if offset else "wb") as handle:
                for chunk in response.iter_content(chunk_size=CHUNK_BYTES):
                    handle.write(chunk)
                    written += len(chunk)
                    if written >= next_report:
                        suffix = f" / {total / (1 << 20):.0f}" if total else ""
                        logger.info("  %.0f%s MB", written / (1 << 20), suffix)
                        next_report += PROGRESS_EVERY_BYTES
        except requests.RequestException as error:
            logger.error("transfer interrupted at %.1f MB: %s", written / (1 << 20), error)
            return False

    if total is not None and written < total:
        logger.error("short read: %d of %d bytes; re-run to resume", written, total)
        return False
    partial.rename(destination)
    return True


def member_target(name: str, languages: Sequence[str]) -> Optional[str]:
    """The cache-relative path to extract an archive member to, or ``None``.

    Members are ``txt/<lang>/ep-*.txt``, sometimes under a leading
    ``europarl/`` directory; anything else in the archive (tools, other
    languages) is skipped.
    """
    parts = Path(name).parts
    for index in range(len(parts) - 2):
        if parts[index] == "txt" and parts[index + 1] in languages:
            filename = parts[-1]
            if index + 3 == len(parts) and filename.startswith("ep-") and filename.endswith(".txt"):
                return str(Path("txt", parts[index + 1], filename))
    return None


def extract_languages(
    archive: Path, cache_dir: Path, languages: Sequence[str], *, force: bool = False
) -> Dict[str, int]:
    """Extract the session files of ``languages`` from the archive.

    The tarball is read as a stream (``r|gz``), so extraction is one pass over
    the file with nothing held in memory but the current member.

    Returns:
        Files written per language (cached files not counted).
    """
    written: Dict[str, int] = {language: 0 for language in languages}
    with tarfile.open(archive, mode="r|gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            target = member_target(member.name, languages)
            if target is None:
                continue
            path = cache_dir / target
            if path.exists() and not force:
                continue
            source = tar.extractfile(member)
            if source is None:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(source.read())
            written[path.parent.name] += 1
            if sum(written.values()) % 1000 == 0:
                logger.info("  extracted %d files", sum(written.values()))
    return written


def write_manifest(cache_dir: Path, languages: Sequence[str], archive: Path) -> None:
    """Record the release and the per-language file counts."""
    counts = {
        language: len(list((cache_dir / "txt" / language).glob("ep-*.txt")))
        for language in languages
    }
    path = cache_dir / MANIFEST_FILENAME
    existing: Dict[str, object] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            pass
    previous = existing.get("languages")
    merged: Dict[str, int] = dict(previous) if isinstance(previous, dict) else {}
    merged.update(counts)
    payload = {
        "version": EUROPARL_VERSION,
        "url": EUROPARL_URL,
        "archive": archive.name,
        "languages": merged,
    }
    path.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help=f"Cache directory (default: {default_cache_dir()})",
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        default=["en"],
        help="Europarl language codes to extract (default: en)",
    )
    parser.add_argument(
        "--archive",
        type=Path,
        default=None,
        help="Use an already-downloaded europarl.tgz instead of fetching one",
    )
    parser.add_argument("--url", default=EUROPARL_URL, help="Source archive URL")
    parser.add_argument(
        "--force", action="store_true", help="Re-extract files already in the cache"
    )
    parser.add_argument(
        "--delete-archive",
        action="store_true",
        help="Delete the downloaded archive after a successful extraction",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report what would happen, touching nothing"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    cache_dir: Path = args.dest or default_cache_dir()
    archive: Path = args.archive or cache_dir / ARCHIVE_FILENAME
    languages: List[str] = [code.lower() for code in args.languages]

    if args.dry_run:
        action = "use" if archive.exists() else f"download {args.url} to"
        print(f"Would {action} {archive}")
        print(f"Would extract {', '.join(languages)} to {cache_dir / 'txt'}")
        return 0

    cache_dir.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        if args.archive:
            logger.error("Archive not found: %s", archive)
            return 1
        logger.info("downloading %s", args.url)
        if not download_archive(args.url, archive):
            return 1

    logger.info("extracting %s from %s", ", ".join(languages), archive)
    try:
        written = extract_languages(archive, cache_dir, languages, force=args.force)
    except (tarfile.TarError, OSError, EOFError) as error:
        logger.error("%s: extraction failed: %s", archive, error)
        return 1
    write_manifest(cache_dir, languages, archive)
    for language, count in written.items():
        logger.info("%s: %d files extracted", language, count)

    if args.delete_archive and not args.archive:
        archive.unlink()
        logger.info("deleted %s", archive)
    return 0


if __name__ == "__main__":
    sys.exit(main())
