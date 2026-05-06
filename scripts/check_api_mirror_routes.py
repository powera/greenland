#!/usr/bin/env python3
"""Check that mirrored route path/method metadata matches between barsukas and api."""

import ast
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent

BARSUKAS_FILES = [
    "src/barsukas/routes/lemmas.py",
    "src/barsukas/routes/sentences.py",
    "src/barsukas/routes/translations.py",
    "src/barsukas/routes/audio.py",
    "src/barsukas/routes/batch_operations.py",
    "src/barsukas/routes/llm_api.py",
]

API_FILES = [
    "api/lemmas.py",
    "api/sentences.py",
    "api/translations.py",
    "api/audio.py",
    "api/batch_operations.py",
    "api/llm_agents.py",
]


def _extract_mirror_pairs(file_paths: Iterable[str], decorator_name: str) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for rel_path in file_paths:
        source = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=rel_path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Name):
                    continue
                if dec.func.id != decorator_name or len(dec.args) < 2:
                    continue
                route_arg = dec.args[0]
                method_arg = dec.args[1]
                if not (
                    isinstance(route_arg, ast.Constant)
                    and isinstance(route_arg.value, str)
                    and isinstance(method_arg, ast.Constant)
                    and isinstance(method_arg.value, str)
                ):
                    raise ValueError(f"{rel_path}:{node.lineno} has non-literal mirror metadata")
                pairs.add((route_arg.value, method_arg.value.upper()))
    return pairs


def main() -> int:
    barsukas_pairs = _extract_mirror_pairs(BARSUKAS_FILES, "mirrored_by_api")
    api_pairs = _extract_mirror_pairs(API_FILES, "mirrored_route")

    missing_in_api = barsukas_pairs - api_pairs
    missing_in_barsukas = api_pairs - barsukas_pairs

    if missing_in_api or missing_in_barsukas:
        if missing_in_api:
            print("Missing in api decorators:")
            for route_path, method in sorted(missing_in_api):
                print(f"  - {method} {route_path}")
        if missing_in_barsukas:
            print("Missing in barsukas decorators:")
            for route_path, method in sorted(missing_in_barsukas):
                print(f"  - {method} {route_path}")
        return 1

    print(f"OK: {len(api_pairs)} mirrored route path/method pairs match.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
