#!/usr/bin/python3

"""Benchmark runners for evaluating language models."""

# Import all runners to register them with the factory
from lib.benchmarks.runners.antonym_runner import AntonymBenchmark
from lib.benchmarks.runners.spell_check_runner import SpellCheckBenchmark
from lib.benchmarks.runners.definitions_runner import DefinitionsBenchmark
from lib.benchmarks.runners.translation_runner import TranslationBenchmark

# Add imports for other runners as they are created
