#!/usr/bin/env python3
"""Measure which test directories actually exercise each source directory.

This is the tool that produced the numbers in src/tests/affected_map.py.  It is
not run by ./run_tests.sh -- the map is static on purpose.  Run this by hand
after a large refactor, read the matrix, and update the map.

  GREENLAND_TEST_MODE=1 PYTHONPATH=src python tools/measure_test_coverage.py

Takes several minutes: it runs the whole suite under coverage with a per-test
dynamic context, which is far slower than a plain run.
"""

from __future__ import annotations

import collections
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def _test_top_level(context: str) -> str:
    """coverage context 'src.tests.langtools.test_x.TestY.test_z' -> 'langtools'."""
    parts = context.split(".")
    if parts[:2] == ["src", "tests"] and len(parts) > 2:
        return "(root)" if parts[2].startswith("test_") else parts[2]
    return "(root)"


def main() -> int:
    tmpdir = Path(tempfile.mkdtemp(prefix="measure-coverage-"))
    rcfile = tmpdir / "coveragerc"
    jsonfile = tmpdir / "coverage.json"
    # `source` must be absolute: PYTHONPATH=src makes project modules import as
    # top-level names, which a relative source root fails to match.
    rcfile.write_text(
        f"[run]\nsource = {SRC}\ndata_file = {tmpdir / 'coverage.data'}\n"
        "dynamic_context = test_function\n"
    )

    print("Running the full suite under coverage; this takes several minutes.")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "coverage",
            "run",
            f"--rcfile={rcfile}",
            "-m",
            "pytest",
            "src/tests",
            "-q",
            "-p",
            "no:randomly",
        ],
        cwd=ROOT,
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "coverage",
            "json",
            f"--rcfile={rcfile}",
            "-o",
            str(jsonfile),
            "--show-contexts",
        ],
        cwd=ROOT,
        check=True,
    )

    report = json.loads(jsonfile.read_text())
    hits: dict[str, set[tuple[str, str]]] = collections.defaultdict(set)
    for filename, filedata in report.get("files", {}).items():
        path = Path(filename)
        try:
            relative = path.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            continue
        if not relative.startswith("src/") or relative.startswith("src/tests/"):
            continue
        parts = relative.split("/")
        source_dir = "(top)" if len(parts) == 2 else parts[1]
        for line_contexts in (filedata.get("contexts") or {}).values():
            for context in line_contexts:
                if context:
                    hits[source_dir].add((_test_top_level(context), context))

    print(f"\n{'src dir':14s} {'tests':>6s}  test dirs by distinct-test count")
    for source_dir in sorted(hits):
        counts = collections.Counter(top for top, _ in hits[source_dir])
        total = sum(counts.values())
        shown = [(top, n) for top, n in counts.most_common() if n / total >= 0.03]
        marks = " ".join(f"{'=' if top == source_dir else '+'}{top}({n})" for top, n in shown)
        print(f"{source_dir:14s} {total:6d}  {marks}")
    print("\n'=' is the mirror directory, '+' a cross-directory edge.")
    print("Update DIRECTORY_MAP in src/tests/affected_map.py from this matrix.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
