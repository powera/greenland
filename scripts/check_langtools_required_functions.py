#!/usr/bin/env python3
"""Validate required langtools functions for selected languages.

Currently enforced for: es, fr, lt.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_FUNCTIONS: dict[str, dict[str, tuple[str, ...]]] = {
    "es": {
        "llm_forms.py": (
            "get_noun_forms",
            "get_verb_forms",
        ),
        "directions.py": ("get_general_direction_note",),
        "utils.py": ("strip_subject_pronoun",),
    },
    "fr": {
        "llm_forms.py": (
            "get_noun_forms",
            "get_verb_forms",
        ),
        "directions.py": ("get_general_direction_note",),
        "utils.py": ("strip_subject_pronoun",),
    },
    "lt": {
        "llm_forms.py": (
            "get_noun_forms",
            "get_verb_forms",
            "get_adjective_forms",
            "get_adverb_forms",
        ),
        "directions.py": ("get_general_direction_note",),
        "utils.py": ("strip_subject_pronoun",),
    },
}


def get_defined_functions(file_path: Path) -> set[str]:
    parsed = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    return {
        node.name
        for node in parsed.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def main() -> int:
    errors: list[str] = []

    for language_code, file_requirements in REQUIRED_FUNCTIONS.items():
        language_dir = ROOT / "src" / "langtools" / language_code

        for file_name, required_names in file_requirements.items():
            file_path = language_dir / file_name
            if not file_path.exists():
                errors.append(f"Missing file: {file_path.relative_to(ROOT)}")
                continue

            available = get_defined_functions(file_path)
            for function_name in required_names:
                if function_name not in available:
                    rel_path = file_path.relative_to(ROOT)
                    errors.append(f"Missing function '{function_name}' in {rel_path}")

    if errors:
        print("Langtools required-function check failed:")
        for message in errors:
            print(f"  - {message}")
        return 1

    print("Langtools required-function check passed (es/fr/lt).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
