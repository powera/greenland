import json
from pathlib import Path
from typing import Any, cast

from exports.wireword.service import (
    MIN_WIREWORD_SENTENCE_EXPORT_COUNT,
    WirewordExportService,
)


class _DummySentenceExporter:
    def __init__(self, sentence_count: int) -> None:
        self.sentence_count = sentence_count
        self.last_min_sentences_to_export: int | None = None

    def export_to_file(
        self,
        output_path: str,
        include_all_languages: bool = False,
        exclude_conversation_sentences: bool = True,
        min_sentences_to_export: int = 0,
    ) -> int:
        del include_all_languages, exclude_conversation_sentences
        self.last_min_sentences_to_export = min_sentences_to_export
        sentence_payload = {"sentences": [{"id": idx} for idx in range(self.sentence_count)]}
        Path(output_path).write_text(
            json.dumps(sentence_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return self.sentence_count


def _build_service_with_sentence_exporter(
    sentence_count: int,
) -> tuple[WirewordExportService, _DummySentenceExporter]:
    exporter_service = WirewordExportService.__new__(WirewordExportService)
    exporter = _DummySentenceExporter(sentence_count)
    setattr(exporter_service, "sentence_exporter", cast(Any, exporter))
    return exporter_service, exporter


def test_export_wireword_sentences_passes_threshold_to_exporter(tmp_path: Path) -> None:
    output_path = tmp_path / "wireword_sentences.json"
    exporter_service, exporter = _build_service_with_sentence_exporter(sentence_count=10)

    success, sentence_count = exporter_service.export_wireword_sentences(
        output_path=str(output_path)
    )

    assert success is True
    assert sentence_count == 10
    assert exporter.last_min_sentences_to_export == MIN_WIREWORD_SENTENCE_EXPORT_COUNT


def test_export_wireword_sentences_returns_exporter_count(tmp_path: Path) -> None:
    output_path = tmp_path / "wireword_sentences.json"
    exporter_service, _ = _build_service_with_sentence_exporter(
        sentence_count=MIN_WIREWORD_SENTENCE_EXPORT_COUNT
    )

    success, sentence_count = exporter_service.export_wireword_sentences(
        output_path=str(output_path)
    )

    assert success is True
    assert sentence_count == MIN_WIREWORD_SENTENCE_EXPORT_COUNT


def test_legacy_ungurys_agent_is_service_alias() -> None:
    from agents.ungurys import UngurysAgent

    assert UngurysAgent is WirewordExportService


def test_every_advertised_language_can_actually_be_exported() -> None:
    """The CLI validates against the service, then hands the code to the exporter.

    These were two separate comprehensions over the tier lists, so adding a
    language to one left the other rejecting it at construction with
    "Unsupported language" after it had passed every visible check.
    """
    from exports.wireword.export_manager import TrakaidoExporter
    from exports.wireword.service import SUPPORTED_LANGUAGES

    assert set(SUPPORTED_LANGUAGES) == set(TrakaidoExporter.LANGUAGE_CONFIG)
    for language_code in SUPPORTED_LANGUAGES:
        TrakaidoExporter(language=language_code)


def test_the_storage_dialects_are_exportable() -> None:
    from exports.wireword.service import SUPPORTED_LANGUAGES
    from langtools.dialect_overrides import get_translation_target_dialects

    for language_code in get_translation_target_dialects():
        assert language_code in SUPPORTED_LANGUAGES, language_code


def _service_for(language: str) -> WirewordExportService:
    from storage.backend.config import BackendType, DataSourceConfig

    return WirewordExportService(
        config=DataSourceConfig(backend_type=BackendType.SQLITE),
        language=language,
    )


def test_zh_tw_exports_as_its_own_language() -> None:
    """Traditional Chinese is a zh-tw export, not a zh export with a flag.

    It writes lang_zh-tw/, uploads under the zh-tw CDN prefix, and reads zh-tw
    translation rows -- there is no zh fallback and no zh_Hant naming left.
    """
    service = _service_for("zh-tw")

    assert service.language == "zh-tw"
    assert service.language_suffix == "zh-tw"
    assert service._get_cdn_language_code() == "zh-tw"
    assert service.get_language_output_dir().endswith("lang_zh-tw/generated")
    assert service.exporter.language == "zh-tw"
    assert service.sentence_exporter.language == "zh-tw"
    assert service.conversation_exporter.language == "zh-tw"


def test_legacy_zh_hant_spelling_resolves_to_zh_tw() -> None:
    """Queued tasks and saved commands still say zh-Hant; it means zh-tw."""
    for legacy_spelling in ("zh-Hant", "zh_TW", "zh-hant"):
        assert _service_for(legacy_spelling).language == "zh-tw"


def test_zh_export_is_unaffected_by_the_dialect() -> None:
    service = _service_for("zh")

    assert service.language == "zh"
    assert service._get_cdn_language_code() == "zh"
    assert service.get_language_output_dir().endswith("lang_zh/generated")
