#!/usr/bin/python3

"""Benchmark system for evaluating language models."""

# Import data models
from lib.benchmarks.data_models import (
    BenchmarkQuestion, BenchmarkResult, BenchmarkMetadata,
    AnswerType, Difficulty, EvaluationCriteria
)

# Import base classes
from lib.benchmarks.base import BenchmarkGenerator, BenchmarkRunner

# Import factory functions
from lib.benchmarks.factory import (
    get_generator, get_runner, get_all_benchmark_codes,
    get_benchmark_metadata, benchmark, generator, runner
)

# Import all generators
from lib.benchmarks.generators import *

# Import all runners
from lib.benchmarks.runners import *

# Version info
__version__ = "1.0.0"
