#!/usr/bin/env python3
"""
Shared utilities for audio generation scripts.

This module contains common functions used by both genaudio_outetts.py and gen_audio.py
for Lithuanian text-to-speech processing.
"""

import re
from typing import List, Optional
from pathlib import Path

# Complete list of Lithuanian letters and diacritics
# Lithuanian alphabet: a ą b c č d e ę ė f g h i į y j k l m n o p r s š t u ų ū v z ž
LITHUANIAN_CHARS = "aąbcčdeęėfghiįyjklmnoprsštuųūvzž"

# TTS instructions for Lithuanian pronunciation
LITHUANIAN_TTS_INSTRUCTIONS = """
Pronounce this Lithuanian word or phrase with clear, accurate pronunciation:
- Emphasize proper Lithuanian vowel length and stress patterns
- Maintain proper Lithuanian intonation with a natural rise and fall
- Articulate each syllable distinctly without rushing
- Use standard Lithuanian pronunciation, not dialectal variants
- Pronounce every phoneme fully - do not drop consonant clusters or reduce unstressed vowels
- For phrases, maintain proper spacing and natural flow between words
"""


def sanitize_lithuanian_word(word: str) -> str:
    """
    Sanitize a Lithuanian word or phrase for use as a filename.
    
    Args:
        word: The Lithuanian word or phrase to sanitize
    
    Returns:
        Sanitized filename-safe version or empty string if invalid
    """
    word = word.strip().lower()
    
    # Replace spaces with underscores for multi-word phrases
    word_with_underscores = word.replace(' ', '_')
    
    # Allow all Lithuanian letters, basic Latin letters, and safe characters
    sanitized = re.sub(r'[^a-z' + LITHUANIAN_CHARS + r'\-_]', '', word_with_underscores)
    
    if not sanitized or len(sanitized) > 100:
        return ""
        
    return sanitized


def read_words_from_file(file_path: str) -> List[str]:
    """
    Read words from a text file, one word per line.
    
    Args:
        file_path: Path to the text file
    
    Returns:
        List of words/phrases, with empty lines filtered out
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            words = [line.strip() for line in f if line.strip()]
        return words
    except Exception as e:
        print(f"Error reading words file '{file_path}': {str(e)}")
        return []


def ensure_output_directory(output_dir: str) -> Path:
    """
    Ensure output directory exists and return Path object.
    
    Args:
        output_dir: Directory path as string
    
    Returns:
        Path object for the directory
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    return output_path


def read_api_key_from_file(key_file: str = "keys/openai.key") -> Optional[str]:
    """
    Read OpenAI API key from a file.
    
    Args:
        key_file: Path to the file containing the API key
    
    Returns:
        API key as string or None if file not found/readable
    """
    try:
        key_path = Path(key_file)
        if key_path.exists():
            with open(key_path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        return None
    except Exception as e:
        print(f"Error reading API key file: {str(e)}")
        return None