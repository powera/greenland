# from Claude
"""
Audio segmentation and transcription utilities.

Requires: pip install greenland[audioshoe] transformers
"""

from __future__ import annotations

from typing import Any, cast


def segment_audio(
    file_path: str,
    min_silence_len: int = 500,
    silence_thresh: int = -40,
    keep_silence: int = 100,
) -> list[Any]:
    """
    Segment an audio file into phrases based on silence.

    Requires: pydub

    :param file_path: Path to the audio file
    :param min_silence_len: Minimum length of silence (in ms) that will be used to split the audio
    :param silence_thresh: Threshold (in dB) below which to consider as silence
    :param keep_silence: Amount of silence to keep around each phrase (in ms)
    :return: List of AudioSegment chunks
    """
    from pydub import AudioSegment
    from pydub.silence import split_on_silence

    # Load the audio file
    audio = AudioSegment.from_file(file_path, format="wav")

    # Split the audio into chunks
    chunks = split_on_silence(
        audio,
        min_silence_len=min_silence_len,
        silence_thresh=silence_thresh,
        keep_silence=keep_silence,
    )

    return cast(list[Any], chunks)


def transcribe_chunks(
    chunks: list[Any],
    processor: Any,
    model: Any,
) -> list[str]:
    """
    Transcribe each audio chunk using the Whisper model.

    Requires: torch, librosa, transformers

    :param chunks: List of AudioSegment chunks (from pydub)
    :param processor: Whisper processor (from transformers)
    :param model: Whisper model (from transformers)
    :return: List of transcriptions
    """
    import librosa
    import torch

    transcriptions = []

    for i, chunk in enumerate(chunks):
        # Export the chunk to a temporary file
        chunk.export(f"temp_chunk_{i}.wav", format="wav")

        # Load the audio file using librosa
        audio, sr = librosa.load(f"temp_chunk_{i}.wav", sr=16000)

        # Process the audio
        input_features = processor(audio, sampling_rate=sr, return_tensors="pt").input_features

        # Generate the transcription
        with torch.no_grad():
            output = model.generate(input_features)

        # Decode the output
        transcription = processor.batch_decode(output, skip_special_tokens=True)[0]
        transcriptions.append(transcription)

    return transcriptions


def main() -> None:
    """Usage example for audio segmentation and transcription."""
    from transformers import WhisperForConditionalGeneration, WhisperProcessor

    file_path = "path/to/your/audio/file.wav"
    chunks = segment_audio(file_path)

    print(f"Number of segments: {len(chunks)}")

    # Load Whisper model and processor
    processor = WhisperProcessor.from_pretrained("openai/whisper-base")
    model = WhisperForConditionalGeneration.from_pretrained("openai/whisper-base")

    transcriptions = transcribe_chunks(chunks, processor, model)

    for i, transcription in enumerate(transcriptions):
        print(f"Segment {i+1}: {transcription}")


if __name__ == "__main__":
    main()
