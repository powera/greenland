#!/usr/bin/python3

"""Download the Open American National Corpus and extract chosen subcorpora.

    PYTHONPATH=src python src/wordfreq/corpora/download_oanc.py
    PYTHONPATH=src python src/wordfreq/corpora/download_oanc.py --subcorpora slate switchboard
    PYTHONPATH=src python src/wordfreq/corpora/download_oanc.py --archive ~/Downloads/OANC_GrAF.tgz

The OANC (https://anc.org/data/oanc/) is about 15M words of American English
from 1990 on, released as one GrAF archive (~660MB, ~4.8GB unpacked).  The
project describes it as freely available for research and development,
including commercial development, and asks that derived resources such as
frequency lists be contributed back.

Each document in the GrAF release is a plain-text primary file (``*.txt``)
beside standoff XML annotations.  Only the primary text is needed, so only the
``.txt`` files of the requested subcorpora are extracted, to
``<cache>/<subcorpus>/<relative path>``, which is the layout
:mod:`wordfreq.corpora.oanc_text` reads.  The cache is
``$GREENLAND_OANC_CACHE``, else ``constants.OANC_CACHE_DIR`` on the external
corpus drive (``/Volumes/Dorothy Day/data/oanc``), which must be mounted.

The download resumes (see :func:`download_europarl.download_archive`); an
archive already in place is not fetched again, and extraction skips files
already cached unless ``--force`` is given, so adding a subcorpus later costs
no network.

This script makes one live HTTP request to github.com (unless ``--archive``).
"""

import argparse
import json
import logging
import os
import sys
import tarfile
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional, Sequence

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import constants
from wordfreq.corpora.download_europarl import download_archive

logger = logging.getLogger(__name__)

OANC_RELEASE = "datasets-2026-09-25"
OANC_URL = f"https://github.com/nancyide/anc-website/releases/download/{OANC_RELEASE}/OANC_GrAF.tgz"
ARCHIVE_FILENAME = "OANC_GrAF.tgz"
MANIFEST_FILENAME = "manifest.json"
DEFAULT_SUBCORPORA = ("slate",)


def default_cache_dir() -> Path:
    """Directory holding the archive and the extracted primary texts."""
    configured = os.environ.get("GREENLAND_OANC_CACHE")
    if configured:
        return Path(configured)
    return Path(constants.OANC_CACHE_DIR)


def member_target(name: str, subcorpora: Sequence[str]) -> Optional[PurePosixPath]:
    """The cache-relative path to extract an archive member to, or ``None``.

    A primary text is a ``.txt`` file with a requested subcorpus name as one of
    its directory components (``.../written_1/journal/slate/1/Article247_3.txt``);
    it is written under that subcorpus, keeping the path below it.  Annotation
    files and other subcorpora are skipped, as are the macOS resource-fork
    files (``._Article247_3.txt``) the archive carries beside every text.
    """
    path = PurePosixPath(name)
    if path.suffix != ".txt" or path.name.startswith("._"):
        return None
    directories = [part.lower() for part in path.parts[:-1]]
    for subcorpus in subcorpora:
        if subcorpus in directories:
            index = directories.index(subcorpus)
            return PurePosixPath(subcorpus, *path.parts[index + 1 :])
    return None


def extract_subcorpora(
    archive: Path, cache_dir: Path, subcorpora: Sequence[str], *, force: bool = False
) -> Dict[str, int]:
    """Extract the primary texts of ``subcorpora`` from the archive in one pass.

    Returns:
        Files written per subcorpus (cached files not counted).
    """
    written: Dict[str, int] = {subcorpus: 0 for subcorpus in subcorpora}
    with tarfile.open(archive, mode="r|gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            target = member_target(member.name, subcorpora)
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
            written[target.parts[0]] += 1
            if sum(written.values()) % 1000 == 0:
                logger.info("  extracted %d files", sum(written.values()))
    return written


def write_manifest(cache_dir: Path, subcorpora: Sequence[str], archive: Path) -> None:
    """Record the release and the per-subcorpus file counts."""
    path = cache_dir / MANIFEST_FILENAME
    existing: Dict[str, object] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            pass
    previous = existing.get("subcorpora")
    merged: Dict[str, int] = dict(previous) if isinstance(previous, dict) else {}
    for subcorpus in subcorpora:
        merged[subcorpus] = len(list((cache_dir / subcorpus).rglob("*.txt")))
    payload = {
        "release": OANC_RELEASE,
        "url": OANC_URL,
        "archive": archive.name,
        "subcorpora": merged,
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
        "--subcorpora",
        nargs="+",
        default=list(DEFAULT_SUBCORPORA),
        help="OANC subcorpus directory names to extract (default: slate)",
    )
    parser.add_argument(
        "--archive",
        type=Path,
        default=None,
        help="Use an already-downloaded OANC_GrAF.tgz instead of fetching one",
    )
    parser.add_argument("--url", default=OANC_URL, help="Source archive URL")
    parser.add_argument(
        "--force", action="store_true", help="Re-extract files already in the cache"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report what would happen, touching nothing"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    cache_dir: Path = args.dest or default_cache_dir()
    archive: Path = args.archive or cache_dir / ARCHIVE_FILENAME
    subcorpora: List[str] = [name.lower() for name in args.subcorpora]

    if args.dry_run:
        action = "use" if archive.exists() else f"download {args.url} to"
        print(f"Would {action} {archive}")
        print(f"Would extract {', '.join(subcorpora)} to {cache_dir}")
        return 0

    cache_dir.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        if args.archive:
            logger.error("Archive not found: %s", archive)
            return 1
        logger.info("downloading %s", args.url)
        if not download_archive(args.url, archive):
            return 1

    logger.info("extracting %s from %s", ", ".join(subcorpora), archive)
    try:
        written = extract_subcorpora(archive, cache_dir, subcorpora, force=args.force)
    except (tarfile.TarError, OSError, EOFError) as error:
        logger.error("%s: extraction failed: %s", archive, error)
        return 1
    write_manifest(cache_dir, subcorpora, archive)
    for subcorpus, count in written.items():
        logger.info("%s: %d files extracted", subcorpus, count)
        if count == 0 and not any((cache_dir / subcorpus).rglob("*.txt")):
            logger.warning("%s: no files matched; check the subcorpus name", subcorpus)
    return 0


if __name__ == "__main__":
    sys.exit(main())
