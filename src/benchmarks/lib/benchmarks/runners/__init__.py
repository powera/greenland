#!/usr/bin/python3

"""Benchmark runners for evaluating language models."""

# Import all runners to register them with the factory
from benchmarks.lib.benchmarks.runners.antonym_runner import AntonymRunner
from benchmarks.lib.benchmarks.runners.definitions_runner import DefinitionsRunner
from benchmarks.lib.benchmarks.runners.english_to_ipa_runner import EnglishToIPARunner

# Knowledge questions
from benchmarks.lib.benchmarks.runners.geography_runner import GeographyRunner
from benchmarks.lib.benchmarks.runners.lemma_runner import LemmaRunner
from benchmarks.lib.benchmarks.runners.letter_count_runner import LetterCountRunner
from benchmarks.lib.benchmarks.runners.part_of_speech_runner import PartOfSpeechRunner
from benchmarks.lib.benchmarks.runners.pinyin_letter_count_runner import PinyinLetterCountRunner
from benchmarks.lib.benchmarks.runners.spell_check_runner import SpellCheckRunner
from benchmarks.lib.benchmarks.runners.translations_runner import TranslationRunner
from benchmarks.lib.benchmarks.runners.unit_conversion_runner import UnitConversionRunner
from benchmarks.lib.benchmarks.runners.word_length_runner import WordLengthRunner
