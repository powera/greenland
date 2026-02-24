#!/usr/bin/python3

"""Benchmark question generators."""

# Import all generators to register them with the factory
from benchmarks.lib.generators.antonym_generator import AntonymGenerator
from benchmarks.lib.generators.definitions_generator import DefinitionsGenerator
from benchmarks.lib.generators.word_to_ipa_generator import WordToIPAGenerator

# Knowledge generators
from benchmarks.lib.generators.geography_generator import GeographyGenerator
from benchmarks.lib.generators.lemma_generator import LemmaGenerator
from benchmarks.lib.generators.letter_count_generator import LetterCountGenerator
from benchmarks.lib.generators.part_of_speech_generator import PartOfSpeechGenerator
from benchmarks.lib.generators.pinyin_letter_count_generator import (
    PinyinLetterCountGenerator,
)
from benchmarks.lib.generators.spell_check_generator import SpellCheckGenerator
from benchmarks.lib.generators.synonyms_generator import SynonymsGenerator
from benchmarks.lib.generators.translations_generator import TranslationGenerator
from benchmarks.lib.generators.unit_conversion_generator import UnitConversionGenerator
from benchmarks.lib.generators.word_length_generator import WordLengthGenerator

from benchmarks.lib.generators.sentence_decomposition_generator import (
    SentenceDecompositionGenerator,
)

from benchmarks.lib.generators.verb_forms_generator import VerbFormsGenerator

# Agent regression benchmark generators
from benchmarks.lib.generators.validate_lemma_form_generator import ValidateLemmaFormGenerator
from benchmarks.lib.generators.validate_definition_generator import ValidateDefinitionGenerator
from benchmarks.lib.generators.validate_translation_generator import ValidateTranslationGenerator

# Knowledge benchmarks 0152-0155
from benchmarks.lib.generators.syllogism_validity_generator import SyllogismValidityGenerator
from benchmarks.lib.generators.book_author_match_generator import BookAuthorMatchGenerator
from benchmarks.lib.generators.food_category_classification_generator import FoodCategoryClassificationGenerator
from benchmarks.lib.generators.historical_event_year_generator import HistoricalEventYearGenerator
