#!/usr/bin/env python3
"""Tests for the strazdas CLI's dry-run handling.

Regression coverage: --dry-run used to gate only the confirmation prompt, so it
skipped the safety check and then generated audio anyway.
"""

import unittest
from unittest.mock import MagicMock, patch

from agents import strazdas


class TestStrazdasDryRun(unittest.TestCase):
    """--dry-run must report and stop, without generating."""

    def run_main(self, *argv: str) -> MagicMock:
        """Run strazdas.main() with a stubbed agent; return the agent mock."""
        agent = MagicMock()
        agent.get_translation_text.return_value = "labas"

        argv_full = ["strazdas.py", *argv]
        with (
            patch.object(strazdas.sys, "argv", argv_full),
            patch.object(strazdas, "StrazdasAgent", return_value=agent),
            patch.object(strazdas, "get_data_source_config"),
            patch.object(
                strazdas, "get_lemmas_for_agent", return_value=[MagicMock(guid="N01_001")]
            ),
        ):
            strazdas.main()
        return agent

    def test_dry_run_does_not_generate(self) -> None:
        agent = self.run_main("--mode", "populate-only", "--language", "lt", "--dry-run")
        agent.generate_batch.assert_not_called()

    def test_dry_run_does_not_prompt(self) -> None:
        with patch.object(strazdas, "confirm_operation") as confirm:
            self.run_main("--mode", "populate-only", "--language", "lt", "--dry-run")
        confirm.assert_not_called()

    def test_without_dry_run_generates(self) -> None:
        with patch.object(strazdas, "confirm_operation", return_value=True):
            agent = self.run_main("--mode", "populate-only", "--language", "lt")
        agent.generate_batch.assert_called_once()

    def test_declining_confirmation_does_not_generate(self) -> None:
        with patch.object(strazdas, "confirm_operation", return_value=False):
            with self.assertRaises(SystemExit):
                self.run_main("--mode", "populate-only", "--language", "lt")


if __name__ == "__main__":
    unittest.main()
