import json
from pathlib import Path
from typing import Any, cast

from agents.ungurys.agent import MIN_WIREWORD_SENTENCE_EXPORT_COUNT, UngurysAgent


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


def _build_agent_with_sentence_exporter(
    sentence_count: int,
) -> tuple[UngurysAgent, _DummySentenceExporter]:
    agent = UngurysAgent.__new__(UngurysAgent)
    exporter = _DummySentenceExporter(sentence_count)
    setattr(agent, "sentence_exporter", cast(Any, exporter))
    return agent, exporter


def test_export_wireword_sentences_passes_threshold_to_exporter(tmp_path: Path) -> None:
    output_path = tmp_path / "wireword_sentences.json"
    agent, exporter = _build_agent_with_sentence_exporter(sentence_count=10)

    success, sentence_count = agent.export_wireword_sentences(output_path=str(output_path))

    assert success is True
    assert sentence_count == 10
    assert exporter.last_min_sentences_to_export == MIN_WIREWORD_SENTENCE_EXPORT_COUNT


def test_export_wireword_sentences_returns_exporter_count(tmp_path: Path) -> None:
    output_path = tmp_path / "wireword_sentences.json"
    agent, _ = _build_agent_with_sentence_exporter(
        sentence_count=MIN_WIREWORD_SENTENCE_EXPORT_COUNT
    )

    success, sentence_count = agent.export_wireword_sentences(output_path=str(output_path))

    assert success is True
    assert sentence_count == MIN_WIREWORD_SENTENCE_EXPORT_COUNT
