#!/usr/bin/python3

"""Base classes for implementing language model benchmarks."""

# BenchmarkRunner formerly in this file; imported for imports but not used locally
from lib.benchmarks.base_runner import BenchmarkRunner
from lib.benchmarks.base_generator import BenchmarkGenerator    

COMMON_SHORT_WORDS = [
    "chair", "music", "candle", "tree", "cat", "fish", "sun", "book", "ball",
    "hat", "water", "cake", "baby", "flower", "hill", "road", "clock", "door",
    "farm", "game", "hand", "ice", "jelly", "key", "moon", "nest", "orange", 
    "park", "quiet", "red", "sock"
]

COMMON_MEDIUM_WORDS = [
    "apple", "banana", "computer", "dog", "elephant", "freedom",
    "garden", "happiness", "internet", "journey", "knowledge", "language",
    "mountain", "notebook", "ocean", "patience", "question", "rainbow",
    "science", "technology", "umbrella", "variety", "window", "xylophone",
    "yesterday", "zebra"
]
COMMON_LONG_WORDS = [
    "strawberry", "programming", "mathematics", "engineering", "intelligence",
    "development", "application", "successful", "interesting", "beautiful",
    "ordinary", "atmosphere", "excitement", "conversation", "experience",
    "knowledge", "necessary", "community", "education", "information",
    "technology", "understanding", "opportunity", "relationship", "environment",
    "significant", "performance", "profession", "university", "restaurant",
    "breakfast", "president", "television", "government", "important",
    "computer", "different", "business", "possible", "together"
]