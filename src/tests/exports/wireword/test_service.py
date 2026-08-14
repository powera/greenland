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
