#!/usr/bin/env python3

"""Build the linguistics SQLite database from data/release, start to finish.

Run from the repository root:

    python tools/init_sqlite.py

The target database must not exist.  There is deliberately no --force: this
script creates a database from scratch, and silently replacing a live one is
how hand-curated work that was never exported gets lost.  Delete the file
yourself once you have a backup you trust.

Steps:

  1. Import data/release into a fresh SQLite file (storage/migrate.py).
  2. Generate the English forms that follow mechanically from spelling and
     grammar facts (wordfreq/tools/generate_mechanical_forms.py).

Step 2 exists because mechanically-derivable forms do not need to be stored in
data/release -- the rules put them back on import, so the release files only
carry the ones the rules cannot derive.

Every step runs as a subprocess with PYTHONPATH=src, so each tool keeps its own
CLI as the supported entry point rather than being imported here.  GREENLAND
_DISABLE_LLM=1 is set for the whole run: this pipeline is entirely mechanical
and must never reach a paid backend, so an accidental LLM call fails loudly
instead of quietly spending money.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
DEFAULT_DB = REPO_ROOT / "data" / "wordfreq" / "linguistics.sqlite"
DEFAULT_RELEASE = REPO_ROOT / "data" / "release"

# Sidecars a previous database may have left behind. A stale -wal/-shm paired
# with a freshly written main file makes SQLite raise disk I/O errors.
SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")


def run_step(number: int, total: int, title: str, command: List[str]) -> None:
    """Run one pipeline step, echoing it, and abort the run if it fails."""
    print(f"\n[{number}/{total}] {title}")
    print(f"      $ {' '.join(command)}")

    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    # This pipeline is mechanical end to end; nothing in it may call an LLM.
    env["GREENLAND_DISABLE_LLM"] = "1"

    result = subprocess.run(command, cwd=REPO_ROOT, env=env)
    if result.returncode != 0:
        sys.exit(f"\nFAILED at step {number} ({title}); exit code {result.returncode}")


def check_target_absent(db_path: Path) -> None:
    """Refuse to run when the database (or a sidecar) already exists."""
    if db_path.exists():
        sys.exit(
            f"Refusing to run: {db_path} already exists.\n"
            f"This script only builds a database from scratch, and there is no\n"
            f"--force override. Back the file up and delete it, then re-run.\n"
            f"\n"
            f"Note that data/release does not carry everything a live database\n"
            f"holds (operation logs, word frequencies, difficulty overrides and\n"
            f"other locally-curated state), so a rebuild is not a round trip."
        )

    stale = [db_path.with_name(db_path.name + s) for s in SIDECAR_SUFFIXES]
    present = [p for p in stale if p.exists()]
    if present:
        listed = "\n  ".join(str(p) for p in present)
        sys.exit(
            f"Refusing to run: stale SQLite sidecar file(s) present:\n  {listed}\n"
            f"Delete them before rebuilding."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the linguistics SQLite database from data/release"
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB,
        help=f"Database to create (default: {DEFAULT_DB.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--release-dir",
        type=Path,
        default=DEFAULT_RELEASE,
        help=f"Release directory to import (default: {DEFAULT_RELEASE.relative_to(REPO_ROOT)})",
    )
    args = parser.parse_args()

    db_path: Path = args.db_path.resolve()
    release_dir: Path = args.release_dir.resolve()

    if not release_dir.is_dir():
        sys.exit(f"Release directory not found: {release_dir}")

    check_target_absent(db_path)

    print(f"Building {db_path}")
    print(f"    from {release_dir}")

    total = 2

    run_step(
        1,
        total,
        "Import data/release into a fresh SQLite database",
        [
            sys.executable,
            str(SRC / "storage" / "migrate.py"),
            "jsonl-to-sqlite",
            "--jsonl-release-dir",
            str(release_dir),
            "--sqlite-path",
            str(db_path),
        ],
    )

    run_step(
        2,
        total,
        "Generate mechanically-derivable English forms",
        [
            sys.executable,
            str(SRC / "wordfreq" / "tools" / "generate_mechanical_forms.py"),
            "--db-path",
            str(db_path),
        ],
    )

    print(f"\nDone. {db_path} is ready.")


if __name__ == "__main__":
    main()
