"""Tests for Vilkas CLI task parsing and task-specific coverage behavior."""

from __future__ import annotations

from unittest.mock import patch

from agents.vilkas.cli import main


def test_coverage_mode_uses_task_language_instead_of_full_lithuanian_report() -> None:
    """Coverage mode should honor the selected task language and POS."""

    class _Args:
        languages = None
        task = "en-noun-forms"
        populate = False
        coverage = True
        dry_run = False
        output = None
        model = "gpt-5-mini"
        limit = 20
        throttle = 1.0
        use_wiktionary = False
        use_workqueue = False
        yes = True
        guid = None
        level = None
        pos_type = None
        backend = None
        db_path = ":memory:"
        barsukas_url = None
        cache_only = False
        debug = False

    lemma = type("LemmaStub", (), {"lemma_text": "dog", "guid": "N00_001", "pos_type": "noun"})()

    session_stub = type("SessionStub", (), {"close": lambda self: None})()

    with (
        patch("argparse.ArgumentParser.parse_args", return_value=_Args()),
        patch("agents.vilkas.cli.validate_cache_args"),
        patch("agents.vilkas.cli.get_data_source_config", return_value=object()),
        patch("words.lemma_selection.get_lemmas_for_agent", return_value=[lemma]),
        patch("agents.vilkas.display.print_fix_results") as mock_print_results,
        patch("words.inflections.InflectionService") as mock_agent_class,
    ):
        mock_agent = mock_agent_class.return_value
        mock_agent.get_session.return_value = session_stub
        mock_agent.fix_missing_forms.return_value = {"total_needing_fix": 2, "would_process": 2}

        main()

    mock_agent.fix_missing_forms.assert_called_once_with(
        lemmas=[lemma],
        language_code="en",
        pos_type="noun",
        limit=20,
        model="gpt-5-mini",
        throttle=1.0,
        dry_run=True,
        use_wiktionary=False,
    )
    mock_agent.run_full_check.assert_not_called()
    mock_print_results.assert_called_once()
