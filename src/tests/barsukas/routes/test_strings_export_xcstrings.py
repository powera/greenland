from __future__ import annotations

import json
from pathlib import Path

from barsukas.routes.strings_export import _parse_uploaded_xcstrings
from storage.backend.config import BackendType, DataSourceConfig
from strings.gyvate_service import GyvateStringsExportService


def test_parse_uploaded_xcstrings_extracts_source_language_strings() -> None:
    sample_xcstrings = {
        "sourceLanguage": "en",
        "strings": {
            "landing.learnLanguage": {
                "comment": "Landing Page",
                "localizations": {
                    "en": {"stringUnit": {"state": "translated", "value": "Learn {targetLanguage}"}}
                },
            },
            "landing.moreModes": {
                "comment": "Landing Page",
                "localizations": {
                    "en": {"stringUnit": {"state": "translated", "value": "More Modes"}}
                },
            },
            "landing.statistics": {
                "comment": "Landing Page",
                "localizations": {
                    "en": {"stringUnit": {"state": "translated", "value": "Statistics"}}
                },
            },
            "landing.studyMaterials": {
                "comment": "Landing Page",
                "localizations": {
                    "en": {"stringUnit": {"state": "translated", "value": "Study Materials"}}
                },
            },
        },
        "version": "1.0",
    }

    parsed_catalog = _parse_uploaded_xcstrings(
        json.dumps(sample_xcstrings).encode("utf-8"), "landing.xcstrings"
    )

    assert parsed_catalog["landing.learnLanguage"] == "Learn {targetLanguage}"
    assert parsed_catalog["landing.moreModes"] == "More Modes"
    assert parsed_catalog["landing.statistics"] == "Statistics"
    assert parsed_catalog["landing.studyMaterials"] == "Study Materials"


def test_export_strings_write_mode_emits_xcstrings_output(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    templates_root = project_root / "src" / "barsukas" / "templates"
    strings_root = project_root / "strings" / "barsukas"
    templates_root.mkdir(parents=True, exist_ok=True)
    strings_root.mkdir(parents=True, exist_ok=True)

    service = GyvateStringsExportService(
        config=DataSourceConfig(
            backend_type=BackendType.SQLITE, sqlite_path=str(tmp_path / "test.sqlite")
        )
    )
    uploaded_catalogs = {
        "landing": {
            "landing.learnLanguage": "Learn {targetLanguage}",
            "landing.moreModes": "More Modes",
        }
    }

    result = service.export_strings(
        project_root=str(project_root),
        template_path="src/barsukas/templates",
        strings_path="strings/barsukas",
        scopes=["modules"],
        target_languages=["lt"],
        uploaded_english_catalogs=uploaded_catalogs,
        write_mode=True,
    )

    assert result.success is True
    assert (strings_root / "landing" / "lt.xcstrings").exists()
