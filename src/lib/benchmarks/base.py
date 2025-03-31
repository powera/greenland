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
    'abundance', 'appearance', 'banana', 'beautiful', 'challenge', 'computer',
    'delicious', 'difficult', 'education', 'elephant', 'fantastic', 'freedom',
    'garden', 'generation', 'happiness', 'important', 'internet', 'jewelry',
    'journey', 'knowledge', 'language', 'magazine', 'mountain', 'notebook',
    'ocean', 'operation', 'patience', 'positive', 'question', 'rainbow', 'reaction',
    'science', 'solution', 'technology', 'telephone', 'umbrella', 'universe',
    'victory', 'window', 'wonderful', 'yesterday', 'zealous'
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