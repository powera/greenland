#!/usr/bin/python3

"""Benchmark system for evaluating language models."""

# Import base classes
from benchmarks.lib.benchmarks.base import BenchmarkGenerator, BenchmarkRunner

# Import data models
from benchmarks.lib.benchmarks.data_models import (
    AnswerType,
    BenchmarkMetadata,
    BenchmarkQuestion,
    BenchmarkResult,
    Difficulty,
    EvaluationCriteria,
)

# Import factory functions
from benchmarks.lib.benchmarks.factory import (
    benchmark,
    generator,
    get_all_benchmark_codes,
    get_benchmark_metadata,
    get_generator,
    get_runner,
    runner,
)

# Import all generators
from benchmarks.lib.benchmarks.generators import *

# Import all runners
from benchmarks.lib.benchmarks.runners import *

# Version info
__version__ = "1.0.0"
