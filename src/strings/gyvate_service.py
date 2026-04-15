"""Backend service for GYVATE STRINGS export operations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from storage.backend.config import DataSourceConfig
from strings import generate_barsukas_strings as barsukas_generator


@dataclass(frozen=True)
class TemplateChangeSummary:
    """Summary information for one template file."""

    template_path: str
    replacement_count: int


@dataclass(frozen=True)
class LanguageGenerationStatus:
    """Status for one target language catalog generation/update."""

    language: str
    file_path: str
    namespaces_processed: int
    keys_added: int
    status: str


@dataclass(frozen=True)
class GyvateServiceResult:
    """Result payload returned to route handlers."""

    success: bool
    mode: str
    project_root: str
    template_path: str
    strings_path: str
    scopes: list[str]
    replacements_total: int
    templates_changed: int
    module_files_scanned: int
    reused_common_count: int
    new_key_count: int
    collisions_resolved: int
    new_keys_by_namespace: dict[str, list[str]]
    template_changes: list[TemplateChangeSummary]
    language_statuses: list[LanguageGenerationStatus]
    uploaded_english_catalogs: int
    error: str | None = None


class GyvateStringsExportService:
    """Service for extracting template strings and generating STRINGS catalogs."""

    def __init__(self, config: DataSourceConfig) -> None:
        self.config = config

    def export_strings(
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
        """Compute and optionally apply STRINGS extraction and catalog generation."""
        try:
            root_dir = Path(project_root).expanduser().resolve()
            templates_root = (root_dir / template_path).resolve()
            strings_root = (root_dir / strings_path).resolve()

            if not root_dir.exists():
                raise ValueError(f"Project root does not exist: {root_dir}")
            if "templates" in scopes and not templates_root.exists():
                raise ValueError(f"Template path does not exist: {templates_root}")

            template_plans, catalog_state, stats = self._compute_template_plan(
                templates_root=templates_root,
                strings_root=strings_root,
                include_templates="templates" in scopes,
            )
            self._merge_uploaded_english_catalogs(
                strings_root=strings_root,
                catalog_state=catalog_state,
                uploaded_english_catalogs=uploaded_english_catalogs,
                write_mode=write_mode,
            )
            module_files_scanned = self._count_module_files(root_dir) if "modules" in scopes else 0

            replacements_total = sum(len(replacements) for replacements in template_plans.values())
            template_changes = [
                TemplateChangeSummary(
                    template_path=str(template_file.relative_to(root_dir)),
                    replacement_count=len(replacements),
                )
                for template_file, replacements in sorted(template_plans.items())
            ]

            if write_mode:
                self._apply_template_changes(template_plans)
                catalog_state.write()

            language_statuses = self._update_target_languages(
                strings_root=strings_root,
                catalog_state=catalog_state,
                target_languages=target_languages,
                write_mode=write_mode,
            )

            return GyvateServiceResult(
                success=True,
                mode="write" if write_mode else "dry-run",
                project_root=str(root_dir),
                template_path=str(templates_root),
                strings_path=str(strings_root),
                scopes=sorted(set(scopes)),
                replacements_total=replacements_total,
                templates_changed=len(template_plans),
                module_files_scanned=module_files_scanned,
                reused_common_count=stats.reused_common_count,
                new_key_count=stats.new_key_count,
                collisions_resolved=stats.collisions_resolved,
                new_keys_by_namespace={
                    namespace: sorted(keys)
                    for namespace, keys in sorted(catalog_state.new_keys.items())
                    if keys
                },
                template_changes=template_changes,
                language_statuses=language_statuses,
                uploaded_english_catalogs=len(uploaded_english_catalogs),
            )
        except Exception as error:  # pragma: no cover - defensive route safety
            return GyvateServiceResult(
                success=False,
                mode="write" if write_mode else "dry-run",
                project_root=project_root,
                template_path=template_path,
                strings_path=strings_path,
                scopes=sorted(set(scopes)),
                replacements_total=0,
                templates_changed=0,
                module_files_scanned=0,
                reused_common_count=0,
                new_key_count=0,
                collisions_resolved=0,
                new_keys_by_namespace={},
                template_changes=[],
                language_statuses=[],
                uploaded_english_catalogs=len(uploaded_english_catalogs),
                error=str(error),
            )

    def _merge_uploaded_english_catalogs(
        self,
        *,
        strings_root: Path,
        catalog_state: barsukas_generator.CatalogState,
        uploaded_english_catalogs: dict[str, dict[str, str]],
        write_mode: bool,
    ) -> None:
        for namespace, uploaded_catalog in uploaded_english_catalogs.items():
            catalog_state.ensure_namespace(namespace)
            english_catalog = catalog_state.catalogs.setdefault(namespace, {})
            for key_name, english_text in uploaded_catalog.items():
                normalized_text = barsukas_generator.normalize_for_lookup(english_text)
                if normalized_text:
                    existing_locations = catalog_state.reverse_lookup.setdefault(
                        normalized_text, []
                    )
                    if (namespace, key_name) not in existing_locations:
                        existing_locations.append((namespace, key_name))
                english_catalog[key_name] = english_text

            if not write_mode:
                continue

            namespace_dir = strings_root.joinpath(*namespace.split("."))
            namespace_dir.mkdir(parents=True, exist_ok=True)
            sorted_catalog = {
                key_name: english_catalog[key_name] for key_name in sorted(english_catalog)
            }
            with (namespace_dir / "en.json").open("w", encoding="utf-8") as english_handle:
                json.dump(sorted_catalog, english_handle, ensure_ascii=False, indent=2)
                english_handle.write("\n")

    def _compute_template_plan(
        self,
        *,
        templates_root: Path,
        strings_root: Path,
        include_templates: bool,
    ) -> tuple[
        dict[Path, list[barsukas_generator.Replacement]],
        barsukas_generator.CatalogState,
        barsukas_generator.CatalogUpdateStats,
    ]:
        if not include_templates:
            catalog_state = barsukas_generator.CatalogState(strings_root)
            stats = barsukas_generator.CatalogUpdateStats()
            return ({}, catalog_state, stats)

        original_templates_root = barsukas_generator.TEMPLATES_ROOT
        original_strings_root = barsukas_generator.STRINGS_ROOT
        original_namespace_alias = barsukas_generator.NAMESPACE_ALIAS
        try:
            barsukas_generator.TEMPLATES_ROOT = templates_root
            barsukas_generator.STRINGS_ROOT = strings_root
            barsukas_generator.NAMESPACE_ALIAS = {}
            return barsukas_generator.compute_plan()
        finally:
            barsukas_generator.TEMPLATES_ROOT = original_templates_root
            barsukas_generator.STRINGS_ROOT = original_strings_root
            barsukas_generator.NAMESPACE_ALIAS = original_namespace_alias

    def _apply_template_changes(
        self, template_plans: dict[Path, list[barsukas_generator.Replacement]]
    ) -> None:
        for template_file, replacements in template_plans.items():
            original_content = template_file.read_text(encoding="utf-8")
            updated_content = barsukas_generator.apply_replacements(original_content, replacements)
            template_file.write_text(updated_content, encoding="utf-8")

    def _update_target_languages(
        self,
        *,
        strings_root: Path,
        catalog_state: barsukas_generator.CatalogState,
        target_languages: list[str],
        write_mode: bool,
    ) -> list[LanguageGenerationStatus]:
        statuses: list[LanguageGenerationStatus] = []
        languages = [lang for lang in target_languages if lang and lang != "en"]

        for language_code in languages:
            namespaces_processed = 0
            added_keys_total = 0
            for namespace in sorted(catalog_state.namespace_dirs):
                namespace_dir = strings_root.joinpath(*namespace.split("."))
                english_file = namespace_dir / "en.json"
                if not english_file.exists():
                    continue
                namespaces_processed += 1

                with english_file.open("r", encoding="utf-8") as english_handle:
                    english_catalog = json.load(english_handle)
                localized_file = namespace_dir / f"{language_code}.json"
                localized_catalog = self._read_json_file(localized_file)

                added_in_namespace = 0
                for key_name, english_text in english_catalog.items():
                    if key_name not in localized_catalog:
                        localized_catalog[key_name] = english_text
                        added_in_namespace += 1
                added_keys_total += added_in_namespace

                if write_mode:
                    sorted_localized_catalog = {
                        key_name: localized_catalog[key_name]
                        for key_name in sorted(localized_catalog)
                    }
                    namespace_dir.mkdir(parents=True, exist_ok=True)
                    with localized_file.open("w", encoding="utf-8") as localized_handle:
                        json.dump(
                            sorted_localized_catalog, localized_handle, ensure_ascii=False, indent=2
                        )
                        localized_handle.write("\n")

            status = "updated" if write_mode else "would-update"
            statuses.append(
                LanguageGenerationStatus(
                    language=language_code,
                    file_path=str(strings_root),
                    namespaces_processed=namespaces_processed,
                    keys_added=added_keys_total,
                    status=status,
                )
            )

        return statuses

    def _read_json_file(self, json_path: Path) -> dict[str, str]:
        if not json_path.exists():
            return {}
        with json_path.open("r", encoding="utf-8") as source_handle:
            loaded_json: Any = json.load(source_handle)
        if not isinstance(loaded_json, dict):
            return {}
        return {str(key_name): str(value_text) for key_name, value_text in loaded_json.items()}

    def _count_module_files(self, project_root: Path) -> int:
        barsukas_src = project_root / "src" / "barsukas"
        if not barsukas_src.exists():
            return 0
        return sum(1 for _ in barsukas_src.rglob("*.py"))
