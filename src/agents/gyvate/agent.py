"""GYVATE agent for STRINGS export planning and generation."""

from __future__ import annotations

from dataclasses import dataclass
from storage.backend.config import DataSourceConfig
from strings.gyvate_service import GyvateServiceResult, GyvateStringsExportService


@dataclass
class GyvateAgent:
    """Service-backed agent for STRINGS extraction/generation operations."""

    config: DataSourceConfig

    def run_export(
        self,
        *,
        project_root: str,
        template_path: str,
        strings_path: str,
        scopes: list[str],
        target_languages: list[str],
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
            write_mode=write_mode,
        )


__all__ = ["GyvateAgent", "GyvateServiceResult"]
