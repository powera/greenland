#!/usr/bin/python3

"""Benchmark system for evaluating language models."""

# Import base classes
from benchmarks.lib.utils.base import BenchmarkGenerator, BenchmarkRunner

# Import data models
from benchmarks.lib.utils.data_models import (
    AnswerType,
    BenchmarkMetadata,
    BenchmarkQuestion,
    BenchmarkResult,
    Difficulty,
    EvaluationCriteria,
)

# Import factory functions
from benchmarks.lib.utils.factory import (
    benchmark,
    generator,
    get_all_benchmark_codes,
    get_benchmark_metadata,
    get_generator,
    get_runner,
    runner,
)

# Import all generators
from benchmarks.lib.generators import *

# Import all runners
from benchmarks.lib.runners import *

# Version info
__version__ = "1.0.0"
