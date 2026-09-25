#!/usr/bin/python3

"""Argument handling for the release CLI.

These cover the ``database`` pseudo-entity, which is shaped differently from
the element types: it picks its own backend, writes somewhere else, and on
import replaces the whole SQLite file. The round-trip regtest drives only the
element types, so nothing here was exercised until these existed.
"""

import argparse
from typing import Any, Dict, List, Optional, Tuple

import pytest

from storage.release import cli


def _parse(argv: List[str]) -> argparse.Namespace:
    args = cli.build_parser().parse_args(argv)
    args.categories = cli.parse_categories(cli.build_parser(), args.categories)
    return args


class TestDatabaseSelection:
    """Naming ``database`` must not drag in every element type."""

    def test_database_alone_selects_no_elements(self, capsys: Any) -> None:
        """`export database` writes data/working, never data/release.

        Both settings.py routes run exactly this. Selecting every element type
        here would rewrite the whole checked-in release tree as a side effect
        of a JSONL migration.
        """
        assert cli.main(["export", "database", "--dry-run"]) == 0
        printed = capsys.readouterr().out
        assert "would export database" in printed
        assert "lemmas" not in printed
        assert "sentences" not in printed

    def test_export_all_selects_every_element_but_not_the_database(self, capsys: Any) -> None:
        """The dump writes data/working, which the release does not need."""
        assert cli.main(["export", "all", "--dry-run"]) == 0
        printed = capsys.readouterr().out
        for expected in ("lemmas", "sentences", "phrases", "idioms", "tombstones"):
            assert expected in printed
        assert "would export database" not in printed

    def test_naming_elements_beside_database_keeps_both(self, capsys: Any) -> None:
        assert cli.main(["export", "idioms", "database", "--dry-run"]) == 0
        printed = capsys.readouterr().out
        assert "would export idioms" in printed
        assert "would export database" in printed
        assert "lemmas" not in printed


class TestDatabaseOrdering:
    """The whole-database load replaces the file, so it must go first."""

    def test_import_runs_the_database_before_the_elements(self, capsys: Any) -> None:
        """Otherwise it discards the audio the element importers just wrote.

        The whole-database path deliberately does not read the inline release
        audio, so running it second silently undoes `import sentences` and
        `import lemma-audio`.
        """
        assert cli.main(["import", "all", "--dry-run"]) == 0
        lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith("would")]
        assert lines[0] == "would import database", lines

    def test_export_leaves_the_database_last(self, capsys: Any) -> None:
        """On export the two write to different trees, so order is free."""
        assert cli.main(["export", "idioms", "database", "--dry-run"]) == 0
        lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith("would")]
        assert lines[-1] == "would export database", lines


class TestDatabaseArguments:
    """What run_database hands to the whole-database functions."""

    def test_import_passes_release_dir_before_sqlite_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """import_jsonl_to_sqlite is (release_dir, sqlite_path), not the reverse.

        Reversed, it read JSONL from the SQLite file and treated the release
        directory as the destination database.
        """
        seen: Dict[str, Any] = {}

        def _record(release_dir: str, sqlite_path: str, force: bool = False) -> None:
            seen.update(release_dir=release_dir, sqlite_path=sqlite_path, force=force)

        monkeypatch.setattr("storage.migrate.import_jsonl_to_sqlite", _record)
        cli.run_database(
            argparse.Namespace(
                direction="import",
                backend="sqlite",
                postgres_url=None,
                sqlite_path="/tmp/target.sqlite",
                release_root="/tmp/release",
                jsonl_dir="data/working",
                force=True,
            )
        )
        assert seen["release_dir"] == "/tmp/release"
        assert seen["sqlite_path"] == "/tmp/target.sqlite"
        assert seen["force"] is True

    def test_postgres_export_uses_postgres_without_an_explicit_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--backend postgres resolves the URL rather than falling back to SQLite.

        The Barsukas routes pass no --postgres-url; the URL comes from the
        environment or key file, as the old postgres-to-jsonl direction did.
        """
        called: List[Tuple[str, str]] = []
        monkeypatch.setattr(
            "storage.migrate.export_postgres_to_jsonl",
            lambda url, jsonl_dir: called.append((url, jsonl_dir)),
        )
        monkeypatch.setattr(
            "storage.backend.config.DataSourceConfig.build_postgres_url",
            classmethod(lambda cls: "postgresql://resolved/db"),
        )
        monkeypatch.setattr(
            "storage.migrate.export_sqlite_to_jsonl",
            lambda *a, **k: pytest.fail("used SQLite for a postgres backend"),
        )
        cli.run_database(
            argparse.Namespace(
                direction="export",
                backend="postgres",
                postgres_url=None,
                sqlite_path="/tmp/unused.sqlite",
                release_root="/tmp/release",
                jsonl_dir="data/working",
                force=False,
            )
        )
        assert called == [("postgresql://resolved/db", "data/working")]

    def test_an_explicit_url_wins_over_the_resolved_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        called: List[Tuple[str, str]] = []
        monkeypatch.setattr(
            "storage.migrate.export_postgres_to_jsonl",
            lambda url, jsonl_dir: called.append((url, jsonl_dir)),
        )
        cli.run_database(
            argparse.Namespace(
                direction="export",
                backend="postgres",
                postgres_url="postgresql://explicit/db",
                sqlite_path="/tmp/unused.sqlite",
                release_root="/tmp/release",
                jsonl_dir="data/working",
                force=False,
            )
        )
        assert called == [("postgresql://explicit/db", "data/working")]


class TestOptionsAreRejectedWhereTheyDoNotApply:
    """The old CLI accepted --category everywhere and read it on two paths."""

    def test_category_on_an_element_that_ignores_it(self) -> None:
        with pytest.raises(SystemExit):
            cli.main(["export", "idioms", "--category", "nouns/food", "--dry-run"])

    def test_prune_on_an_element_that_ignores_it(self) -> None:
        with pytest.raises(SystemExit):
            cli.main(["import", "idioms", "--prune", "--dry-run"])

    def test_an_unknown_element_is_rejected(self) -> None:
        with pytest.raises(SystemExit):
            cli.main(["export", "widgets", "--dry-run"])

    def test_an_unsupported_direction_is_rejected(self) -> None:
        with pytest.raises(SystemExit):
            cli.main(["import", "phrases", "--dry-run"])
