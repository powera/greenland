#!/usr/bin/python3

"""
Registry for various benchmarks.
"""

import logging

from benchmarks.lib.utils.data_models import BenchmarkMetadata
from benchmarks.lib.utils.factory import benchmark, register_generator, register_runner

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Register benchmark metadata

from benchmarks.lib.generators.word_length_generator import WordLengthGenerator
from benchmarks.lib.runners.word_length_runner import WordLengthRunner


@benchmark(
    code="0011_word_length",
    name="Word Length",
    description="""
           A benchmark to evaluate a model's ability to count
           the total number of letters in a given word.""",
    category="token processing",
)
class WordLengthBenchmark:
    """Module container for word length benchmark."""

    pass


from benchmarks.lib.generators.letter_count_generator import LetterCountGenerator
from benchmarks.lib.runners.letter_count_runner import LetterCountRunner


@benchmark(
    code="0012_letter_count",
    name="Letter Count",
    description="""
           A benchmark to evaluate a model's ability to count
           how many times a specific letter appears in a word.""",
    category="token processing",
)
class LetterCountBenchmark:
    """Module container for letter count benchmark."""

    pass


from benchmarks.lib.generators.vowel_count_generator import VowelCountGenerator
from benchmarks.lib.runners.vowel_count_runner import VowelCountRunner

from benchmarks.lib.generators.syllable_count_generator import SyllableCountGenerator
from benchmarks.lib.runners.syllable_count_runner import SyllableCountRunner

from benchmarks.lib.generators.spell_check_generator import SpellCheckGenerator
from benchmarks.lib.runners.spell_check_runner import SpellCheckRunner


@benchmark(
    code="0015_spell_check",
    name="Spell Check",
    description="""
           A benchmark to evaluate a model's ability to identify
           misspelled words in a sentence and provide their correct spelling.""",
    category="word processing",
)
class SpellCheckBenchmark:
    """Module container for spell check benchmark."""

    pass


from benchmarks.lib.generators.antonym_generator import AntonymGenerator
from benchmarks.lib.runners.antonym_runner import AntonymRunner


@benchmark(
    code="0016_antonym",
    name="Antonym Identification",
    description="""
           A benchmark to evaluate a model's ability to identify
           the antonym of a word.""",
    category="word processing",
)
class AntonymBenchmark:
    """Module container for antonym benchmark."""

    pass


from benchmarks.lib.generators.definitions_generator import DefinitionsGenerator
from benchmarks.lib.runners.definitions_runner import DefinitionsRunner


@benchmark(
    code="0020_definitions",
    name="Definitions",
    description="""
           A benchmark to evaluate a model's ability to identify
           the correct definition of words.""",
    category="word processing",
)
class DefinitionsBenchmark:
    """Module container for definitions benchmark."""


from benchmarks.lib.generators.simple_arithmetic_generator import SimpleArithmeticGenerator
from benchmarks.lib.runners.simple_arithmetic_runner import SimpleArithmeticRunner


@benchmark(
    code="0021_simple_arithmetic",
    name="Simple Arithmetic",
    description="""
           A benchmark to evaluate a model's ability to perform basic arithmetic:
           addition, subtraction, multiplication, and division.""",
    category="simple math",
)
class SimpleArithmeticBenchmark:
    """Module container for simple arithmetic benchmark."""

    pass


from benchmarks.lib.generators.unit_conversion_generator import UnitConversionGenerator
from benchmarks.lib.runners.unit_conversion_runner import UnitConversionRunner


@benchmark(
    code="0022_unit_conversion",
    name="Unit Conversion",
    description="""
           A benchmark to evaluate a model's ability to accurately convert
           between different units of measurement.""",
    category="general knowledge",
)
class UnitConversionBenchmark:
    """Module container for unit conversion benchmark."""

    pass


from benchmarks.lib.generators.percentage_math_generator import PercentageMathGenerator
from benchmarks.lib.runners.percentage_math_runner import PercentageMathRunner


@benchmark(
    code="0024_percentage_math",
    name="Fractions and Percentages",
    description="""
           A benchmark to evaluate a model's ability to calculate percentages and fractions,
           including percent-of, fraction-of, and percent change problems.""",
    category="simple math",
)
class PercentageMathBenchmark:
    """Module container for fractions and percentages benchmark."""

    pass


from benchmarks.lib.generators.time_arithmetic_generator import TimeArithmeticGenerator
from benchmarks.lib.runners.time_arithmetic_runner import TimeArithmeticRunner


@benchmark(
    code="0026_time_arithmetic",
    name="Time Arithmetic",
    description="""
           A benchmark to evaluate a model's ability to add and subtract
           durations from clock times in 24-hour HH:MM format.""",
    category="simple math",
)
class TimeArithmeticBenchmark:
    """Module container for time arithmetic benchmark."""

    pass


from benchmarks.lib.generators.part_of_speech_generator import PartOfSpeechGenerator
from benchmarks.lib.runners.part_of_speech_runner import PartOfSpeechRunner


@benchmark(
    code="0032_part_of_speech",
    name="Part of Speech",
    description="""
           A benchmark to evaluate a model's ability to identify
           the part of speech of a specific word in a sentence.""",
    category="word processing",
)
class PartOfSpeechBenchmark:
    """Module container for part of speech benchmark."""

    pass


from benchmarks.lib.generators.lemma_generator import LemmaGenerator
from benchmarks.lib.runners.lemma_runner import LemmaRunner


@benchmark(
    code="0122_lemma",
    name="Lemma Identification",
    description="""
         A benchmark to evaluate a model's ability to identify the lemma (base form)
         of a given word. The lemma is the dictionary form:
         - For nouns: the singular form (e.g., "cats" → "cat")
         - For verbs: the infinitive form without "to" (e.g., "running" → "run")
         - For adjectives: the positive form (e.g., "better" → "good")
         """,
    category="word processing",
)
class LemmaBenchmark:
    """Module container for lemma identification benchmark."""

    pass


# Register generator and runner
register_generator("0122_lemma", LemmaGenerator)
register_runner("0122_lemma", LemmaRunner)

from benchmarks.lib.generators.translations_generator import TranslationGenerator
from benchmarks.lib.runners.translations_runner import TranslationRunner

translation_codes = {
    "en_fr": "0108_translation_en_fr",
    "en_zh": "0109_translation_en_zh",
    "sw_ko": "0110_translation_sw_ko",
}
for codepair, benchmark_code in translation_codes.items():

    @benchmark(
        code=benchmark_code,
        name=f"Translation {codepair}",
        description="""
               A benchmark to evaluate a model's ability to translate
               words from one language to another.""",
        category="translation",
    )
    class TranslationBenchmark:
        """Module container for translation benchmark."""

        pass

    register_generator(benchmark_code, TranslationGenerator)
    register_runner(benchmark_code, TranslationRunner)

from benchmarks.lib.generators.pinyin_letter_count_generator import (
    PinyinLetterCountGenerator,
)
from benchmarks.lib.runners.pinyin_letter_count_runner import PinyinLetterCountRunner


@benchmark(
    code="0051_pinyin_letters",
    name="Pinyin Letter Count",
    description="""A benchmark to evaluate a model's ability to count
           how many times a specific letter appears in the Pinyin representation
           of a Chinese sentence.""",
    category="token processing",
)
class PinyinLetterCountBenchmark:
    """Module container for Pinyin letter count benchmark."""

    pass


from benchmarks.lib.generators.word_to_ipa_generator import WordToIPAGenerator
from benchmarks.lib.runners.word_to_ipa_runner import WordToIPARunner


@benchmark(
    code="0061_word_to_ipa",
    name="Word to IPA",
    description="""
           A benchmark to evaluate a model's ability to convert words from multiple languages
           to their IPA (International Phonetic Alphabet) pronunciation.""",
    category="token processing",
)
class WordToIPABenchmark:
    """Module container for Word to IPA benchmark."""

    pass


from benchmarks.lib.generators.sentence_decomposition_generator import (
    SentenceDecompositionGenerator,
)
from benchmarks.lib.runners.sentence_decomposition_runner import SentenceDecompositionRunner


@benchmark(
    code="0062_sentence_decomposition",
    name="Sentence Decomposition",
    description="""
           A benchmark to evaluate a model's ability to produce multilingual
           token-level sentence decomposition with grammatical metadata.""",
    category="word processing",
)
class SentenceDecompositionBenchmark:
    """Module container for sentence decomposition benchmark."""

    pass


# Register the generator and runner classes
register_generator("0061_word_to_ipa", WordToIPAGenerator)
register_runner("0061_word_to_ipa", WordToIPARunner)

register_generator("0062_sentence_decomposition", SentenceDecompositionGenerator)
register_runner("0062_sentence_decomposition", SentenceDecompositionRunner)

# Register the geography benchmark
from benchmarks.lib.generators.geography_generator import GeographyGenerator
from benchmarks.lib.runners.geography_runner import GeographyRunner
from benchmarks.lib.generators.verb_forms_generator import VerbFormsGenerator
from benchmarks.lib.runners.verb_forms_runner import VerbFormsRunner


@benchmark(
    code="0151_geography",
    name="Geography Knowledge",
    description="""
           A benchmark to evaluate a model's knowledge of world geography through
           multiple-choice questions about countries, capitals, physical features,
           and other geographical information.""",
    category="general knowledge",
)
class GeographyBenchmark:
    """Module container for geography benchmark."""

    pass


register_generator("0151_geography", GeographyGenerator)
register_runner("0151_geography", GeographyRunner)

from benchmarks.lib.generators.syllogism_validity_generator import SyllogismValidityGenerator
from benchmarks.lib.runners.syllogism_validity_runner import SyllogismValidityRunner
from benchmarks.lib.generators.book_author_match_generator import BookAuthorMatchGenerator
from benchmarks.lib.runners.book_author_match_runner import BookAuthorMatchRunner
from benchmarks.lib.generators.food_category_classification_generator import (
    FoodCategoryClassificationGenerator,
)
from benchmarks.lib.runners.food_category_classification_runner import (
    FoodCategoryClassificationRunner,
)
from benchmarks.lib.generators.historical_event_year_generator import HistoricalEventYearGenerator
from benchmarks.lib.runners.historical_event_year_runner import HistoricalEventYearRunner


@benchmark(
    code="0152_syllogism_validity",
    name="Syllogism Validity",
    description="""
           A benchmark to evaluate whether a model can determine if short
           categorical syllogisms are logically valid.""",
    category="general knowledge",
)
class SyllogismValidityBenchmark:
    """Module container for syllogism validity benchmark."""

    pass


register_generator("0152_syllogism_validity", SyllogismValidityGenerator)
register_runner("0152_syllogism_validity", SyllogismValidityRunner)


@benchmark(
    code="0153_book_author_match",
    name="Book Author Match",
    description="""
           A benchmark to evaluate matching famous books to their correct authors.""",
    category="general knowledge",
)
class BookAuthorMatchBenchmark:
    """Module container for book-author benchmark."""

    pass


register_generator("0153_book_author_match", BookAuthorMatchGenerator)
register_runner("0153_book_author_match", BookAuthorMatchRunner)


@benchmark(
    code="0154_food_category_classification",
    name="Food Category Classification",
    description="""
           A benchmark to evaluate classification of food items by category.""",
    category="general knowledge",
)
class FoodCategoryClassificationBenchmark:
    """Module container for food category benchmark."""

    pass


register_generator("0154_food_category_classification", FoodCategoryClassificationGenerator)
register_runner("0154_food_category_classification", FoodCategoryClassificationRunner)


@benchmark(
    code="0155_historical_event_year",
    name="Historical Event Year",
    description="""
           A benchmark to evaluate selecting the correct year for major historical events.""",
    category="general knowledge",
)
class HistoricalEventYearBenchmark:
    """Module container for historical event year benchmark."""

    pass


register_generator("0155_historical_event_year", HistoricalEventYearGenerator)
register_runner("0155_historical_event_year", HistoricalEventYearRunner)

from benchmarks.lib.generators.synonyms_generator import SynonymsGenerator
from benchmarks.lib.runners.synonyms_runner import SynonymsRunner


@benchmark(
    code="0111_synonyms",
    name="Multilingual Synonym Generation",
    description="""
           A benchmark to evaluate a model's ability to generate noun synonyms
           in multiple languages.""",
    category="word processing",
    default_num_questions=64,
)
class SynonymsBenchmark:
    """Module container for multilingual synonym benchmark."""

    pass


register_generator("0111_synonyms", SynonymsGenerator)
register_runner("0111_synonyms", SynonymsRunner)


@benchmark(
    code="0121_verb_forms",
    name="Verb Forms",
    description="""
           A benchmark to evaluate a model's ability to generate full verb-form
           paradigms across persons and tenses in multiple languages.""",
    category="word processing",
    default_num_questions=56,
)
class VerbFormsBenchmark:
    """Module container for verb forms benchmark."""

    pass


register_generator("0121_verb_forms", VerbFormsGenerator)
register_runner("0121_verb_forms", VerbFormsRunner)

from benchmarks.lib.generators.validate_lemma_form_generator import ValidateLemmaFormGenerator
from benchmarks.lib.runners.validate_lemma_form_runner import ValidateLemmaFormRunner


@benchmark(
    code="0130_validate_lemma_form",
    name="Validate Lemma Form (lokys)",
    description="""
           A regression benchmark for the lokys agent's validate_lemma_form() function.
           Tests whether the LLM correctly identifies if a word is in its base/lemma form
           and suggests the correct form when it is not.""",
    category="agent regression",
    default_num_questions=25,
)
class ValidateLemmaFormBenchmark:
    """Module container for validate_lemma_form agent benchmark."""

    pass


register_generator("0130_validate_lemma_form", ValidateLemmaFormGenerator)
register_runner("0130_validate_lemma_form", ValidateLemmaFormRunner)

from benchmarks.lib.generators.validate_definition_generator import ValidateDefinitionGenerator
from benchmarks.lib.runners.validate_definition_runner import ValidateDefinitionRunner


@benchmark(
    code="0131_validate_definition",
    name="Validate Definition (lokys)",
    description="""
           A regression benchmark for the lokys agent's validate_definition() function.
           Tests whether the LLM correctly identifies well-formed vs. problematic word
           definitions (e.g. circular definitions, translations used as definitions).""",
    category="agent regression",
    default_num_questions=25,
)
class ValidateDefinitionBenchmark:
    """Module container for validate_definition agent benchmark."""

    pass


register_generator("0131_validate_definition", ValidateDefinitionGenerator)
register_runner("0131_validate_definition", ValidateDefinitionRunner)

from benchmarks.lib.generators.validate_translation_generator import ValidateTranslationGenerator
from benchmarks.lib.runners.validate_translation_runner import ValidateTranslationRunner


@benchmark(
    code="0132_validate_translation",
    name="Validate Translation (voras)",
    description="""
           A regression benchmark for the voras agent's validate_all_translations_for_word()
           function. Tests whether the LLM correctly identifies semantically incorrect or
           non-lemma translations across multiple target languages.""",
    category="agent regression",
    default_num_questions=20,
)
class ValidateTranslationBenchmark:
    """Module container for validate_all_translations_for_word agent benchmark."""

    pass


register_generator("0132_validate_translation", ValidateTranslationGenerator)
register_runner("0132_validate_translation", ValidateTranslationRunner)
