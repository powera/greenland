#!/usr/bin/env python3
"""Replace legacy release booleans with reviewed concept dimensions; no SQLite access.

Run with GREENLAND_DISABLE_LLM=1 PYTHONPATH=src python migrations/20261012_migrate_noun_concept_facts.py --apply
Without --apply, validate coverage and report pending replacements. Safe to rerun.
"""

import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import argparse
import json
from typing import Dict, List, Tuple

from storage.config.lemma_fact_registry import RETIRED_LEMMA_FACT_TYPES, validate_lemma_fact

# Individually reviewed against each release concept_definition, not inferred
# from a legacy boolean. The current legacy inventory consists entirely of
# individual animals and whole food items. Unknown legacy GUIDs require review.
# GUID -> (expected concept label, individuation, concreteness)
REVIEWED_SENSES: Dict[str, Tuple[str, str, str]] = {
    "N02_001": ("dog", "individual", "physical"),
    "N02_002": ("cat", "individual", "physical"),
    "N02_003": ("bird", "individual", "physical"),
    "N02_004": ("horse", "individual", "physical"),
    "N02_005": ("cow", "individual", "physical"),
    "N02_006": ("pig", "individual", "physical"),
    "N02_008": ("mouse (animal)", "individual", "physical"),
    "N02_009": ("bear", "individual", "physical"),
    "N02_010": ("wolf", "individual", "physical"),
    "N02_011": ("rabbit", "individual", "physical"),
    "N02_013": ("tiger", "individual", "physical"),
    "N02_014": ("snake", "individual", "physical"),
    "N02_015": ("elephant", "individual", "physical"),
    "N02_018": ("spider", "individual", "physical"),
    "N02_020": ("goat", "individual", "physical"),
    "N02_022": ("duck", "individual", "physical"),
    "N02_023": ("frog", "individual", "physical"),
    "N02_028": ("sheep", "individual", "physical"),
    "N02_035": ("lion", "individual", "physical"),
    "N02_039": ("bee", "individual", "physical"),
    "N06_009": ("egg", "individual", "physical"),
    "N06_014": ("potato", "individual", "physical"),
    "N06_015": ("apple", "individual", "physical"),
    "N06_016": ("banana", "individual", "physical"),
    "N06_018": ("tomato", "individual", "physical"),
    "N06_019": ("onion", "individual", "physical"),
    "N06_027": ("sandwich", "individual", "physical"),
    "N06_042": ("lemon", "individual", "physical"),
    "N06_044": ("grape", "individual", "physical"),
    "N06_084": ("carrot", "individual", "physical"),
}


def migrate_release(
    release_path: Path,
    *,
    apply: bool = False,
    reviewed_senses: Dict[str, Tuple[str, str, str]] = REVIEWED_SENSES,
) -> int:
    """Preflight the entire inventory before writing; return changed lemma count."""
    pending: List[Tuple[Path, str]] = []
    seen: set[str] = set()
    changed = 0
    for path in sorted(release_path.rglob("*.jsonl")):
        output: List[str] = []
        file_changed = False
        for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
            if not line.strip():
                output.append(line)
                continue
            record = json.loads(line)
            facts = record.get("facts") or {}
            guid = record.get("guid")
            legacy = RETIRED_LEMMA_FACT_TYPES.intersection(facts)
            if legacy and (guid not in reviewed_senses or "concept_label" not in record):
                raise ValueError(f"Unreviewed legacy fact on {guid} in {path}")
            if guid not in reviewed_senses or "concept_label" not in record:
                output.append(line)
                continue
            if guid in seen:
                raise ValueError(f"Duplicate reviewed GUID {guid}")
            seen.add(guid)
            label, individuation, concreteness = reviewed_senses[guid]
            if record.get("concept_label") != label or record.get("pos_type") != "noun":
                raise ValueError(f"Sense changed for {guid}; review {label!r} again")
            dimensions = {"individuation": individuation, "concreteness": concreteness}
            for fact_type, fact_value in dimensions.items():
                error = validate_lemma_fact(fact_type, fact_value)
                if error:
                    raise ValueError(error)
                if fact_type in facts and facts[fact_type] != fact_value:
                    raise ValueError(f"Conflicting {fact_type} on {guid}; review required")
            if not legacy and not all(facts.get(k) == v for k, v in dimensions.items()):
                raise ValueError(f"Missing source facts on reviewed sense {guid}")
            if legacy:
                record["facts"] = {
                    k: v for k, v in facts.items() if k not in RETIRED_LEMMA_FACT_TYPES
                }
                record["facts"].update(dimensions)
                record["facts"] = dict(sorted(record["facts"].items()))
                output.append(
                    json.dumps(record, ensure_ascii=False) + ("\n" if line.endswith("\n") else "")
                )
                changed += 1
                file_changed = True
            else:
                output.append(line)
        if file_changed:
            pending.append((path, "".join(output)))
    absent = set(reviewed_senses) - seen
    if absent:
        raise ValueError(f"Reviewed senses absent from release: {sorted(absent)}")
    if apply:
        for path, content in pending:
            path.write_text(content, encoding="utf-8")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-path", type=Path, default=SOURCE_ROOT.parent / "data/release")
    parser.add_argument(
        "--apply", action="store_true", help="Write reviewed replacements to release files"
    )
    args = parser.parse_args()
    changed = migrate_release(args.release_path, apply=args.apply)
    print(
        f"{'Migrated' if args.apply else 'Would migrate'} {changed} senses; {len(REVIEWED_SENSES)} reviewed senses verified"
    )


if __name__ == "__main__":
    main()
