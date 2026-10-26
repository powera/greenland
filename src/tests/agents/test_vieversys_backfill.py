"""Backfill selection and explicit Speech API model routing."""

from argparse import Namespace
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from agents.vieversys import VieversysAgent, _get_lemmas_for_audio, get_argument_parser
from clients.audio.gpt_voices import GptVoice
from clients.audio.openai_tts import DEFAULT_MODEL
from clients.audio.types import AudioGenerationResult, Voice
from storage.backend.config import DataSourceConfig
from storage.models.schema import Lemma, LemmaDifficultyOverride, Sentence, SentenceTranslation


@pytest.mark.parametrize("level", ["1-30", "5"])
def test_selection_uses_only_target_language_overrides(level: str) -> None:
    engine = create_engine("sqlite:///:memory:")
    Lemma.metadata.create_all(
        engine,
        tables=[
            Lemma.metadata.tables["lemmas"],
            Lemma.metadata.tables["lemma_difficulty_overrides"],
        ],
    )
    with Session(engine) as session:
        for lemma_id, base_level in enumerate([5, 50, 5, 5, 5, None], 1):
            session.add(
                Lemma(
                    id=lemma_id,
                    guid=f"N01_{lemma_id:03}",
                    lemma_text="word",
                    definition_text="test",
                    pos_type="noun",
                    difficulty_level=base_level,
                )
            )
        session.flush()
        session.add_all(
            [
                LemmaDifficultyOverride(lemma_id=2, language_code="es", difficulty_level=5),
                LemmaDifficultyOverride(lemma_id=3, language_code="es", difficulty_level=50),
                LemmaDifficultyOverride(lemma_id=4, language_code="es", difficulty_level=-1),
                LemmaDifficultyOverride(lemma_id=5, language_code="es-419", difficulty_level=-1),
                LemmaDifficultyOverride(lemma_id=6, language_code="es", difficulty_level=5),
            ]
        )
        session.flush()
        args = Namespace(guid=None, level=level, limit=None, sample_rate=1.0)
        assert [lemma.id for lemma in _get_lemmas_for_audio(session, args, "es")] == [1, 2, 5, 6]
        args.guid = "N01_003"
        assert [lemma.id for lemma in _get_lemmas_for_audio(session, args, "es")] == [3]
    engine.dispose()


@pytest.mark.parametrize("sentence_audio", [False, True])
def test_explicit_tts_model_reaches_generation(tmp_path: Path, sentence_audio: bool) -> None:
    model = "gpt-4o-mini-tts-2025-12-15"
    agent = VieversysAgent(
        DataSourceConfig(model="unrelated-llm-model"),
        output_dir=str(tmp_path),
        upload_s3=False,
        tts_model=model,
    )
    failed = AudioGenerationResult(
        audio_data=b"",
        text="pan",
        voice=Voice.CORAL,
        language_code="es",
        model=model,
        duration_ms=0,
        success=False,
        error="test failure",
    )
    with patch("agents.vieversys.generate_audio", return_value=failed) as generate:
        if sentence_audio:
            result = agent.generate_audio_for_sentence(
                Mock(),
                Sentence(id=1),
                SentenceTranslation(sentence_id=1, language_code="es", translation_text="pan"),
                [GptVoice.GPT_ES_F1],
                create_review_record=False,
            )
        else:
            with patch.object(agent, "get_translation_text", return_value="pan"):
                result = agent.generate_audio_for_lemma(
                    Mock(), Lemma(guid="N01_001", lemma_text="bread"), "es", [GptVoice.GPT_ES_F1]
                )
    assert result["success"] is False
    assert generate.call_args.kwargs["model"] == model
    assert generate.call_args.kwargs["voice"] == Voice.CORAL
    assert generate.call_args.kwargs["language_code"] == "es"


def test_parser_keeps_audio_and_llm_models_independent() -> None:
    parser = get_argument_parser()
    assert parser.parse_args([]).tts_model == DEFAULT_MODEL
    args = parser.parse_args(["--model", "llm-model", "--tts-model", "gpt-4o-mini-tts"])
    assert args.model == "llm-model"
    assert args.tts_model == "gpt-4o-mini-tts"
    assert args.upload_s3 is True
