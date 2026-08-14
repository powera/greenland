#!/usr/bin/env python3
"""Generate localized categorychoice-{lang}.json files from the English source.

The English ``data/categorychoice.json`` is the source of truth. For each
target source-language, this script translates the ``label`` and each entry
in ``groups`` via ``storage.models.enum_translations``.

Mapping rule for ``groups``: each English group string must match a value in
``en.SUBTYPE_DISPLAY``. We reverse that map to find the subtype key, then look
it up in the target language's ``SUBTYPE_DISPLAY`` to get the localized group
string. If any English group has no reverse mapping, we fail loudly — that
indicates drift between ``categorychoice.json`` and ``en.SUBTYPE_DISPLAY``
that must be reconciled at the source.

Mapping rule for ``label``: set ``label = SUBTYPE_DISPLAY[subtype]`` in the
target language. This loses the nicer plural/prose phrasing of the English
labels but keeps the file fully automatable. The ``id`` and ``avoidDecoys``
fields are preserved verbatim.

Usage:
    PYTHONPATH=src python src/exports/wireword/generate_categorychoice.py
    PYTHONPATH=src python src/exports/wireword/generate_categorychoice.py --langs fr es
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from storage.models.enum_translations import en as en_translations
from storage.models.enum_translations import get_subtype_display_name

DEFAULT_LANGS = ("es", "fr", "zh")
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
EN_SOURCE = DATA_DIR / "categorychoice.json"


def build_reverse_subtype_map() -> Dict[str, str]:
    """Build a value -> subtype key map from en.SUBTYPE_DISPLAY.

    Raises if there are duplicate display values that would make the reverse
    mapping ambiguous (excluding the ``__other__`` alias).
    """
    reverse: Dict[str, str] = {}
    duplicates: Dict[str, List[str]] = {}
    for subtype, display in en_translations.SUBTYPE_DISPLAY.items():
        if subtype == "__other__":
            continue
        if display in reverse:
            duplicates.setdefault(display, [reverse[display]]).append(subtype)
        else:
            reverse[display] = subtype
    if duplicates:
        msg = "\n".join(f"  {disp!r}: {keys}" for disp, keys in duplicates.items())
        raise ValueError(f"Ambiguous reverse mapping in en.SUBTYPE_DISPLAY:\n{msg}")
    return reverse


def generate_for_language(
    en_data: Dict[str, Any], reverse_map: Dict[str, str], lang: str
) -> Dict[str, Any]:
    """Build the localized config dict for *lang*."""
    out_categories: List[Dict[str, Any]] = []
    for entry in en_data.get("categories", []):
        en_groups: List[str] = entry["groups"]
        if not en_groups:
            raise ValueError(f"Category {entry['id']!r} has empty groups[]")

        subtypes: List[str] = []
        for g in en_groups:
            if g not in reverse_map:
                raise ValueError(
                    f"Category {entry['id']!r}: group {g!r} not found in "
                    f"en.SUBTYPE_DISPLAY values. Fix categorychoice.json or "
                    f"en.SUBTYPE_DISPLAY so they agree."
                )
            subtypes.append(reverse_map[g])

        localized_groups = [get_subtype_display_name(s, lang) for s in subtypes]
        # Use the first subtype's display as the localized label.
        localized_label = get_subtype_display_name(subtypes[0], lang)

        out_categories.append(
            {
                "id": entry["id"],
                "label": localized_label,
                "groups": localized_groups,
                "avoidDecoys": list(entry.get("avoidDecoys", [])),
            }
        )
    return {"categories": out_categories}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--langs",
        nargs="+",
        default=list(DEFAULT_LANGS),
        help=f"Target language codes (default: {' '.join(DEFAULT_LANGS)})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DATA_DIR,
        help="Directory to write categorychoice-{lang}.json files (default: data/)",
    )
    args = parser.parse_args()

    if not EN_SOURCE.exists():
        print(f"error: missing source file {EN_SOURCE}", file=sys.stderr)
        return 1

    with EN_SOURCE.open("r", encoding="utf-8") as f:
        en_data = json.load(f)

    reverse_map = build_reverse_subtype_map()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for lang in args.langs:
        if lang == "en":
            print("skipping 'en' (source file)")
            continue
        out = generate_for_language(en_data, reverse_map, lang)
        out_path = args.output_dir / f"categorychoice-{lang}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"wrote {out_path} ({len(out['categories'])} categories)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
