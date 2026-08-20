#!/usr/bin/env python3
"""
Small file helpers shared by the audio generation scripts.

Nothing here is audio- or language-specific; it is plain file I/O that the
the gen_lithuanian_word_audio and OuteTTS command lines both need. Lithuanian orthography lives in
langtools.lt.utils, TTS prompts in prompts/audio/, and key loading in
clients.keys .
"""

from pathlib import Path
from typing import List, Union


def read_words_from_file(file_path: Union[str, Path]) -> List[str]:
    """
    Read words from a text file, one word per line.

    Args:
        file_path: Path to the text file, as a str or Path

    Returns:
        List of words/phrases, with empty lines filtered out
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            words = [line.strip() for line in f if line.strip()]
        return words
    except Exception as e:
        print(f"Error reading words file '{file_path}': {str(e)}")
        return []


def ensure_output_directory(output_dir: Union[str, Path]) -> Path:
    """
    Ensure output directory exists and return Path object.

    Args:
        output_dir: Directory path, as a str or Path

    Returns:
        Path object for the directory
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    return output_path
