"""Capability handlers for WireWord export tasks."""

from __future__ import annotations

from typing import Any

from agents.ungurys import UngurysAgent
from workqueue.tools import build_default_config, workqueue_payload_handler


def do_wireword_export_directory(
    session: Any,
    language: str,
    source_language: str = "en",
    include_unreviewed_audio: bool = False,
    apply_level_overrides: bool = False,
) -> str:
    """Run a directory-format WireWord export for a target/source language pair."""
    _ = session
    config = build_default_config()

    simplified_chinese = True
    normalized_language = language
    if language == "zh-Hant":
        normalized_language = "zh"
        simplified_chinese = False

    agent = UngurysAgent(
        config=config,
        language=normalized_language,
        simplified_chinese=simplified_chinese,
        include_unreviewed_audio=include_unreviewed_audio,
        source_language=source_language,
    )

    if apply_level_overrides:
        agent.apply_level_overrides()

    success, results = agent.export_wireword_directory()
    if not success:
        raise RuntimeError("WireWord directory export failed")

    files_created = results.get("files_created", [])
    sentences_exported = results.get("sentences_exported", 0)
    return (
        f"Exported WireWord directory for {language} from {source_language}: "
        f"{len(files_created)} word files, {sentences_exported} sentences"
    )


@workqueue_payload_handler()
def handle_wireword_export_directory(
    session: Any,
    language: str,
    source_language: str = "en",
    include_unreviewed_audio: bool = False,
    apply_level_overrides: bool = False,
    **_: Any,
) -> str:
    """Workqueue wrapper for directory-format WireWord exports.

    Accepts and ignores extra payload kwargs added by the route so it is
    tolerant of payload changes.
    """
    return do_wireword_export_directory(
        session=session,
        language=language,
        source_language=source_language,
        include_unreviewed_audio=include_unreviewed_audio,
        apply_level_overrides=apply_level_overrides,
    )
