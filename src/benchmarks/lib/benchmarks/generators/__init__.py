#!/usr/bin/python3

"""Benchmark question generators."""

# Import all generators to register them with the factory
from benchmarks.lib.benchmarks.generators.antonym_generator import AntonymGenerator
from benchmarks.lib.benchmarks.generators.definitions_generator import DefinitionsGenerator
from benchmarks.lib.benchmarks.generators.english_to_ipa_generator import EnglishToIPAGenerator

# Knowledge generators
from benchmarks.lib.benchmarks.generators.geography_generator import GeographyGenerator
from benchmarks.lib.benchmarks.generators.lemma_generator import LemmaGenerator
from benchmarks.lib.benchmarks.generators.letter_count_generator import LetterCountGenerator
from benchmarks.lib.benchmarks.generators.part_of_speech_generator import PartOfSpeechGenerator
from benchmarks.lib.benchmarks.generators.pinyin_letter_count_generator import (
    PinyinLetterCountGenerator,
)
from benchmarks.lib.benchmarks.generators.spell_check_generator import SpellCheckGenerator
from benchmarks.lib.benchmarks.generators.translations_generator import TranslationGenerator
from benchmarks.lib.benchmarks.generators.unit_conversion_generator import UnitConversionGenerator
from benchmarks.lib.benchmarks.generators.word_length_generator import WordLengthGenerator
