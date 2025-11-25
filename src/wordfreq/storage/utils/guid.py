"""GUID generation utilities for lemmas."""

from wordfreq.storage.models.guid_prefixes import SUBTYPE_GUID_PREFIXES
from wordfreq.storage.models.schema import Lemma


def generate_guid(session, subtype: str) -> str:
    """
    Generate a unique GUID for a lemma in a specific subtype.

    Args:
        session: Database session
        subtype: POS subtype name (e.g., 'body_part', 'color')

    Returns:
        Unique GUID string (e.g., 'N14_001')
    """
    if subtype not in SUBTYPE_GUID_PREFIXES:
        raise ValueError(f"Unknown subtype: {subtype}")

    prefix = SUBTYPE_GUID_PREFIXES[subtype]

    # Find the highest existing GUID number for this subtype
    existing_guids = session.query(Lemma.guid)\
        .filter(Lemma.guid.like(f"{prefix}%"))\
        .filter(Lemma.guid != None)\
        .all()

    max_num = 0
    for (guid,) in existing_guids:
        if guid and guid.startswith(prefix):
            try:
                # Handle old format (A01001), dot format (A01.001), and new underscore format (A01_001)
                if "_" in guid:
                    # New format: A01_001
                    if len(guid) >= 7 and guid[3] == "_":
                        num = int(guid[4:])  # Extract the number part after the underscore
                        max_num = max(max_num, num)
                elif "." in guid:
                    # Dot format: A01.001 (for backward compatibility)
                    if len(guid) >= 7 and guid[3] == ".":
                        num = int(guid[4:])  # Extract the number part after the period
                        max_num = max(max_num, num)
                else:
                    # Old format: A01001 (for backward compatibility)
                    if len(guid) == 6:
                        num = int(guid[3:])  # Extract the number part
                        max_num = max(max_num, num)
            except ValueError:
                continue

    # Generate next GUID in new format (using underscore for valid Python variable names)
    next_num = max_num + 1
    return f"{prefix}_{next_num:03d}"
