from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import bootstrap_database


def test_repository_bootstrap_defaults_to_release(tmp_path: Path) -> None:
    database_path = tmp_path / "database.sqlite"
    release_path = tmp_path / "release"

    with patch(
        "bootstrap_database.bootstrap_from_release",
        return_value={"bootstrap_kind": "release"},
    ) as bootstrap_release:
        exit_code = bootstrap_database.main(
            [
                "--db-path",
                str(database_path),
                "--release-path",
                str(release_path),
                "--release-only",
            ]
        )

    assert exit_code == 0
    assert bootstrap_release.call_args.args[1] == release_path
    assert bootstrap_release.call_args.kwargs["include_frequency_data"] is False


def test_repository_bootstrap_empty_mode(tmp_path: Path) -> None:
    database_path = tmp_path / "database.sqlite"

    with patch(
        "bootstrap_database.bootstrap_empty_database",
        return_value={"bootstrap_kind": "empty"},
    ) as bootstrap_empty:
        exit_code = bootstrap_database.main(["--db-path", str(database_path), "--empty"])

    assert exit_code == 0
    assert bootstrap_empty.call_args.kwargs["dry_run"] is False
