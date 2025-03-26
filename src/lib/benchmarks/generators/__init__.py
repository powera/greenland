#!/usr/bin/python3

"""Benchmark question generators."""

# Import all generators to register them with the factory
from lib.benchmarks.generators.antonym_generator import AntonymGenerator
from lib.benchmarks.generators.spell_check_generator import SpellCheckGenerator
from lib.benchmarks.generators.definitions_generator import DefinitionsGenerator
from lib.benchmarks.generators.translation_generator import TranslationGenerator


# Add imports for other generators as they are created