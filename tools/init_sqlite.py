#!/usr/bin/env python3

"""Build the linguistics SQLite database from data/release.

    python tools/init_sqlite.py
    python tools/init_sqlite.py --db-path /tmp/scratch.sqlite

A thin wrapper around ``bootstrap_database.py`` in the repository root, which
is the maintained rebuild path.  This script used to carry its own two-step
pipeline calling ``migrate.py jsonl-to-sqlite``; that subcommand was removed by
the Agent refactor (#713), so the script had been failing at step 1 for some
time.  Rather than reimplement the steps a second time, it now forwards to the
one implementation and exists only as the familiar entry point.

``bootstrap_database.py`` does strictly more than the old pipeline did: it
imports data/release *and* runs the corpus, form/token-link, tier and rank
enrichment that release files do not carry.  That enrichment is not optional
for a usable database -- an enabled corpus with no annotations makes
``combined_rank`` charge every lemma that corpus's unknown-rank floor.

Note that a rebuild is not a round trip.  data/release is a publishing
projection: it carries English forms only, and nothing of word tokens, tiers,
operation logs or difficulty overrides.  A rebuild also renumbers ``lemmas.id``
and ``sentences.id``, so anything joining across two snapshots must join on
``guid``.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP = REPO_ROOT / "bootstrap_database.py"


def main() -> int:
    """Forward every argument to bootstrap_database.py."""
    if not BOOTSTRAP.exists():
        sys.exit(f"Cannot find the bootstrap script: {BOOTSTRAP}")

    command = [sys.executable, str(BOOTSTRAP), *sys.argv[1:]]
    print(f"$ {' '.join(command)}\n")
    return subprocess.run(command, cwd=REPO_ROOT).returncode


if __name__ == "__main__":
    sys.exit(main())
