"""Generate Barsukas base string catalogs from templates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from strings import generate_barsukas_strings as barsukas_generator


@dataclass(frozen=True)
class VeidrodisRunResult:
    replacements_total: int
    templates_changed: int
    new_key_count: int
    reused_common_count: int
    collisions_resolved: int


@dataclass
class TemplateStringsExporter:
    """Generate or update base Barsukas string catalogs and template references."""

    def run(
        self, *, templates_root: str, strings_root: str, write_mode: bool
    ) -> VeidrodisRunResult:
        original_templates_root = barsukas_generator.TEMPLATES_ROOT
        original_strings_root = barsukas_generator.STRINGS_ROOT
        original_namespace_alias = barsukas_generator.NAMESPACE_ALIAS
        try:
            barsukas_generator.TEMPLATES_ROOT = Path(templates_root).resolve()
            barsukas_generator.STRINGS_ROOT = Path(strings_root).resolve()
            barsukas_generator.NAMESPACE_ALIAS = {}
            (
                template_plans,
                standard_catalog_state,
                _cstr_catalog_state,
                standard_stats,
                _cstr_stats,
            ) = barsukas_generator.compute_plan()

            if write_mode:
                for template_file, replacements in template_plans.items():
                    original_content = template_file.read_text(encoding="utf-8")
                    updated_content = barsukas_generator.apply_replacements(
                        original_content, replacements
                    )
                    template_file.write_text(updated_content, encoding="utf-8")
                standard_catalog_state.write()

            replacements_total = sum(len(items) for items in template_plans.values())
            return VeidrodisRunResult(
                replacements_total=replacements_total,
                templates_changed=len(template_plans),
                new_key_count=standard_stats.new_key_count,
                reused_common_count=standard_stats.reused_common_count,
                collisions_resolved=standard_stats.collisions_resolved,
            )
        finally:
            barsukas_generator.TEMPLATES_ROOT = original_templates_root
            barsukas_generator.STRINGS_ROOT = original_strings_root
            barsukas_generator.NAMESPACE_ALIAS = original_namespace_alias


VeidrodisAgent = TemplateStringsExporter

__all__ = ["TemplateStringsExporter", "VeidrodisAgent", "VeidrodisRunResult"]
