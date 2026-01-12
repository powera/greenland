#!/usr/bin/env python3
"""
Lape - Grammar Facts Generator Agent

⚠️  IMPORTANT: This agent has a custom Barsukas API in src/barsukas/routes/agents.py
    If you modify the public interface of this agent, you MUST update:
    - /agents/generate-grammar-fact/<lemma_id> endpoint
    Keep the API contract in sync to prevent runtime errors!

This agent generates language-specific grammatical facts for lemmas using LLM queries.
It supports various types of grammar facts that can be specified via command line parameters.

Supported fact types:

Noun facts:
- measure_words (Chinese): Generate appropriate measure words/classifiers for nouns
- grammatical_gender (French, Spanish, German, etc.): Determine noun gender (masculine, feminine, neuter)
- countability (English): Classify nouns as countable, uncountable, or both
- declension_class (Lithuanian): Determine which declension class (1-5) a noun follows
- animacy (English): Classify nouns as animate or inanimate (affects grammar in some languages)

Verb facts:
- verb_transitivity (English): Classify as transitive, intransitive, ditransitive, or ambitransitive
- verb_reflexivity (French, Spanish, German, Lithuanian, Italian): Identify reflexive verbs
- auxiliary_verb (French, German, Italian): Which auxiliary verb is used in compound tenses

Note: number_type (plurale_tantum/singulare_tantum) is auto-detected during form generation by Vilkas.

"Lape" means "fox" in Lithuanian - clever and precise in analyzing grammar!
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import constants
import util.prompt_loader
from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_guid_arg,
    add_language_args,
    add_llm_args,
    get_data_source_config,
)
from agents.common.lemma_selection import (
    LemmaQueryBuilder,
    apply_limit_and_sample_rate,
    get_lemmas_for_agent,
)
from barsukas.utils.task_queue import (
    TaskStatus,
    claim_next_task,
    enqueue_task,
    mark_task_complete,
    mark_task_failed,
)
from clients.types import Schema, SchemaProperty
from clients.unified_client import UnifiedLLMClient
from wordfreq.storage.backend import create_session as create_backend_session
from wordfreq.storage.backend.config import BackendType, DataSourceConfig
from wordfreq.storage.crud.grammar_fact import (
    add_grammar_fact,
    get_grammar_fact_value,
    get_grammar_facts,
)
from wordfreq.storage.crud.operation_log import log_operation
from wordfreq.storage.models.schema import Lemma
from wordfreq.storage.translation_helpers import get_translation
from wordfreq.translation.client import LinguisticClient

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class LapeAgent:
    """Agent for generating grammar facts for lemmas."""

    # Language-specific gender systems configuration
    GENDER_SYSTEMS = {
        "fr": {
            "name": "French",
            "genders": ["masculine", "feminine"],
            "description": "2-way system (masculine/feminine)",
        },
        "lt": {
            "name": "Lithuanian",
            "genders": ["masculine", "feminine"],
            "description": "2-way system (masculine/feminine)",
        },
        "es": {
            "name": "Spanish",
            "genders": ["masculine", "feminine"],
            "description": "2-way system (masculine/feminine)",
        },
        "de": {
            "name": "German",
            "genders": ["masculine", "feminine", "neuter"],
            "description": "3-way system (masculine/feminine/neuter)",
        },
        "pt": {
            "name": "Portuguese",
            "genders": ["masculine", "feminine"],
            "description": "2-way system (masculine/feminine)",
        },
        "ru": {
            "name": "Russian",
            "genders": ["masculine", "feminine", "neuter"],
            "description": "3-way system (masculine/feminine/neuter)",
        },
        "it": {
            "name": "Italian",
            "genders": ["masculine", "feminine"],
            "description": "2-way system (masculine/feminine)",
        },
    }

    # Language-specific auxiliary verb systems
    AUXILIARY_SYSTEMS = {
        "fr": {
            "name": "French",
            "auxiliaries": ["avoir", "être"],
            "description": "avoir (most verbs) or être (motion/reflexive verbs)",
        },
        "de": {
            "name": "German",
            "auxiliaries": ["haben", "sein"],
            "description": "haben (most verbs) or sein (motion/state change verbs)",
        },
        "it": {
            "name": "Italian",
            "auxiliaries": ["avere", "essere"],
            "description": "avere (most verbs) or essere (motion/reflexive verbs)",
        },
    }

    # Language-specific reflexivity systems
    REFLEXIVITY_SYSTEMS = {
        "fr": {
            "name": "French",
            "values": ["inherently_reflexive", "optionally_reflexive", "non_reflexive"],
            "description": "se + verb for reflexive forms",
        },
        "es": {
            "name": "Spanish",
            "values": ["inherently_reflexive", "optionally_reflexive", "non_reflexive"],
            "description": "se + verb for reflexive forms",
        },
        "de": {
            "name": "German",
            "values": ["inherently_reflexive", "optionally_reflexive", "non_reflexive"],
            "description": "sich + verb for reflexive forms",
        },
        "lt": {
            "name": "Lithuanian",
            "values": ["inherently_reflexive", "optionally_reflexive", "non_reflexive"],
            "description": "-si/-tis suffix for reflexive forms",
        },
        "it": {
            "name": "Italian",
            "values": ["inherently_reflexive", "optionally_reflexive", "non_reflexive"],
            "description": "si + verb for reflexive forms",
        },
    }

    # Supported fact types and their required parameters
    SUPPORTED_FACT_TYPES = {
        "measure_words": {
            "languages": ["zh"],  # Chinese only for now
            "required_pos": ["noun"],
            "description": "Generate Chinese measure words/classifiers for nouns",
        },
        "grammatical_gender": {
            "languages": list(GENDER_SYSTEMS.keys()),
            "required_pos": ["noun"],
            "description": "Determine grammatical gender (masculine, feminine, neuter)",
        },
        "verb_transitivity": {
            "languages": ["en"],  # English-based, applies to base concept
            "required_pos": ["verb"],
            "description": "Classify verbs as transitive, intransitive, ditransitive, or ambitransitive",
        },
        "verb_reflexivity": {
            "languages": ["fr", "es", "de", "lt", "it"],
            "required_pos": ["verb"],
            "description": "Identify inherently reflexive, optionally reflexive, or non-reflexive verbs",
        },
        "countability": {
            "languages": ["en"],  # English-based, applies to base concept
            "required_pos": ["noun"],
            "description": "Classify nouns as countable, uncountable, or both",
        },
        "declension_class": {
            "languages": ["lt"],  # Lithuanian for now
            "required_pos": ["noun"],
            "description": "Determine declension class (1-5 for Lithuanian nouns)",
        },
        "auxiliary_verb": {
            "languages": ["fr", "de", "it"],
            "required_pos": ["verb"],
            "description": "Identify auxiliary verb used in compound tenses (avoir/être, haben/sein, etc.)",
        },
        "animacy": {
            "languages": ["en"],  # English-based, applies to base concept
            "required_pos": ["noun"],
            "description": "Classify nouns as animate or inanimate (affects case in some languages)",
        },
    }

    # Grouped task presets mapping to multiple fact types
    TASK_PRESETS = {
        "all": list(SUPPORTED_FACT_TYPES.keys()),
        "gender": ["grammatical_gender"],
        "measure-words": ["measure_words"],
        "nouns": ["grammatical_gender", "countability", "animacy", "declension_class"],
        "verbs": ["verb_transitivity", "verb_reflexivity", "auxiliary_verb"],
    }

    def __init__(self, config: DataSourceConfig):
        """
        Initialize the Lape agent.

        Args:
            config: DataSourceConfig with model, debug, and backend settings (required)
        """
        self.config = config
        self.debug = config.debug

        # Keep db_path for backward compatibility with LinguisticClient
        if self.config.backend_type == BackendType.SQLITE:
            self.db_path = self.config.sqlite_path
        else:
            self.db_path = None

        self.linguistic_client = None  # Lazy initialization
        self.llm_client = None  # For direct LLM calls

        if self.debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self):
        """Get database session using backend abstraction."""
        return create_backend_session(self.config)

    def get_linguistic_client(self):
        """Get or create linguistic client for LLM queries."""
        if self.linguistic_client is None:
            self.linguistic_client = LinguisticClient(
                model=self.config.model, db_path=self.db_path, debug=self.debug
            )
        return self.linguistic_client

    def get_llm_client(self):
        """Get or create LLM client for direct queries."""
        if self.llm_client is None:
            self.llm_client = UnifiedLLMClient.from_config(self.config)
            if self.config.model:
                self.llm_client.warm_model(self.config.model)
        return self.llm_client

    def generate_measure_words(
        self, lemma: Lemma, chinese_translation: str, session=None
    ) -> Tuple[Optional[str], Optional[str], float]:
        """
        Generate Chinese measure word(s) for a noun using LLM.

        Args:
            lemma: The Lemma object
            chinese_translation: The Chinese translation of the word
            session: Database session (optional)

        Returns:
            Tuple of (measure_word, explanation, confidence)
        """
        if lemma.pos_type != "noun":
            logger.warning(
                f"Lemma '{lemma.lemma_text}' is not a noun, skipping measure word generation"
            )
            return None, None, 0.0

        # Load prompts
        try:
            context = util.prompt_loader.get_context("wordfreq", "measure_words")
            prompt_template = util.prompt_loader.get_prompt("wordfreq", "measure_words")
        except Exception as e:
            logger.error(f"Failed to load measure_words prompts: {e}")
            return None, None, 0.0

        # Format prompt
        prompt_text = prompt_template.format(
            english_word=lemma.lemma_text,
            chinese_translation=chinese_translation,
            pos_type=lemma.pos_type,
            definition=lemma.definition_text or "N/A",
        )

        # Define JSON schema for response
        schema = Schema(
            name="MeasureWordGeneration",
            description="Generate Chinese measure words/classifiers for nouns",
            properties={
                "primary_measure_word": SchemaProperty(
                    "string", "The primary/most common measure word"
                ),
                "alternative_measure_words": SchemaProperty(
                    "array",
                    "List of alternative measure words that can also be used",
                    items={"type": "string"},
                ),
                "explanation": SchemaProperty(
                    "string", "Brief explanation of why this measure word is appropriate"
                ),
                "confidence": SchemaProperty(
                    "number", "Confidence score 0.0-1.0", minimum=0.0, maximum=1.0
                ),
            },
        )

        # Query LLM
        try:
            client = self.get_llm_client()
            response = client.generate_chat(prompt=prompt_text, json_schema=schema, context=context)

            # Extract structured data
            if response.structured_data:
                result = response.structured_data
            else:
                logger.error(f"No structured data received for '{lemma.lemma_text}'")
                return None, None, 0.0

            measure_word = result.get("primary_measure_word", None)
            alternatives = result.get("alternative_measure_words", [])
            explanation = result.get("explanation", "")
            confidence = float(result.get("confidence", 0.5))

            # Combine primary and alternatives
            if alternatives:
                all_measure_words = f"{measure_word} (alt: {', '.join(alternatives)})"
            else:
                all_measure_words = measure_word

            logger.info(
                f"Generated measure word for '{lemma.lemma_text}': {all_measure_words} "
                f"(confidence: {confidence:.2f})"
            )

            return measure_word, explanation, confidence

        except Exception as e:
            logger.error(f"Failed to generate measure word for '{lemma.lemma_text}': {e}")
            return None, None, 0.0

    def generate_grammatical_gender(
        self, lemma: Lemma, target_translation: str, language_code: str, session=None
    ) -> Tuple[Optional[str], Optional[str], float]:
        """
        Generate grammatical gender for a noun using LLM.

        Args:
            lemma: The Lemma object
            target_translation: The translation in the target language
            language_code: Target language code (e.g., 'fr', 'lt', 'de')
            session: Database session (optional)

        Returns:
            Tuple of (gender, explanation, confidence)
        """
        if lemma.pos_type != "noun":
            logger.warning(f"Lemma '{lemma.lemma_text}' is not a noun, skipping gender generation")
            return None, None, 0.0

        if language_code not in self.GENDER_SYSTEMS:
            logger.error(f"Language '{language_code}' does not have a configured gender system")
            return None, None, 0.0

        gender_config = self.GENDER_SYSTEMS[language_code]
        language_name = gender_config["name"]
        valid_genders = ", ".join(gender_config["genders"])
        gender_system = gender_config["description"]

        # Load prompts
        try:
            context = util.prompt_loader.get_context("wordfreq", "grammatical_gender")
            prompt_template = util.prompt_loader.get_prompt("wordfreq", "grammatical_gender")
        except Exception as e:
            logger.error(f"Failed to load grammatical_gender prompts: {e}")
            return None, None, 0.0

        # Format prompt
        prompt_text = prompt_template.format(
            english_word=lemma.lemma_text,
            target_translation=target_translation,
            pos_type=lemma.pos_type,
            definition=lemma.definition_text or "N/A",
            language_name=language_name,
            language_code=language_code,
            gender_system=gender_system,
            valid_genders=valid_genders,
        )

        # Define JSON schema for response
        schema = Schema(
            name="GrammaticalGenderGeneration",
            description=f"Determine grammatical gender for {language_name} nouns",
            properties={
                "gender": SchemaProperty(
                    "string",
                    f"The grammatical gender: {valid_genders}",
                    enum=gender_config["genders"],
                ),
                "explanation": SchemaProperty(
                    "string", "Brief explanation of why this gender is correct"
                ),
                "confidence": SchemaProperty(
                    "number", "Confidence score 0.0-1.0", minimum=0.0, maximum=1.0
                ),
            },
        )

        # Query LLM
        try:
            client = self.get_llm_client()
            response = client.generate_chat(prompt=prompt_text, json_schema=schema, context=context)

            # Extract structured data
            if response.structured_data:
                result = response.structured_data
            else:
                logger.error(f"No structured data received for '{lemma.lemma_text}'")
                return None, None, 0.0

            gender = result.get("gender", None)
            explanation = result.get("explanation", "")
            confidence = float(result.get("confidence", 0.5))

            logger.info(
                f"Generated gender for '{lemma.lemma_text}' ({target_translation}): "
                f"{gender} (confidence: {confidence:.2f})"
            )

            return gender, explanation, confidence

        except Exception as e:
            logger.error(f"Failed to generate gender for '{lemma.lemma_text}': {e}")
            return None, None, 0.0

    def generate_verb_transitivity(
        self, lemma: Lemma, session=None
    ) -> Tuple[Optional[str], Optional[str], float]:
        """
        Generate verb transitivity classification using LLM.

        Args:
            lemma: The Lemma object
            session: Database session (optional)

        Returns:
            Tuple of (transitivity, explanation, confidence)
        """
        if lemma.pos_type != "verb":
            logger.warning(f"Lemma '{lemma.lemma_text}' is not a verb, skipping transitivity")
            return None, None, 0.0

        # Load prompts
        try:
            context = util.prompt_loader.get_context("wordfreq", "verb_transitivity")
            prompt_template = util.prompt_loader.get_prompt("wordfreq", "verb_transitivity")
        except Exception as e:
            logger.error(f"Failed to load verb_transitivity prompts: {e}")
            return None, None, 0.0

        # Format prompt
        prompt_text = prompt_template.format(
            english_word=lemma.lemma_text,
            pos_type=lemma.pos_type,
            definition=lemma.definition_text or "N/A",
        )

        # Define JSON schema for response
        schema = Schema(
            name="VerbTransitivityClassification",
            description="Classify verb transitivity",
            properties={
                "transitivity": SchemaProperty(
                    "string",
                    "The transitivity classification",
                    enum=["transitive", "intransitive", "ditransitive", "ambitransitive"],
                ),
                "explanation": SchemaProperty(
                    "string", "Brief explanation if notable"
                ),
                "confidence": SchemaProperty(
                    "number", "Confidence score 0.0-1.0", minimum=0.0, maximum=1.0
                ),
            },
        )

        # Query LLM
        try:
            client = self.get_llm_client()
            response = client.generate_chat(prompt=prompt_text, json_schema=schema, context=context)

            if response.structured_data:
                result = response.structured_data
            else:
                logger.error(f"No structured data received for '{lemma.lemma_text}'")
                return None, None, 0.0

            transitivity = result.get("transitivity", None)
            explanation = result.get("explanation", "")
            confidence = float(result.get("confidence", 0.5))

            logger.info(
                f"Generated transitivity for '{lemma.lemma_text}': {transitivity} "
                f"(confidence: {confidence:.2f})"
            )

            return transitivity, explanation, confidence

        except Exception as e:
            logger.error(f"Failed to generate transitivity for '{lemma.lemma_text}': {e}")
            return None, None, 0.0

    def generate_verb_reflexivity(
        self, lemma: Lemma, target_translation: str, language_code: str, session=None
    ) -> Tuple[Optional[str], Optional[str], float]:
        """
        Generate verb reflexivity classification using LLM.

        Args:
            lemma: The Lemma object
            target_translation: The translation in the target language
            language_code: Target language code
            session: Database session (optional)

        Returns:
            Tuple of (reflexivity, explanation, confidence)
        """
        if lemma.pos_type != "verb":
            logger.warning(f"Lemma '{lemma.lemma_text}' is not a verb, skipping reflexivity")
            return None, None, 0.0

        if language_code not in self.REFLEXIVITY_SYSTEMS:
            logger.error(f"Language '{language_code}' does not have reflexivity configuration")
            return None, None, 0.0

        reflex_config = self.REFLEXIVITY_SYSTEMS[language_code]
        language_name = reflex_config["name"]

        # Load prompts
        try:
            context = util.prompt_loader.get_context("wordfreq", "verb_reflexivity")
            prompt_template = util.prompt_loader.get_prompt("wordfreq", "verb_reflexivity")
        except Exception as e:
            logger.error(f"Failed to load verb_reflexivity prompts: {e}")
            return None, None, 0.0

        # Format prompt
        prompt_text = prompt_template.format(
            english_word=lemma.lemma_text,
            target_translation=target_translation,
            pos_type=lemma.pos_type,
            definition=lemma.definition_text or "N/A",
            language_name=language_name,
            language_code=language_code,
        )

        # Define JSON schema for response
        schema = Schema(
            name="VerbReflexivityClassification",
            description=f"Classify verb reflexivity for {language_name}",
            properties={
                "reflexivity": SchemaProperty(
                    "string",
                    "The reflexivity classification",
                    enum=reflex_config["values"],
                ),
                "explanation": SchemaProperty(
                    "string", "Brief explanation with reflexive form if applicable"
                ),
                "confidence": SchemaProperty(
                    "number", "Confidence score 0.0-1.0", minimum=0.0, maximum=1.0
                ),
            },
        )

        # Query LLM
        try:
            client = self.get_llm_client()
            response = client.generate_chat(prompt=prompt_text, json_schema=schema, context=context)

            if response.structured_data:
                result = response.structured_data
            else:
                logger.error(f"No structured data received for '{lemma.lemma_text}'")
                return None, None, 0.0

            reflexivity = result.get("reflexivity", None)
            explanation = result.get("explanation", "")
            confidence = float(result.get("confidence", 0.5))

            logger.info(
                f"Generated reflexivity for '{lemma.lemma_text}' ({target_translation}): "
                f"{reflexivity} (confidence: {confidence:.2f})"
            )

            return reflexivity, explanation, confidence

        except Exception as e:
            logger.error(f"Failed to generate reflexivity for '{lemma.lemma_text}': {e}")
            return None, None, 0.0

    def generate_countability(
        self, lemma: Lemma, session=None
    ) -> Tuple[Optional[str], Optional[str], float]:
        """
        Generate noun countability classification using LLM.

        Args:
            lemma: The Lemma object
            session: Database session (optional)

        Returns:
            Tuple of (countability, explanation, confidence)
        """
        if lemma.pos_type != "noun":
            logger.warning(f"Lemma '{lemma.lemma_text}' is not a noun, skipping countability")
            return None, None, 0.0

        # Load prompts
        try:
            context = util.prompt_loader.get_context("wordfreq", "countability")
            prompt_template = util.prompt_loader.get_prompt("wordfreq", "countability")
        except Exception as e:
            logger.error(f"Failed to load countability prompts: {e}")
            return None, None, 0.0

        # Format prompt
        prompt_text = prompt_template.format(
            english_word=lemma.lemma_text,
            pos_type=lemma.pos_type,
            definition=lemma.definition_text or "N/A",
        )

        # Define JSON schema for response
        schema = Schema(
            name="NounCountabilityClassification",
            description="Classify noun countability",
            properties={
                "countability": SchemaProperty(
                    "string",
                    "The countability classification",
                    enum=["countable", "uncountable", "both"],
                ),
                "explanation": SchemaProperty(
                    "string", "Brief explanation if notable"
                ),
                "confidence": SchemaProperty(
                    "number", "Confidence score 0.0-1.0", minimum=0.0, maximum=1.0
                ),
            },
        )

        # Query LLM
        try:
            client = self.get_llm_client()
            response = client.generate_chat(prompt=prompt_text, json_schema=schema, context=context)

            if response.structured_data:
                result = response.structured_data
            else:
                logger.error(f"No structured data received for '{lemma.lemma_text}'")
                return None, None, 0.0

            countability = result.get("countability", None)
            explanation = result.get("explanation", "")
            confidence = float(result.get("confidence", 0.5))

            logger.info(
                f"Generated countability for '{lemma.lemma_text}': {countability} "
                f"(confidence: {confidence:.2f})"
            )

            return countability, explanation, confidence

        except Exception as e:
            logger.error(f"Failed to generate countability for '{lemma.lemma_text}': {e}")
            return None, None, 0.0

    def generate_declension_class(
        self, lemma: Lemma, target_translation: str, language_code: str, session=None
    ) -> Tuple[Optional[str], Optional[str], float]:
        """
        Generate noun declension class using LLM.

        Args:
            lemma: The Lemma object
            target_translation: The translation in the target language
            language_code: Target language code (currently only 'lt' for Lithuanian)
            session: Database session (optional)

        Returns:
            Tuple of (declension_class, explanation, confidence)
        """
        if lemma.pos_type != "noun":
            logger.warning(f"Lemma '{lemma.lemma_text}' is not a noun, skipping declension class")
            return None, None, 0.0

        if language_code != "lt":
            logger.error(f"Declension class only supported for Lithuanian, got '{language_code}'")
            return None, None, 0.0

        # Load prompts
        try:
            context = util.prompt_loader.get_context("wordfreq", "declension_class")
            prompt_template = util.prompt_loader.get_prompt("wordfreq", "declension_class")
        except Exception as e:
            logger.error(f"Failed to load declension_class prompts: {e}")
            return None, None, 0.0

        # Format prompt
        prompt_text = prompt_template.format(
            english_word=lemma.lemma_text,
            target_translation=target_translation,
            pos_type=lemma.pos_type,
            definition=lemma.definition_text or "N/A",
        )

        # Define JSON schema for response
        schema = Schema(
            name="LithuanianDeclensionClassification",
            description="Classify Lithuanian noun declension class",
            properties={
                "declension_class": SchemaProperty(
                    "string",
                    "The declension class (1-5)",
                    enum=["1", "2", "3", "4", "5"],
                ),
                "explanation": SchemaProperty(
                    "string", "Brief explanation with ending pattern"
                ),
                "confidence": SchemaProperty(
                    "number", "Confidence score 0.0-1.0", minimum=0.0, maximum=1.0
                ),
            },
        )

        # Query LLM
        try:
            client = self.get_llm_client()
            response = client.generate_chat(prompt=prompt_text, json_schema=schema, context=context)

            if response.structured_data:
                result = response.structured_data
            else:
                logger.error(f"No structured data received for '{lemma.lemma_text}'")
                return None, None, 0.0

            declension_class = result.get("declension_class", None)
            explanation = result.get("explanation", "")
            confidence = float(result.get("confidence", 0.5))

            logger.info(
                f"Generated declension class for '{lemma.lemma_text}' ({target_translation}): "
                f"class {declension_class} (confidence: {confidence:.2f})"
            )

            return declension_class, explanation, confidence

        except Exception as e:
            logger.error(f"Failed to generate declension class for '{lemma.lemma_text}': {e}")
            return None, None, 0.0

    def generate_auxiliary_verb(
        self, lemma: Lemma, target_translation: str, language_code: str, session=None
    ) -> Tuple[Optional[str], Optional[str], float]:
        """
        Generate auxiliary verb classification for compound tenses using LLM.

        Args:
            lemma: The Lemma object
            target_translation: The translation in the target language
            language_code: Target language code (fr, de, it)
            session: Database session (optional)

        Returns:
            Tuple of (auxiliary_verb, explanation, confidence)
        """
        if lemma.pos_type != "verb":
            logger.warning(f"Lemma '{lemma.lemma_text}' is not a verb, skipping auxiliary")
            return None, None, 0.0

        if language_code not in self.AUXILIARY_SYSTEMS:
            logger.error(f"Language '{language_code}' does not have auxiliary verb configuration")
            return None, None, 0.0

        aux_config = self.AUXILIARY_SYSTEMS[language_code]
        language_name = aux_config["name"]
        valid_auxiliaries = ", ".join(aux_config["auxiliaries"])

        # Load prompts
        try:
            context = util.prompt_loader.get_context("wordfreq", "auxiliary_verb")
            prompt_template = util.prompt_loader.get_prompt("wordfreq", "auxiliary_verb")
        except Exception as e:
            logger.error(f"Failed to load auxiliary_verb prompts: {e}")
            return None, None, 0.0

        # Format prompt
        prompt_text = prompt_template.format(
            english_word=lemma.lemma_text,
            target_translation=target_translation,
            pos_type=lemma.pos_type,
            definition=lemma.definition_text or "N/A",
            language_name=language_name,
            language_code=language_code,
            valid_auxiliaries=valid_auxiliaries,
        )

        # Define JSON schema for response
        schema = Schema(
            name="AuxiliaryVerbClassification",
            description=f"Classify auxiliary verb for {language_name} compound tenses",
            properties={
                "auxiliary_verb": SchemaProperty(
                    "string",
                    f"The auxiliary verb: {valid_auxiliaries}",
                    enum=aux_config["auxiliaries"],
                ),
                "explanation": SchemaProperty(
                    "string", "Brief explanation if notable"
                ),
                "confidence": SchemaProperty(
                    "number", "Confidence score 0.0-1.0", minimum=0.0, maximum=1.0
                ),
            },
        )

        # Query LLM
        try:
            client = self.get_llm_client()
            response = client.generate_chat(prompt=prompt_text, json_schema=schema, context=context)

            if response.structured_data:
                result = response.structured_data
            else:
                logger.error(f"No structured data received for '{lemma.lemma_text}'")
                return None, None, 0.0

            auxiliary = result.get("auxiliary_verb", None)
            explanation = result.get("explanation", "")
            confidence = float(result.get("confidence", 0.5))

            logger.info(
                f"Generated auxiliary for '{lemma.lemma_text}' ({target_translation}): "
                f"{auxiliary} (confidence: {confidence:.2f})"
            )

            return auxiliary, explanation, confidence

        except Exception as e:
            logger.error(f"Failed to generate auxiliary for '{lemma.lemma_text}': {e}")
            return None, None, 0.0

    def generate_animacy(
        self, lemma: Lemma, session=None
    ) -> Tuple[Optional[str], Optional[str], float]:
        """
        Generate noun animacy classification using LLM.

        Args:
            lemma: The Lemma object
            session: Database session (optional)

        Returns:
            Tuple of (animacy, explanation, confidence)
        """
        if lemma.pos_type != "noun":
            logger.warning(f"Lemma '{lemma.lemma_text}' is not a noun, skipping animacy")
            return None, None, 0.0

        # Load prompts
        try:
            context = util.prompt_loader.get_context("wordfreq", "animacy")
            prompt_template = util.prompt_loader.get_prompt("wordfreq", "animacy")
        except Exception as e:
            logger.error(f"Failed to load animacy prompts: {e}")
            return None, None, 0.0

        # Format prompt
        prompt_text = prompt_template.format(
            english_word=lemma.lemma_text,
            pos_type=lemma.pos_type,
            definition=lemma.definition_text or "N/A",
        )

        # Define JSON schema for response
        schema = Schema(
            name="NounAnimacyClassification",
            description="Classify noun animacy",
            properties={
                "animacy": SchemaProperty(
                    "string",
                    "The animacy classification",
                    enum=["animate", "inanimate"],
                ),
                "explanation": SchemaProperty(
                    "string", "Brief explanation if notable"
                ),
                "confidence": SchemaProperty(
                    "number", "Confidence score 0.0-1.0", minimum=0.0, maximum=1.0
                ),
            },
        )

        # Query LLM
        try:
            client = self.get_llm_client()
            response = client.generate_chat(prompt=prompt_text, json_schema=schema, context=context)

            if response.structured_data:
                result = response.structured_data
            else:
                logger.error(f"No structured data received for '{lemma.lemma_text}'")
                return None, None, 0.0

            animacy = result.get("animacy", None)
            explanation = result.get("explanation", "")
            confidence = float(result.get("confidence", 0.5))

            logger.info(
                f"Generated animacy for '{lemma.lemma_text}': {animacy} "
                f"(confidence: {confidence:.2f})"
            )

            return animacy, explanation, confidence

        except Exception as e:
            logger.error(f"Failed to generate animacy for '{lemma.lemma_text}': {e}")
            return None, None, 0.0

    def generate_grammar_facts(
        self,
        fact_type: str,
        language_code: str,
        lemmas: Optional[List[Lemma]] = None,
        limit: Optional[int] = None,
        skip_existing: bool = True,
        min_confidence: float = 0.7,
        dry_run: bool = False,
    ) -> Dict[str, any]:
        """
        Generate grammar facts for lemmas.

        Args:
            fact_type: Type of grammar fact to generate (e.g., 'measure_words')
            language_code: Language code (e.g., 'zh', 'fr')
            lemmas: List of lemmas to process (if None, returns empty result)
            limit: Maximum number of lemmas to process
            skip_existing: Skip lemmas that already have this fact
            min_confidence: Minimum confidence to save the fact
            dry_run: If True, don't save to database

        Returns:
            Dictionary with generation results
        """
        # Validate fact type
        if fact_type not in self.SUPPORTED_FACT_TYPES:
            raise ValueError(
                f"Unsupported fact type: {fact_type}. "
                f"Supported types: {', '.join(self.SUPPORTED_FACT_TYPES.keys())}"
            )

        fact_config = self.SUPPORTED_FACT_TYPES[fact_type]

        # Validate language
        if language_code not in fact_config["languages"]:
            raise ValueError(
                f"Fact type '{fact_type}' does not support language '{language_code}'. "
                f"Supported languages: {', '.join(fact_config['languages'])}"
            )

        logger.info(f"Generating {fact_type} for language {language_code}...")
        if dry_run:
            logger.info("DRY RUN MODE - No changes will be saved")

        # If no lemmas provided, return empty result
        if not lemmas:
            return {
                "fact_type": fact_type,
                "language_code": language_code,
                "processed": 0,
                "success": 0,
                "failed": 0,
                "skipped": 0,
                "results": [],
                "dry_run": dry_run,
            }

        session = self.get_session()
        try:
            # Filter lemmas by required POS types for this fact type
            required_pos = fact_config["required_pos"]
            lemmas = [l for l in lemmas if l.pos_type in required_pos]

            logger.info(f"Found {len(lemmas)} candidate lemmas")

            # Process lemmas
            processed_count = 0
            skipped_count = 0
            success_count = 0
            failed_count = 0
            results = []

            for lemma in lemmas:
                if limit and processed_count >= limit:
                    break

                # Check if fact already exists
                if skip_existing:
                    existing_fact = get_grammar_fact_value(
                        session, lemma.id, language_code, fact_type
                    )
                    if existing_fact is not None:
                        skipped_count += 1
                        continue

                # Get translation for target language
                translation = get_translation(session, lemma, language_code)
                if not translation:
                    logger.debug(
                        f"No {language_code} translation for '{lemma.lemma_text}', skipping"
                    )
                    skipped_count += 1
                    continue

                processed_count += 1
                logger.info(f"Processing {processed_count}/{limit or '∞'}: {lemma.lemma_text}")

                # Generate fact based on type
                if fact_type == "measure_words":
                    fact_value, notes, confidence = self.generate_measure_words(
                        lemma, translation, session
                    )
                elif fact_type == "grammatical_gender":
                    fact_value, notes, confidence = self.generate_grammatical_gender(
                        lemma, translation, language_code, session
                    )
                elif fact_type == "verb_transitivity":
                    # English-based fact, no translation needed
                    fact_value, notes, confidence = self.generate_verb_transitivity(
                        lemma, session
                    )
                elif fact_type == "verb_reflexivity":
                    fact_value, notes, confidence = self.generate_verb_reflexivity(
                        lemma, translation, language_code, session
                    )
                elif fact_type == "countability":
                    # English-based fact, no translation needed
                    fact_value, notes, confidence = self.generate_countability(
                        lemma, session
                    )
                elif fact_type == "declension_class":
                    fact_value, notes, confidence = self.generate_declension_class(
                        lemma, translation, language_code, session
                    )
                elif fact_type == "auxiliary_verb":
                    fact_value, notes, confidence = self.generate_auxiliary_verb(
                        lemma, translation, language_code, session
                    )
                elif fact_type == "animacy":
                    # English-based fact, no translation needed
                    fact_value, notes, confidence = self.generate_animacy(
                        lemma, session
                    )
                else:
                    # Placeholder for future fact types
                    logger.error(f"Fact type {fact_type} not yet implemented")
                    failed_count += 1
                    continue

                if fact_value and confidence >= min_confidence:
                    # Save to database (unless dry run)
                    if not dry_run:
                        add_grammar_fact(
                            session,
                            lemma_id=lemma.id,
                            language_code=language_code,
                            fact_type=fact_type,
                            fact_value=fact_value,
                            notes=notes,
                            verified=False,
                        )
                        session.commit()

                        # Log operation
                        log_operation(
                            session,
                            operation_type="grammar_fact_generated",
                            entity_type="grammar_fact",
                            entity_id=lemma.id,
                            details={
                                "fact_type": fact_type,
                                "language_code": language_code,
                                "fact_value": fact_value,
                                "confidence": confidence,
                                "agent": "lape",
                                "model": self.config.model,
                            },
                        )
                        session.commit()

                    success_count += 1
                    results.append(
                        {
                            "lemma_id": lemma.id,
                            "lemma_text": lemma.lemma_text,
                            "translation": translation,
                            "fact_value": fact_value,
                            "notes": notes,
                            "confidence": confidence,
                        }
                    )
                    logger.info(f"  ✓ Generated: {fact_value} (confidence: {confidence:.2f})")
                else:
                    failed_count += 1
                    logger.warning(
                        f"  ✗ Failed or low confidence: {fact_value} (confidence: {confidence:.2f})"
                    )

            logger.info(
                f"Complete! Processed: {processed_count}, Success: {success_count}, "
                f"Failed: {failed_count}, Skipped: {skipped_count}"
            )

            return {
                "fact_type": fact_type,
                "language_code": language_code,
                "processed": processed_count,
                "success": success_count,
                "failed": failed_count,
                "skipped": skipped_count,
                "results": results,
                "dry_run": dry_run,
            }

        except Exception as e:
            logger.error(f"Error generating grammar facts: {e}")
            if session:
                session.rollback()
            raise
        finally:
            if session:
                session.close()


def get_argument_parser():
    """Return the argument parser for introspection."""
    parser = argparse.ArgumentParser(
        description="Lape - Grammar Facts Generator Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate Chinese measure words for nouns
  python lape.py --fact-type measure_words --languages zh --limit 10

  # Generate French grammatical gender for nouns
  python lape.py --fact-type grammatical_gender --languages fr --limit 10

  # Generate verb transitivity (English-based, applies to all languages)
  python lape.py --fact-type verb_transitivity --languages en --limit 10

  # Generate French auxiliary verb classification (avoir/être)
  python lape.py --fact-type auxiliary_verb --languages fr --limit 10

  # Generate Lithuanian declension classes
  python lape.py --fact-type declension_class --languages lt --limit 10

  # Generate for a single lemma by GUID
  python lape.py --fact-type grammatical_gender --languages fr --guid N14_001

  # Dry run to see what would be generated
  python lape.py --fact-type grammatical_gender --languages fr --limit 5 --dry-run

  # Use grouped tasks to process multiple fact types
  python lape.py --task all --languages fr es --limit 10
  python lape.py --task nouns --languages lt en --limit 10
  python lape.py --task verbs --languages fr en --limit 10

Supported fact types:

  Noun facts:
    - measure_words: Chinese measure words/classifiers (languages: zh)
    - grammatical_gender: Noun gender (languages: fr, lt, es, de, pt, ru, it)
    - countability: Countable/uncountable/both (languages: en - base concept)
    - declension_class: Declension class 1-5 (languages: lt)
    - animacy: Animate/inanimate (languages: en - base concept)

  Verb facts:
    - verb_transitivity: Transitive/intransitive/ditransitive/ambitransitive (languages: en - base concept)
    - verb_reflexivity: Inherently/optionally/non-reflexive (languages: fr, es, de, lt, it)
    - auxiliary_verb: Compound tense auxiliary (languages: fr, de, it)

  Note: number_type (plurale_tantum/singulare_tantum) is auto-detected during form generation by Vilkas.

Task presets:
  - all: All fact types
  - gender: grammatical_gender only
  - measure-words: measure_words only
  - nouns: grammatical_gender, countability, animacy, declension_class
  - verbs: verb_transitivity, verb_reflexivity, auxiliary_verb
        """,
    )

    # Common arguments
    add_common_args(parser)
    add_llm_args(parser, default_model="gpt-5-mini")
    add_backend_args(parser)
    add_language_args(parser, multiple=True)

    # Lape-specific arguments
    add_guid_arg(parser, help_text="Process only the lemma with this GUID")
    task_group = parser.add_mutually_exclusive_group(required=True)
    task_group.add_argument(
        "--fact-type",
        choices=LapeAgent.SUPPORTED_FACT_TYPES.keys(),
        help="Type of grammar fact to generate",
    )
    task_group.add_argument(
        "--task",
        choices=LapeAgent.TASK_PRESETS.keys(),
        help="Run a grouped task preset that maps to multiple fact types",
    )
    parser.add_argument("--limit", type=int, help="Maximum number of lemmas to process")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip lemmas that already have this fact (default: True)",
    )
    parser.add_argument(
        "--no-skip-existing",
        dest="skip_existing",
        action="store_false",
        help="Process all lemmas, even if they have existing facts",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.7,
        help="Minimum confidence score to save fact (default: 0.7)",
    )

    # Workqueue arguments
    parser.add_argument(
        "--use-workqueue",
        action="store_true",
        default=False,
        help="Use work queue for batch processing instead of immediate processing",
    )
    parser.add_argument(
        "--workqueue-mode",
        choices=["enqueue", "process", "immediate"],
        default="immediate",
        help=(
            "Work queue mode: "
            "'enqueue' to add work items to queue, "
            "'process' to process queued items, "
            "'immediate' to process directly (default)"
        ),
    )
    parser.add_argument(
        "--workqueue-limit",
        type=int,
        help="Maximum number of work items to process from queue (only applies to 'process' mode)",
    )

    return parser


def enqueue_grammar_fact_work(agent, session, lemmas, fact_types_by_language, dry_run=False):
    """Enqueue grammar fact generation work items to the queue.

    Args:
        agent: LapeAgent instance
        session: Database session
        lemmas: List of lemmas to process
        fact_types_by_language: Dict mapping language_code to list of fact_types
        dry_run: If True, don't actually enqueue

    Returns:
        Dictionary with enqueue statistics
    """
    enqueued_count = 0
    skipped_count = 0

    logger.info(f"Enqueuing work for {len(lemmas)} lemmas...")
    if dry_run:
        logger.info("DRY RUN MODE - No work items will be enqueued")

    for language_code, fact_types in fact_types_by_language.items():
        for fact_type in fact_types:
            fact_config = LapeAgent.SUPPORTED_FACT_TYPES[fact_type]
            required_pos = fact_config["required_pos"]

            for lemma in lemmas:
                # Skip if wrong POS type
                if lemma.pos_type not in required_pos:
                    skipped_count += 1
                    continue

                # Enqueue work item using barsukas task queue
                if not dry_run:
                    dedup_key = f"lape_{fact_type}_{lemma.id}_{language_code}"
                    result = enqueue_task(
                        session,
                        task_type="lape_generate_grammar_fact",
                        target_type="lemma",
                        target_id=lemma.id,
                        payload={
                            "fact_type": fact_type,
                            "language_code": language_code,
                            "lemma_guid": lemma.guid,
                            "lemma_text": lemma.lemma_text,
                        },
                        dedup_key=dedup_key,
                    )
                    if result.created:
                        enqueued_count += 1
                    else:
                        skipped_count += 1
                        logger.debug(f"Skipped duplicate: {lemma.lemma_text} ({fact_type}, {language_code})")
                else:
                    enqueued_count += 1

    if not dry_run:
        session.commit()

    return {
        "enqueued": enqueued_count,
        "skipped": skipped_count,
        "dry_run": dry_run,
    }


def get_lape_queue_stats(session):
    """Get statistics for lape tasks in the queue."""
    from wordfreq.storage.models.schema import BarsukasTask

    task_type = "lape_generate_grammar_fact"
    return {
        "pending": session.query(BarsukasTask).filter(
            BarsukasTask.task_type == task_type,
            BarsukasTask.status == TaskStatus.PENDING
        ).count(),
        "running": session.query(BarsukasTask).filter(
            BarsukasTask.task_type == task_type,
            BarsukasTask.status == TaskStatus.RUNNING
        ).count(),
        "completed": session.query(BarsukasTask).filter(
            BarsukasTask.task_type == task_type,
            BarsukasTask.status == TaskStatus.COMPLETED
        ).count(),
        "failed": session.query(BarsukasTask).filter(
            BarsukasTask.task_type == task_type,
            BarsukasTask.status == TaskStatus.FAILED
        ).count(),
    }


def process_grammar_fact_work_queue(agent, session, limit=None, dry_run=False):
    """Process grammar fact work items from the queue.

    Args:
        agent: LapeAgent instance
        session: Database session
        limit: Maximum number of work items to process
        dry_run: If True, don't actually process

    Returns:
        Dictionary with processing statistics
    """
    from wordfreq.storage.models.schema import BarsukasTask, Lemma

    processed_count = 0
    success_count = 0
    failed_count = 0
    results = []

    logger.info("Processing work items from queue...")
    if dry_run:
        logger.info("DRY RUN MODE - No work will be processed")

    # Get statistics
    stats = get_lape_queue_stats(session)
    logger.info(f"Queue stats: {stats['pending']} pending, {stats['running']} running, "
                f"{stats['completed']} completed, {stats['failed']} failed")

    if stats['pending'] == 0:
        logger.info("No pending work items in queue")
        return {
            "processed": 0,
            "success": 0,
            "failed": 0,
            "results": [],
            "dry_run": dry_run,
        }

    while True:
        if limit and processed_count >= limit:
            logger.info(f"Reached limit of {limit} work items")
            break

        # Claim next lape task
        task = claim_next_task(session)
        if not task or task.task_type != "lape_generate_grammar_fact":
            # Put it back if it's not ours
            if task and task.task_type != "lape_generate_grammar_fact":
                task.status = TaskStatus.PENDING
                task.started_at = None
                session.commit()
            logger.info("No more lape work items in queue")
            break

        processed_count += 1

        # Extract payload
        payload = json.loads(task.payload) if task.payload else {}
        fact_type = payload.get("fact_type")
        language_code = payload.get("language_code")
        lemma_guid = payload.get("lemma_guid", "unknown")

        logger.info(f"[{processed_count}/{limit or '∞'}] Processing task {task.id}: "
                   f"lemma_id={task.target_id}, fact_type={fact_type}, language={language_code}")

        if dry_run:
            mark_task_complete(session, task, "Dry run - not processed")
            session.commit()
            continue

        try:
            # Get lemma
            lemma = session.query(Lemma).filter(Lemma.id == task.target_id).first()
            if not lemma:
                logger.error(f"Lemma {task.target_id} not found")
                mark_task_failed(session, task, "Lemma not found")
                session.commit()
                failed_count += 1
                continue

            if not fact_type:
                logger.error(f"No fact_type in payload for task {task.id}")
                mark_task_failed(session, task, "No fact_type in payload")
                session.commit()
                failed_count += 1
                continue

            # Check if fact already exists
            existing_fact = get_grammar_fact_value(session, lemma.id, language_code, fact_type)
            if existing_fact is not None:
                logger.info(f"Fact already exists for {lemma.lemma_text}, skipping")
                mark_task_complete(session, task, "Fact already exists")
                session.commit()
                continue

            # Get translation if needed
            translation = None
            if fact_type not in ["verb_transitivity", "countability", "animacy"]:
                translation = get_translation(session, lemma, language_code)
                if not translation:
                    logger.warning(f"No {language_code} translation for '{lemma.lemma_text}', skipping")
                    mark_task_complete(session, task, "No translation available")
                    session.commit()
                    continue

            # Generate fact based on type
            fact_value, notes, confidence = None, None, 0.0
            if fact_type == "measure_words":
                fact_value, notes, confidence = agent.generate_measure_words(lemma, translation, session)
            elif fact_type == "grammatical_gender":
                fact_value, notes, confidence = agent.generate_grammatical_gender(
                    lemma, translation, language_code, session
                )
            elif fact_type == "verb_transitivity":
                fact_value, notes, confidence = agent.generate_verb_transitivity(lemma, session)
            elif fact_type == "verb_reflexivity":
                fact_value, notes, confidence = agent.generate_verb_reflexivity(
                    lemma, translation, language_code, session
                )
            elif fact_type == "countability":
                fact_value, notes, confidence = agent.generate_countability(lemma, session)
            elif fact_type == "declension_class":
                fact_value, notes, confidence = agent.generate_declension_class(
                    lemma, translation, language_code, session
                )
            elif fact_type == "auxiliary_verb":
                fact_value, notes, confidence = agent.generate_auxiliary_verb(
                    lemma, translation, language_code, session
                )
            elif fact_type == "animacy":
                fact_value, notes, confidence = agent.generate_animacy(lemma, session)
            else:
                logger.error(f"Unsupported fact type: {fact_type}")
                mark_task_failed(session, task, f"Unsupported fact type: {fact_type}")
                session.commit()
                failed_count += 1
                continue

            # Save result
            min_confidence = 0.7
            if fact_value and confidence >= min_confidence:
                add_grammar_fact(
                    session,
                    lemma_id=lemma.id,
                    language_code=language_code,
                    fact_type=fact_type,
                    fact_value=fact_value,
                    notes=notes,
                    verified=False,
                )
                log_operation(
                    session,
                    operation_type="grammar_fact_generated",
                    entity_type="grammar_fact",
                    entity_id=lemma.id,
                    details={
                        "fact_type": fact_type,
                        "language_code": language_code,
                        "fact_value": fact_value,
                        "confidence": confidence,
                        "agent": "lape",
                        "model": agent.config.model,
                        "via_workqueue": True,
                    },
                )
                mark_task_complete(
                    session, task,
                    f"Generated {fact_type}={fact_value} (confidence: {confidence:.2f})"
                )
                session.commit()
                success_count += 1
                logger.info(f"  ✓ Generated: {fact_value} (confidence: {confidence:.2f})")
            else:
                mark_task_failed(
                    session, task,
                    f"Low confidence or no value (confidence: {confidence:.2f})"
                )
                session.commit()
                failed_count += 1
                logger.warning(f"  ✗ Failed or low confidence: {fact_value} (confidence: {confidence:.2f})")

        except Exception as e:
            logger.error(f"Error processing task {task.id}: {e}")
            mark_task_failed(
                session, task,
                f"Error: {str(e)}",
                error_detail=str(e)
            )
            session.commit()
            failed_count += 1

    return {
        "processed": processed_count,
        "success": success_count,
        "failed": failed_count,
        "results": results,
        "dry_run": dry_run,
    }


def main():
    """Command-line interface for the Lape agent."""
    parser = get_argument_parser()
    args = parser.parse_args()

    # Determine workqueue mode (handle both --use-workqueue flag and --workqueue-mode)
    if args.use_workqueue and args.workqueue_mode == "immediate":
        # User specified --use-workqueue without explicit mode, default to enqueue
        workqueue_mode = "enqueue"
    else:
        workqueue_mode = args.workqueue_mode

    # Create configuration from args
    config = get_data_source_config(args)

    # Create agent
    agent = LapeAgent(config=config)

    # WORKQUEUE MODE: Process work items from queue
    if workqueue_mode == "process":
        logger.info("=" * 80)
        logger.info("LAPE AGENT - PROCESSING WORK QUEUE")
        logger.info("=" * 80)

        session = agent.get_session()
        try:
            results = process_grammar_fact_work_queue(
                agent=agent,
                session=session,
                limit=args.workqueue_limit,
                dry_run=args.dry_run,
            )

            # Print summary
            print("\n" + "=" * 80)
            print("WORK QUEUE PROCESSING SUMMARY")
            print("=" * 80)
            print(f"Processed: {results['processed']}")
            print(f"Success: {results['success']}")
            print(f"Failed: {results['failed']}")
            if results["dry_run"]:
                print("\n⚠️  DRY RUN - No work was actually processed")
            print("=" * 80)

            # Show current queue stats
            stats = get_lape_queue_stats(session)
            print("\nCurrent queue status:")
            print(f"  Pending: {stats['pending']}")
            print(f"  Running: {stats['running']}")
            print(f"  Completed: {stats['completed']}")
            print(f"  Failed: {stats['failed']}")
            print("=" * 80)

        except Exception as e:
            logger.error(f"Failed to process work queue: {e}")
            sys.exit(1)
        finally:
            session.close()

        return

    # For enqueue and immediate modes, we need lemmas and languages
    if not args.languages:
        parser.error("At least one --language/--languages value is required")

    # Normalize language list while preserving order
    languages = list(dict.fromkeys(args.languages))

    explicit_fact_type = args.fact_type is not None

    # Determine which fact types to run (either explicit type or grouped task)
    if explicit_fact_type:
        fact_types_to_run = [args.fact_type]
    else:
        fact_types_to_run = LapeAgent.TASK_PRESETS[args.task]

    # Build fact_types_by_language map
    fact_types_by_language = {}
    for language_code in languages:
        applicable_fact_types = [
            fact_type
            for fact_type in fact_types_to_run
            if language_code in LapeAgent.SUPPORTED_FACT_TYPES[fact_type]["languages"]
        ]

        if explicit_fact_type and not applicable_fact_types:
            parser.error(
                f"Fact type '{args.fact_type}' does not support language '{language_code}'."
            )

        if applicable_fact_types:
            fact_types_by_language[language_code] = applicable_fact_types

    if not fact_types_by_language:
        logger.error("No applicable fact types for the selected languages")
        sys.exit(1)

    # Get lemmas to process (either single lemma from --guid or batch)
    session = agent.get_session()
    try:
        lemmas = get_lemmas_for_agent(session, args)
    finally:
        session.close()

    # Show what we're processing
    if len(lemmas) == 1:
        lemma = lemmas[0]
        logger.info(f"Processing: {lemma.lemma_text} (GUID: {lemma.guid}, POS: {lemma.pos_type})")
    elif len(lemmas) == 0:
        logger.error("No lemmas found to process")
        sys.exit(1)
    else:
        logger.info(f"Processing {len(lemmas)} lemmas")

    # WORKQUEUE MODE: Enqueue work items
    if workqueue_mode == "enqueue":
        logger.info("=" * 80)
        logger.info("LAPE AGENT - ENQUEUING WORK")
        logger.info("=" * 80)

        session = agent.get_session()
        try:
            results = enqueue_grammar_fact_work(
                agent=agent,
                session=session,
                lemmas=lemmas,
                fact_types_by_language=fact_types_by_language,
                dry_run=args.dry_run,
            )

            # Print summary
            print("\n" + "=" * 80)
            print("WORK ENQUEUE SUMMARY")
            print("=" * 80)
            print(f"Enqueued: {results['enqueued']}")
            print(f"Skipped: {results['skipped']}")
            if results["dry_run"]:
                print("\n⚠️  DRY RUN - No work items were actually enqueued")
            print("=" * 80)

            # Show queue stats
            if not args.dry_run:
                stats = get_lape_queue_stats(session)
                print("\nCurrent queue status:")
                print(f"  Pending: {stats['pending']}")
                print(f"  Running: {stats['running']}")
                print(f"  Completed: {stats['completed']}")
                print(f"  Failed: {stats['failed']}")
                print("=" * 80)

        except Exception as e:
            logger.error(f"Failed to enqueue work: {e}")
            sys.exit(1)
        finally:
            session.close()

        return

    # IMMEDIATE MODE: Process directly (default behavior)
    logger.info("=" * 80)
    logger.info("LAPE AGENT - IMMEDIATE PROCESSING")
    logger.info("=" * 80)

    try:
        for language_code, applicable_fact_types in fact_types_by_language.items():
            for fact_type in applicable_fact_types:
                results = agent.generate_grammar_facts(
                    fact_type=fact_type,
                    language_code=language_code,
                    lemmas=lemmas,
                    limit=args.limit,
                    skip_existing=args.skip_existing,
                    min_confidence=args.min_confidence,
                    dry_run=args.dry_run,
                )

                # Print summary
                print("\n" + "=" * 60)
                print("GRAMMAR FACTS GENERATION SUMMARY")
                print("=" * 60)
                print(f"Fact Type: {results['fact_type']}")
                print(f"Language: {results['language_code']}")
                print(f"Processed: {results['processed']}")
                print(f"Success: {results['success']}")
                print(f"Failed: {results['failed']}")
                print(f"Skipped: {results['skipped']}")
                if results["dry_run"]:
                    print("\n⚠️  DRY RUN - No changes saved to database")
                print("=" * 60)

                # Print some examples
                if results["results"]:
                    print("\nSample results:")
                    for i, result in enumerate(results["results"][:5], 1):
                        print(f"{i}. {result['lemma_text']} ({result['translation']})")
                        print(f"   → {result['fact_value']}")
                        print(f"   Confidence: {result['confidence']:.2f}")
                        if result["notes"]:
                            print(f"   Notes: {result['notes']}")

    except Exception as e:
        logger.error(f"Failed to generate grammar facts: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
