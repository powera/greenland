import json
from pathlib import Path
from typing import Any, cast

from wireword.export_wireword_sentences import WirewordSentenceExporter


def _build_exporter_with_data(sentence_count: int) -> WirewordSentenceExporter:
    exporter = WirewordSentenceExporter.__new__(WirewordSentenceExporter)

    def _fake_export_sentences(
        include_all_languages: bool = False,
        exclude_conversation_sentences: bool = True,
    ) -> dict[str, Any]:
        del include_all_languages, exclude_conversation_sentences
        return {"sentences": [{"id": idx} for idx in range(sentence_count)]}

    setattr(exporter, "export_sentences", cast(Any, _fake_export_sentences))
    return exporter


def test_export_to_file_writes_empty_payload_below_minimum_threshold(tmp_path: Path) -> None:
    output_path = tmp_path / "wireword_sentences.json"
    exporter = _build_exporter_with_data(sentence_count=3)

    sentence_count = exporter.export_to_file(
        output_path=str(output_path),
        min_sentences_to_export=25,
    )

    assert sentence_count == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload == {"sentences": []}


def test_export_to_file_preserves_payload_at_minimum_threshold(tmp_path: Path) -> None:
    output_path = tmp_path / "wireword_sentences.json"
    exporter = _build_exporter_with_data(sentence_count=25)

    sentence_count = exporter.export_to_file(
        output_path=str(output_path),
        min_sentences_to_export=25,
    )

    assert sentence_count == 25
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert len(payload["sentences"]) == 25
