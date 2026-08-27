#!/usr/bin/python3

"""Download Supreme Court opinions from the Caselaw Access Project.

    PYTHONPATH=src python src/wordfreq/corpora/download_scotus.py --years 1997-2006
    PYTHONPATH=src python src/wordfreq/corpora/download_scotus.py --volumes 537 538
    PYTHONPATH=src python src/wordfreq/corpora/download_scotus.py --years 2000-2004 --dry-run

Cases land in a scratch cache directory (``$GREENLAND_SCOTUS_CACHE``, else
``data/working/scotus``), never in the repository: like the Gutenberg texts
they are bulky inputs to a corpus JSON file, not artifacts worth keeping.
Already-downloaded cases are skipped unless ``--force`` is given, so a re-run
costs nothing.

CAP serves static JSON over HTTPS with no API key, unlike CourtListener, whose
v3 and v4 APIs both require a token.  Three layers matter here:

* ``VolumesMetadata.json`` lists every U.S. Reports volume.  Its ``start_year``
  and ``end_year`` are the years of the *decisions* in that volume, which is
  what selects a date range -- ``publication_year`` lags by two to four years
  and would pick the wrong volumes.
* ``<volume>/CasesMetadata.json`` lists that volume's cases, with an
  ``analysis.char_count`` for each.  Filtering on it costs no bandwidth: a
  volume holds a few hundred to a few thousand entries and almost all of them
  are one-page orders and denials of certiorari, which are near-pure
  boilerplate.
* ``<volume>/cases/<page>-01.json`` is one case.  The ``-01`` suffix
  disambiguates cases that begin on the same page; see ``--force`` below for
  why the downloaded id is checked against the metadata.

This script makes live HTTP requests to static.case.law.  It sleeps
``--delay`` seconds between them to stay a polite client.
"""

import argparse
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

logger = logging.getLogger(__name__)

CAP_BASE = "https://static.case.law/us"
DEFAULT_DELAY_SECONDS = 0.35
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_RETRIES = 3
USER_AGENT = "greenland-wordfreq-corpus-builder/1.0 (linguistic research; contact via repo)"
MANIFEST_FILENAME = "manifest.json"

# Opinions shorter than this are orders and denials of certiorari.  A volume
# holds a few hundred to a few thousand entries and typically only a few dozen
# clear the floor: volume 537 has 5541 entries and 14 opinions over 25k
# characters.  The rest carry almost no running prose.
DEFAULT_MIN_CHARS = 25000


def default_cache_dir() -> Path:
    """Directory holding downloaded cases."""
    configured = os.environ.get("GREENLAND_SCOTUS_CACHE")
    if configured:
        return Path(configured)
    return Path("data/working/scotus")


def case_path(cache_dir: Path, volume: int, first_page: Any) -> Path:
    """Path of the cached JSON for one case."""
    return cache_dir / f"case_{volume}us{first_page}.json"


def volume_metadata_path(cache_dir: Path, volume: int) -> Path:
    """Path of the cached case list for one volume."""
    return cache_dir / f"meta_vol{volume}_cases.json"


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def _get_json(
    session: requests.Session,
    url: str,
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    retries: int = DEFAULT_RETRIES,
) -> Optional[Any]:
    """Fetch and parse one JSON document, retrying transient failures."""
    for attempt in range(1, retries + 1):
        try:
            response = session.get(url, timeout=timeout)
        except requests.RequestException as error:
            logger.warning("%s: %s (attempt %d/%d)", url, error, attempt, retries)
            continue
        if response.status_code == 404:
            logger.warning("%s: not found", url)
            return None
        if response.status_code != 200:
            logger.warning(
                "%s: HTTP %d (attempt %d/%d)", url, response.status_code, attempt, retries
            )
            continue
        try:
            return response.json()
        except ValueError as error:
            logger.warning("%s: bad JSON: %s", url, error)
            return None
    return None


def volumes_for_years(session: requests.Session, start_year: int, end_year: int) -> List[int]:
    """U.S. Reports volumes holding decisions between two years, inclusive.

    Uses ``start_year``/``end_year`` from the volume metadata, which are
    decision years.  ``publication_year`` is the year the bound volume was
    printed -- two to four years later -- and selecting on it silently returns
    the wrong volumes.
    """
    payload = _get_json(session, f"{CAP_BASE}/VolumesMetadata.json")
    if not payload:
        return []
    volumes: List[int] = []
    for entry in payload:
        try:
            number = int(entry["volume_number"])
        except (KeyError, TypeError, ValueError):
            continue
        first = entry.get("start_year")
        last = entry.get("end_year")
        if not first or not last:
            continue
        if last < start_year or first > end_year:
            continue
        volumes.append(number)
    return sorted(volumes)


def load_volume_cases(
    session: requests.Session,
    volume: int,
    cache_dir: Path,
    *,
    delay: float = DEFAULT_DELAY_SECONDS,
) -> List[Dict[str, Any]]:
    """Case list for one volume, from the cache when it is already there."""
    path = volume_metadata_path(cache_dir, volume)
    if path.exists():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(cached, list):
                return cached
        except ValueError:
            logger.warning("%s: unreadable, refetching", path)
    payload = _get_json(session, f"{CAP_BASE}/{volume}/CasesMetadata.json")
    time.sleep(delay)
    if not isinstance(payload, list):
        return []
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def select_opinions(
    cases: Sequence[Dict[str, Any]], *, min_chars: int = DEFAULT_MIN_CHARS
) -> List[Dict[str, Any]]:
    """Cases long enough to be argued opinions rather than orders."""
    selected = []
    for case in cases:
        analysis = case.get("analysis") or {}
        if int(analysis.get("char_count") or 0) >= min_chars:
            selected.append(case)
    return selected


def download_case(
    session: requests.Session,
    volume: int,
    case: Dict[str, Any],
    cache_dir: Path,
    *,
    force: bool = False,
    delay: float = DEFAULT_DELAY_SECONDS,
) -> Tuple[str, Optional[Path]]:
    """Download one case, returning ``(status, path)``.

    ``status`` is ``"cached"``, ``"downloaded"``, ``"collision"`` or
    ``"failed"``.  A *collision* is a case whose page holds more than one
    case: CAP's ``-01`` suffix then names a different case than the metadata
    row, so the downloaded id does not match and the file is discarded rather
    than silently feeding the corpus the wrong text.
    """
    first_page = case.get("first_page")
    path = case_path(cache_dir, volume, first_page)
    if path.exists() and not force:
        return "cached", path

    page = str(first_page).zfill(4)
    payload = _get_json(session, f"{CAP_BASE}/{volume}/cases/{page}-01.json")
    time.sleep(delay)
    if not isinstance(payload, dict):
        return "failed", None

    if payload.get("id") != case.get("id"):
        logger.warning(
            "volume %d page %s: got case %s (%s), expected %s (%s) - page collision",
            volume,
            first_page,
            payload.get("id"),
            str(payload.get("name_abbreviation"))[:40],
            case.get("id"),
            str(case.get("name_abbreviation"))[:40],
        )
        return "collision", None

    path.write_text(json.dumps(payload), encoding="utf-8")
    return "downloaded", path


def write_manifest(cache_dir: Path, entries: Dict[str, Dict[str, Any]]) -> None:
    """Record what was downloaded, mirroring the Gutenberg cache's manifest."""
    path = cache_dir / MANIFEST_FILENAME
    existing: Dict[str, Any] = {"cases": {}}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            pass
    cases = existing.get("cases") or {}
    cases.update(entries)
    path.write_text(json.dumps({"cases": cases}, indent=1, sort_keys=True), encoding="utf-8")


def parse_years(value: str) -> Tuple[int, int]:
    """Parse ``--years 1997-2006`` (or a single year) into a range."""
    if "-" in value:
        first, _, last = value.partition("-")
        return int(first), int(last)
    year = int(value)
    return year, year


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--years", type=parse_years, help="Decision years to cover, e.g. 1997-2006"
    )
    selection.add_argument(
        "--volumes", type=int, nargs="+", help="U.S. Reports volume numbers to download"
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help=f"Cache directory (default: {default_cache_dir()})",
    )
    parser.add_argument(
        "--min-chars",
        type=int,
        default=DEFAULT_MIN_CHARS,
        help=f"Skip cases shorter than this (default: {DEFAULT_MIN_CHARS})",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY_SECONDS,
        help=f"Seconds between requests (default: {DEFAULT_DELAY_SECONDS})",
    )
    parser.add_argument(
        "--force", action="store_true", help="Re-download cases already in the cache"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be downloaded, fetching only metadata",
    )
    parser.add_argument("--verbose", action="store_true", help="Log every case")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    cache_dir = args.dest or default_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    session = _session()

    if args.volumes:
        volumes = sorted(args.volumes)
    else:
        start_year, end_year = args.years
        volumes = volumes_for_years(session, start_year, end_year)
        if not volumes:
            logger.error("No volumes found for %d-%d", start_year, end_year)
            return 1
        logger.info(
            "Decisions %d-%d: volumes %d-%d (%d volumes)",
            start_year,
            end_year,
            volumes[0],
            volumes[-1],
            len(volumes),
        )

    counts = {"cached": 0, "downloaded": 0, "collision": 0, "failed": 0}
    manifest: Dict[str, Dict[str, Any]] = {}

    for volume in volumes:
        cases = load_volume_cases(session, volume, cache_dir, delay=args.delay)
        opinions = select_opinions(cases, min_chars=args.min_chars)
        logger.info(
            "volume %d: %d entries, %d over %d chars",
            volume,
            len(cases),
            len(opinions),
            args.min_chars,
        )
        if args.dry_run:
            continue
        for case in opinions:
            status, path = download_case(
                session, volume, case, cache_dir, force=args.force, delay=args.delay
            )
            counts[status] += 1
            if args.verbose:
                logger.debug("  %-10s %s", status, case.get("name_abbreviation"))
            if path is not None:
                manifest[str(case.get("id"))] = {
                    "volume": volume,
                    "first_page": case.get("first_page"),
                    "name": case.get("name_abbreviation"),
                    "decision_date": case.get("decision_date"),
                    "char_count": (case.get("analysis") or {}).get("char_count"),
                    "file": path.name,
                }

    if not args.dry_run:
        write_manifest(cache_dir, manifest)
        logger.info(
            "downloaded %d, cached %d, collisions %d, failed %d",
            counts["downloaded"],
            counts["cached"],
            counts["collision"],
            counts["failed"],
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
