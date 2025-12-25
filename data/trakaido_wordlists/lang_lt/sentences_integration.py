#!/usr/bin/python3

"""
Sentences Integration

This module loads generated sentences from JSON files and provides
them in the format expected by the level system.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional

def load_sentences(level: int = 20) -> List[Dict[str, str]]:
    """
    Load sentences from the JSON file for a specific level and convert to the format
    expected by the existing sentence system.
    
    Args:
        level: The level number (default: 20)
    
    Returns:
        List of sentence dictionaries with 'english' and 'lithuanian' keys
    """
    sentences_file = Path(__file__).parent / f"level_{level}_sentences.json"
    
    if not sentences_file.exists():
        print(f"Warning: Sentences file not found: {sentences_file}")
        return []
    
    try:
        with open(sentences_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Convert to the simple format expected by the level system
        sentences = []
        for sentence_data in data.get("sentences", []):
            sentences.append({
                "english": sentence_data["english"],
                "lithuanian": sentence_data["lithuanian"]
            })
        
        return sentences
        
    except Exception as e:
        print(f"Error loading sentences: {e}")
        return []

def get_sentences_with_metadata(level: int = 20) -> Dict[str, Any]:
    """
    Get sentences with full metadata including words used for a specific level.
    
    Args:
        level: The level number (default: 20)
    
    Returns:
        Dictionary with metadata and full sentence data
    """
    sentences_file = Path(__file__).parent / f"level_{level}_sentences.json"
    
    if not sentences_file.exists():
        print(f"Warning: Sentences file not found: {sentences_file}")
        return {"sentences": [], "metadata": {}}
    
    try:
        with open(sentences_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading sentences with metadata: {e}")
        return {"sentences": [], "metadata": {}}

def get_sentences_by_pattern(pattern: str, level: int = 20) -> List[Dict[str, str]]:
    """
    Get sentences filtered by pattern type (SVO, SVAO, etc.) for a specific level.
    
    Args:
        pattern: Pattern code like "SVO", "SVAO", "TSVOL", etc.
        level: The level number (default: 20)
        
    Returns:
        List of sentences matching the pattern
    """
    data = get_sentences_with_metadata(level)
    sentences = []
    
    for sentence_data in data.get("sentences", []):
        if sentence_data.get("pattern") == pattern:
            sentences.append({
                "english": sentence_data["english"],
                "lithuanian": sentence_data["lithuanian"]
            })
    
    return sentences

def get_sentences_by_tense(tense: str, level: int = 20) -> List[Dict[str, str]]:
    """
    Get sentences filtered by tense (present, past, future) for a specific level.
    
    Args:
        tense: Tense type ("present", "past", "future")
        level: The level number (default: 20)
        
    Returns:
        List of sentences in the specified tense
    """
    data = get_sentences_with_metadata(level)
    sentences = []
    
    for sentence_data in data.get("sentences", []):
        if sentence_data.get("tense") == tense:
            sentences.append({
                "english": sentence_data["english"],
                "lithuanian": sentence_data["lithuanian"]
            })
    
    return sentences

def get_words_used_in_sentences(level: int = 20) -> List[Dict[str, Any]]:
    """
    Get all unique words used in the sentences with their metadata for a specific level.
    
    Args:
        level: The level number (default: 20)
    
    Returns:
        List of unique words with their English/Lithuanian forms and GUIDs
    """
    data = get_sentences_with_metadata(level)
    words_seen = set()
    unique_words = []
    
    for sentence_data in data.get("sentences", []):
        for word in sentence_data.get("words_used", []):
            # Create a unique key for the word
            word_key = (word.get("english", ""), word.get("type", ""))
            
            if word_key not in words_seen:
                words_seen.add(word_key)
                unique_words.append(word)
    
    return unique_words

def get_sentence_statistics(level: int = 20) -> Dict[str, Any]:
    """
    Get statistics about the generated sentences for a specific level.
    
    Args:
        level: The level number (default: 20)
    
    Returns:
        Dictionary with various statistics
    """
    data = get_sentences_with_metadata(level)
    sentences = data.get("sentences", [])
    
    if not sentences:
        return {}
    
    # Count patterns
    pattern_counts = {}
    tense_counts = {}
    
    for sentence in sentences:
        pattern = sentence.get("pattern", "unknown")
        tense = sentence.get("tense", "unknown")
        
        pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
        tense_counts[tense] = tense_counts.get(tense, 0) + 1
    
    # Count unique words
    unique_words = get_words_used_in_sentences(level)
    word_type_counts = {}
    
    for word in unique_words:
        word_type = word.get("type", "unknown")
        word_type_counts[word_type] = word_type_counts.get(word_type, 0) + 1
    
    return {
        "level": level,
        "total_sentences": len(sentences),
        "pattern_distribution": pattern_counts,
        "tense_distribution": tense_counts,
        "unique_words": len(unique_words),
        "word_type_distribution": word_type_counts,
        "metadata": data.get("metadata", {})
    }

# Backward compatibility functions for level 20
def load_level_20_sentences() -> List[Dict[str, str]]:
    """
    Load level 20 sentences (backward compatibility function).
    
    Returns:
        List of sentence dictionaries with 'english' and 'lithuanian' keys
    """
    return load_sentences(20)

def get_level_20_sentences_with_metadata() -> Dict[str, Any]:
    """
    Get level 20 sentences with full metadata (backward compatibility function).
    
    Returns:
        Dictionary with metadata and full sentence data
    """
    return get_sentences_with_metadata(20)


# Example usage and testing
if __name__ == "__main__":
    print("Sentences Integration Test")
    print("=========================")
    
    # Test with default level (20)
    print("\nTesting Level 20:")
    sentences = load_sentences()
    print(f"Loaded {len(sentences)} sentences")
    
    # Test statistics
    stats = get_sentence_statistics()
    print(f"\nStatistics:")
    print(f"  Level: {stats.get('level', 'N/A')}")
    print(f"  Total sentences: {stats.get('total_sentences', 0)}")
    print(f"  Unique words: {stats.get('unique_words', 0)}")
    print(f"  Pattern distribution: {stats.get('pattern_distribution', {})}")
    print(f"  Tense distribution: {stats.get('tense_distribution', {})}")
    
    # Test filtering
    svo_sentences = get_sentences_by_pattern("SVO")
    print(f"\nSVO sentences: {len(svo_sentences)}")
    
    present_sentences = get_sentences_by_tense("present")
    print(f"Present tense sentences: {len(present_sentences)}")
    
    # Show some examples
    print(f"\nFirst 5 sentences:")
    for i, sentence in enumerate(sentences[:5]):
        print(f"  {i+1}. EN: {sentence['english']}")
        print(f"     LT: {sentence['lithuanian']}")
    
    # Test with a different level (if available)
    print(f"\nTesting Level 25 (if available):")
    level_25_sentences = load_sentences(25)
    print(f"Loaded {len(level_25_sentences)} level 25 sentences")
    
    if level_25_sentences:
        level_25_stats = get_sentence_statistics(25)
        print(f"Level 25 statistics: {level_25_stats.get('total_sentences', 0)} sentences")