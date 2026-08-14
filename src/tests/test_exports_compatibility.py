"""Compatibility coverage for export modules moved out of agents."""

from __future__ import annotations

from agents.elnias import ElniasAgent, get_argument_parser as get_elnias_parser
from agents.gyvate import GyvateAgent
from agents.povas import PovasAgent, get_argument_parser as get_povas_parser
from agents.veidrodis import VeidrodisAgent, VeidrodisRunResult
from exports.bootstrap import BootstrapExporter
from exports.pos_reports import POSSubtypeReportGenerator
from exports.strings import StringsCatalogExporter, TemplateStringsExporter
from exports.strings.template_catalogs import VeidrodisRunResult as ExportRunResult


def test_legacy_agent_imports_are_aliases_for_export_capabilities() -> None:
    assert ElniasAgent is BootstrapExporter
    assert PovasAgent is POSSubtypeReportGenerator
    assert GyvateAgent is StringsCatalogExporter
    assert VeidrodisAgent is TemplateStringsExporter
    assert VeidrodisRunResult is ExportRunResult


def test_elnias_parser_preserves_export_arguments() -> None:
    args = get_elnias_parser().parse_args(
        ["--language", "zh-Hant", "--include-unverified", "--output", "result.json"]
    )

    assert args.language == "zh-Hant"
    assert args.include_unverified is True
    assert args.output == "result.json"


def test_povas_parser_preserves_index_only_argument() -> None:
    args = get_povas_parser().parse_args(["--index-only"])

    assert args.index_only is True
