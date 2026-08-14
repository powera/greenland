"""Application string catalog export orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from storage.backend.config import DataSourceConfig
from strings.gyvate_service import GyvateServiceResult, GyvateStringsExportService


@dataclass
class StringsCatalogExporter:
    """Service-backed adapter for application string catalog exports."""

    config: DataSourceConfig

    def run_export(
        self,
        *,
        project_root: str,
        template_path: str,
        strings_path: str,
        scopes: list[str],
        target_languages: list[str],
        uploaded_english_catalogs: dict[str, dict[str, str]],
        write_mode: bool,
    ) -> GyvateServiceResult:
        """Run a STRINGS export operation via the reusable backend service."""
        service = GyvateStringsExportService(config=self.config)
        return service.export_strings(
            project_root=project_root,
            template_path=template_path,
            strings_path=strings_path,
            scopes=scopes,
            target_languages=target_languages,
            uploaded_english_catalogs=uploaded_english_catalogs,
            write_mode=write_mode,
        )


GyvateAgent = StringsCatalogExporter

__all__ = ["GyvateAgent", "GyvateServiceResult", "StringsCatalogExporter"]
