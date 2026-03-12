"""Load Lithuanian verb principal parts from data/release/lemmas/verbs/*/lt.jsonl.

Each lt.jsonl line has: {"guid": "V02_001", "3p_present": "gamina", "3p_past": "gamino"}

The loaded data is cached in a module-level dict keyed by GUID.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Cached principal parts: guid -> (3p_present, 3p_past)
_PRINCIPAL_PARTS: Optional[Dict[str, Tuple[str, str]]] = None

_DATA_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "release" / "lemmas" / "verbs"
)


def _load_principal_parts() -> Dict[str, Tuple[str, str]]:
    """Scan all data/release/lemmas/verbs/*/lt.jsonl files and load principal parts."""
    parts: Dict[str, Tuple[str, str]] = {}

    if not _DATA_DIR.is_dir():
        logger.debug("Principal parts data directory not found: %s", _DATA_DIR)
        return parts

    for lt_file in sorted(_DATA_DIR.glob("*/lt.jsonl")):
        for line_num, line in enumerate(lt_file.read_text().splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Bad JSON in %s line %d", lt_file, line_num)
                continue

            guid = entry.get("guid", "")
            present_3p = entry.get("3p_present", "")
            past_3p = entry.get("3p_past", "")
            if guid and present_3p and past_3p:
                parts[guid] = (present_3p, past_3p)

    logger.debug("Loaded Lithuanian principal parts for %d verbs", len(parts))
    return parts


def get_principal_parts(guid: str) -> Optional[Tuple[str, str]]:
    """Look up (3p_present, 3p_past) for a verb by GUID.

    Returns None if no principal parts are available for this GUID.
    """
    global _PRINCIPAL_PARTS
    if _PRINCIPAL_PARTS is None:
        _PRINCIPAL_PARTS = _load_principal_parts()
    return _PRINCIPAL_PARTS.get(guid)
