"""Characterization tests for the bootstrap export format."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from exports.bootstrap.exporter import BootstrapExporter


class _ExporterStub:
    def __init__(self) -> None:
        self.session = object()
        self.query_arguments: dict[str, Any] = {}

    def get_session(self) -> object:
        return self.session

    def query_trakaido_data(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.query_arguments = kwargs
        return [
            {
                "English": "cat",
                "Target": "katė",
                "GUID": "N00_001",
                "trakaido_level": 1,
                "POS": "noun",
                "subtype": "common",
            }
        ]


def test_bootstrap_export_preserves_output_shape_and_query_filters(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    exporter_stub = _ExporterStub()
    exporter = BootstrapExporter.__new__(BootstrapExporter)
    exporter.language = "lt"
    exporter.language_suffix = "lt"
    exporter.exporter = exporter_stub
    output_path = tmp_path / "bootstrap.json"

    with caplog.at_level(logging.INFO):
        result = exporter.export_bootstrap(str(output_path), include_unverified=True)

    assert json.loads(output_path.read_text(encoding="utf-8")) == [
        {
            "English": "cat",
            "Lithuanian": "katė",
            "GUID": "N00_001",
            "trakaido_level": 1,
            "POS": "noun",
            "subtype": "common",
        }
    ]
    assert exporter_stub.query_arguments == {
        "session": exporter_stub.session,
        "include_without_guid": False,
        "include_unverified": True,
        "exclude_verbs": False,
    }
    assert result["success"] is True
    assert result["output_path"] == str(output_path)
    assert result["entry_count"] == 1
    assert result["language"] == "Lithuanian"
    assert result["language_code"] == "lt"
    assert result["include_unverified"] is True
    assert f"Successfully wrote 1 entries to {output_path}" in caplog.messages
