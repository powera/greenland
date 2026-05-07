#!/usr/bin/env python3
"""Verify that mirrored route metadata matches between ``api/`` and ``src/barsukas/``.

Each facade in ``api/`` is decorated with ``@mirrored_route(path, method)``.
Each Flask route it wraps is decorated with ``@mirrored_facade(path, method)``
on the Barsukas side. The two decorators are deliberately defined separately
so neither tree imports from the other; this script pairs them by the literal
``(path, method)`` arguments and fails if either side has an unmatched entry.

Run as part of precommit. Exits 0 on match, 1 on mismatch.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Iterable, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

BARSUKAS_DIR = "src/barsukas/routes"
API_DIR = "api"

API_DECORATOR_NAME = "mirrored_route"
BARSUKAS_DECORATOR_NAME = "mirrored_facade"

RoutePair = Tuple[str, str]


def _iter_python_files(rel_dir: str) -> Iterable[Path]:
    """Yield every .py file under ``rel_dir`` (recursive), sorted for stable output."""
    base = REPO_ROOT / rel_dir
    return sorted(base.rglob("*.py"))


def _extract_pairs(file_paths: Iterable[Path], decorator_name: str) -> Set[RoutePair]:
    pairs: Set[RoutePair] = set()
    for full_path in file_paths:
        rel_path = full_path.relative_to(REPO_ROOT).as_posix()
        source = full_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=rel_path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Name):
                    continue
                if decorator.func.id != decorator_name or len(decorator.args) < 2:
                    continue
                route_arg = decorator.args[0]
                method_arg = decorator.args[1]
                if not (
                    isinstance(route_arg, ast.Constant)
                    and isinstance(route_arg.value, str)
                    and isinstance(method_arg, ast.Constant)
                    and isinstance(method_arg.value, str)
                ):
                    raise ValueError(
                        f"{rel_path}:{node.lineno}: @{decorator_name} requires literal "
                        "string arguments for path and method"
                    )
                pairs.add((route_arg.value, method_arg.value.upper()))
    return pairs


def main() -> int:
    api_pairs = _extract_pairs(_iter_python_files(API_DIR), API_DECORATOR_NAME)
    barsukas_pairs = _extract_pairs(_iter_python_files(BARSUKAS_DIR), BARSUKAS_DECORATOR_NAME)

    missing_in_api = barsukas_pairs - api_pairs
    missing_in_barsukas = api_pairs - barsukas_pairs

    if missing_in_api or missing_in_barsukas:
        if missing_in_api:
            print("Routes annotated on the Barsukas side with no matching api/ facade:")
            for route_path, method in sorted(missing_in_api):
                print(f"  - {method} {route_path}")
        if missing_in_barsukas:
            print("Facades in api/ with no matching Barsukas route:")
            for route_path, method in sorted(missing_in_barsukas):
                print(f"  - {method} {route_path}")
        return 1

    print(f"OK: {len(api_pairs)} mirrored route path/method pairs match.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
