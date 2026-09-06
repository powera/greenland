#!/usr/bin/env python3
"""Print the test directories covering the files changed in the working tree.

Backs `./run_tests.sh affected`.  Writes pytest targets to stdout, one per line,
and its reasoning to stderr so a selection is never silent about what it chose.

The mapping itself lives in src/tests/affected_map.py.  This script only
resolves changed paths against it.  Cases that need care:

* A changed test file runs itself, whatever else is selected.
* A file directly under src/ (constants.py, logging_config.py) is too broad to
  attribute, so it selects everything.
* An unmapped path selects everything rather than nothing -- an empty selection
  must never be mistaken for a pass.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tests.affected_map import (  # noqa: E402
    DIRECTORY_MAP,
    PATH_MAP,
    ROOT_LEVEL_RUNS_EVERYTHING,
)

ALL_TESTS = "src/tests"


def _changed_files(base: str, staged: bool) -> list[str]:
    """Changed paths: committed on this branch, staged, and unstaged."""
    if staged:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return [line for line in result.stdout.splitlines() if line]

    collected: set[str] = set()
    commands = (
        ["git", "diff", "--name-only", "--diff-filter=ACMR", f"{base}...HEAD"],
        ["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    )
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"warning: `{' '.join(command)}` failed; ignoring that source.", file=sys.stderr)
            continue
        collected.update(line for line in result.stdout.splitlines() if line)
    return sorted(collected)


def _targets_for(path: str) -> tuple[set[str], str]:
    """Test targets for one changed path, with the reason for the choice."""
    # Longest prefix wins, so a specific rule beats a general one.
    for prefix, test_dirs in sorted(PATH_MAP, key=lambda item: -len(item[0])):
        if path.startswith(prefix):
            return {f"{ALL_TESTS}/{d}" for d in test_dirs}, f"path rule {prefix}"

    if path.startswith("src/tests/"):
        # affected_map.py is the map itself, not a test; editing it changes
        # only which tests get picked, so it selects nothing on its own.
        if Path(path).name == "affected_map.py":
            return set(), "the affected map itself"
        if not Path(path).name.startswith("test_"):
            # conftest/helpers: run the directory that owns them.
            return {Path(path).parent.as_posix()}, "test support file"
        return ({path} if (ROOT / path).exists() else set()), "changed test file"

    if not path.startswith("src/"):
        return set(), "outside src/"

    parts = Path(path).parts
    if len(parts) == 2:
        if ROOT_LEVEL_RUNS_EVERYTHING and path.endswith(".py"):
            return {ALL_TESTS}, "top-level src module: too broad to narrow"
        return set(), "top-level non-Python file"

    source_dir = parts[1]
    if source_dir in DIRECTORY_MAP:
        return {f"{ALL_TESTS}/{d}" for d in DIRECTORY_MAP[source_dir]}, f"src/{source_dir}"

    return {ALL_TESTS}, f"src/{source_dir} is unmapped: running everything"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="main", help="branch to diff against")
    parser.add_argument("--staged", action="store_true", help="use the index instead")
    args = parser.parse_args()

    changed = _changed_files(args.base, args.staged)
    if not changed:
        print("No changed files; nothing to select.", file=sys.stderr)
        return 0

    selected: set[str] = set()
    # Group by reason rather than listing every path: a release regeneration
    # touches hundreds of files and a per-file dump buries the actual decision.
    by_reason: dict[str, list[str]] = {}
    for path in changed:
        targets, reason = _targets_for(path)
        selected |= targets
        by_reason.setdefault(reason if targets else f"{reason} (no tests)", []).append(path)

    print(f"{len(changed)} changed file(s):", file=sys.stderr)
    for reason, paths in sorted(by_reason.items()):
        head = paths[0] if len(paths) == 1 else f"{paths[0]} +{len(paths) - 1} more"
        print(f"  {reason}: {head}", file=sys.stderr)

    if not selected:
        print("\nNothing to test beyond smoke.", file=sys.stderr)
        return 0

    # Selecting the whole tree makes every narrower target redundant.
    if ALL_TESTS in selected:
        selected = {ALL_TESTS}
    else:
        # Drop any file already inside a selected directory; pytest would
        # collect it twice and the listing hides what is really being run.
        directories = {t for t in selected if (ROOT / t).is_dir()}
        selected = {
            t
            for t in selected
            if t in directories or not any(t.startswith(f"{d}/") for d in directories)
        }

    existing = sorted(target for target in selected if (ROOT / target).exists())
    if not existing:
        print("\nerror: selected targets do not exist; run `./run_tests.sh all`.", file=sys.stderr)
        return 3

    print(f"\nRunning: {' '.join(existing)}", file=sys.stderr)
    for target in existing:
        print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
