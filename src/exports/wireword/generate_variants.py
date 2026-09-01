#!/usr/bin/env python3
"""WireWord regional-variant registry generator.

Emits ``variants.json``, the file that tells a client which regional varieties
of a language exist and which data directory each one's wirewords live in.

It is written into the **base** language's wireword output directory only
(``lang_es/generated/wireword/variants.json``); variant directories carry no
copy, because the registry is what decides which variant directory to load and
so has to be readable before any variant is chosen.

**A missing file means "one variant."**  A language with no regional varieties
emits nothing at all and the client keeps its single-variant behavior, so this
generator returns ``(True, None)`` rather than writing an empty registry.

The registry is built from ``langtools.dialect_overrides``: the base language's
entry in ``BASE_VARIANTS`` plus every storage dialect of it that carries picker
metadata.  Presentation dialects (es-mx) are deliberately excluded -- they store
no wirewords of their own, so there is no directory for a client to load.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add the src directory to the path for imports
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from langtools.dialect_overrides import (
    BASE_VARIANTS,
    get_dialect_override,
    get_dialects_for_language,
    normalize_language_code,
)

logger = logging.getLogger(__name__)

VARIANTS_FILENAME = "variants.json"

# Schema version of the emitted registry.  Bump only alongside a client that
# understands the new shape.
VARIANTS_SCHEMA_VERSION = 1


def get_variant_directory(lang_code: str) -> str:
    """Return the served data directory name for *lang_code*.

    The client has no naming rule of its own -- it loads whatever ``directory``
    says -- but the name has to match what the app's sync step writes, which
    is the language name with the region subtag appended by underscore:
    ``es`` -> ``spanish``, ``es-419`` -> ``spanish_419``.

    >>> get_variant_directory("es")
    'spanish'
    >>> get_variant_directory("es-419")
    'spanish_419'
    """
    from storage.translation_helpers import LANGUAGE_NAMES

    normalized = normalize_language_code(lang_code)
    override = get_dialect_override(normalized)
    base = override.parent_lang if override else normalized

    base_name = LANGUAGE_NAMES.get(base, base).lower()
    if not override:
        return base_name

    # "es-419" -> "419"; the region subtag is everything after the first dash.
    region = normalized.split("-", 1)[1].lower()
    return f"{base_name}_{region}"


def _base_variant_entry(base_lang: str) -> Optional[Dict[str, Any]]:
    """Build the registry entry for the language's own unmarked variety."""
    base = BASE_VARIANTS.get(base_lang)
    if base is None:
        return None

    entry: Dict[str, Any] = {
        "id": base_lang,
        "directory": get_variant_directory(base_lang),
        "language_code": base.language_code,
    }
    if base.speech_locale:
        entry["speech_locale"] = base.speech_locale
    entry["display_name"] = base.name
    entry["native_name"] = base.native_name
    entry["description"] = base.description
    if base.flag:
        entry["flag"] = base.flag
    entry["default_regions"] = list(base.regions)
    entry["source_languages"] = ["en"]
    return entry


def _dialect_variant_entry(dialect_code: str) -> Optional[Dict[str, Any]]:
    """Build the registry entry for one storage dialect.

    Returns ``None`` for a dialect that stores no wirewords of its own, or that
    carries no picker metadata -- neither is something a client can select.
    """
    override = get_dialect_override(dialect_code)
    if override is None or not override.translation_target:
        return None
    if not override.variant_name:
        return None

    entry: Dict[str, Any] = {
        "id": dialect_code,
        "directory": get_variant_directory(dialect_code),
        "language_code": dialect_code,
    }
    if override.speech_locale:
        entry["speech_locale"] = override.speech_locale
    entry["display_name"] = override.variant_name
    entry["native_name"] = override.variant_native_name
    entry["description"] = override.variant_description
    if override.variant_flag:
        entry["flag"] = override.variant_flag
    entry["default_regions"] = list(override.variant_regions)
    entry["source_languages"] = ["en"]
    return entry


def build_variants_registry(language: str) -> Optional[Dict[str, Any]]:
    """Build the ``variants.json`` payload for a base *language*.

    Returns ``None`` when the language has no regional varieties to offer, or
    when it is itself a dialect (a variant directory carries no registry).  A
    single-entry registry is also returned as ``None``: the client treats one
    variant exactly like a missing file, so emitting it would only add a fetch.
    """
    normalized = normalize_language_code(language)

    # A dialect's own directory gets no registry -- only the base language's.
    if get_dialect_override(normalized) is not None:
        return None

    base_entry = _base_variant_entry(normalized)
    if base_entry is None:
        return None

    variants: List[Dict[str, Any]] = [base_entry]
    for dialect_code in get_dialects_for_language(normalized):
        entry = _dialect_variant_entry(dialect_code)
        if entry is not None:
            variants.append(entry)

    if len(variants) < 2:
        return None

    from storage.translation_helpers import LANGUAGE_NAMES

    return {
        "version": VARIANTS_SCHEMA_VERSION,
        # The base language name, matching the directory this is served from.
        "language": LANGUAGE_NAMES.get(normalized, normalized).lower(),
        "default_variant": normalized,
        "variants": variants,
    }


def generate_variants(wireword_dir: str, language: str) -> Tuple[bool, Optional[str]]:
    """Write ``variants.json`` into *wireword_dir* for a base *language*.

    Args:
        wireword_dir: The wireword output directory for the base language.
        language: Language code (e.g. ``"es"``).

    Returns:
        Tuple of (success flag, path written).  The path is ``None`` when the
        language has no regional varieties -- which is a success, not a
        failure: shipping no file is how a single-variant language is spelled.
    """
    registry = build_variants_registry(language)
    if registry is None:
        logger.debug("No regional variants for %s; not emitting %s", language, VARIANTS_FILENAME)
        return True, None

    variants_path = os.path.join(wireword_dir, VARIANTS_FILENAME)
    try:
        with open(variants_path, "w", encoding="utf-8") as f:
            json.dump(registry, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except OSError:
        logger.exception("Failed to write %s", variants_path)
        return False, None

    logger.info("  Wrote %s with %d variants", VARIANTS_FILENAME, len(registry["variants"]))
    return True, variants_path
