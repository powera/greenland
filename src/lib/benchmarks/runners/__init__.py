#!/usr/bin/python3

"""Benchmark runners for evaluating language models."""

# Import all runners to register them with the factory
from lib.benchmarks.runners.antonym_runner import AntonymRunner
from lib.benchmarks.runners.spell_check_runner import SpellCheckRunner
from lib.benchmarks.runners.definitions_runner import DefinitionsRunner
from lib.benchmarks.runners.translations_runner import TranslationRunner

# Add imports for other runners as they are created
