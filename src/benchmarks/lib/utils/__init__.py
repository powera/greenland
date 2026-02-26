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
    get_enabled_benchmark_codes,
    get_generator,
    get_runner,
    runner,
)

# Import all generators
from benchmarks.lib.generators import *

# Import all runners
from benchmarks.lib.runners import *

# Import registry last so all generators/runners are already loaded when it runs.
# This registers benchmark metadata (@benchmark decorators) for all benchmarks,
# and also registers generator/runner classes for benchmarks that don't use
# @generator/@runner decorators in their own files.
import benchmarks.lib.utils.registry as _benchmark_registry  # noqa: F401, E402

# Version info
__version__ = "1.0.0"
