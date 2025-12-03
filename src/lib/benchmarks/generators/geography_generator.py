#!/usr/bin/python3

"""Generator for geography benchmark questions."""

import logging
import random
from typing import Dict, List, Iterator, Optional, Any, Tuple

from lib.benchmarks.base import BenchmarkGenerator, COUNTRIES, CITIES, MOUNTAINS, RIVERS
from lib.benchmarks.data_models import (
    BenchmarkQuestion,
    BenchmarkMetadata,
    AnswerType,
    Difficulty,
    EvaluationCriteria,
)

logger = logging.getLogger(__name__)

# Default model for LLM-based generation
DEFAULT_GENERATION_MODEL = "gpt-4o-mini-2024-07-18"


class GeographyGenerator(BenchmarkGenerator):
    """
    Generator for geography benchmark questions.

    This generator creates multiple-choice questions about geography, including:
    - Country capitals
    - Mountains and their locations
    - Rivers and their locations
    - Cities and their countries
    """

    def __init__(self, metadata: BenchmarkMetadata, session=None, auto_validate: bool = True):
        """
        Initialize generator with benchmark metadata.

        Args:
            metadata: Benchmark metadata
            session: Optional database session
            auto_validate: Whether to automatically validate all generated questions
        """
        super().__init__(metadata, session, auto_validate=auto_validate)

        # Configure generation strategies - only use LLM-based generation
        self.can_load_from_file = False  # No file-based loading
        self.can_generate_locally = False  # No direct local generation
        self.can_generate_with_llm = True  # Generate everything using an LLM

        # Setup context for LLM-based generation
        self.context = """
        You are a geography expert creating accurate multiple-choice questions for a geography benchmark.
        Each question should have one clearly correct answer and three plausible but incorrect alternatives.
        The questions should be unambiguous and factually accurate.
        """

        # Set validation model to use for geography questions
        self.validation_model = "gpt-4o-mini-2024-07-18"

        # Track which types of questions we've used
        self._used_countries = set()
        self._used_cities = set()
        self._used_mountains = set()
        self._used_rivers = set()

    def _generate_with_llm(self, **kwargs) -> Iterator[BenchmarkQuestion]:
        """
        Generate questions using LLM-based methods.

        This method yields questions from each of the specialized generators until their
        respective data sources are exhausted, and then switches to freestyle generation.

        Yields:
            BenchmarkQuestion objects
        """
        # Define categories and their corresponding generators
        category_generators = [
            ("capitals", self._generate_capital_question, len(COUNTRIES)),
            ("mountains", self._generate_mountain_location_question, len(MOUNTAINS)),
            ("rivers", self._generate_river_location_question, len(RIVERS)),
            ("cities", self._generate_city_country_question, len(CITIES)),
        ]

        # First, generate questions using all specialized generators until they're exhausted
        # We'll use round-robin approach but track if each category is exhausted
        exhausted_categories = set()

        while len(exhausted_categories) < len(category_generators):
            for category_name, generator_func, max_items in category_generators:
                # Skip exhausted categories
                if category_name in exhausted_categories:
                    continue

                try:
                    question = generator_func()
                    if question:
                        yield question
                    else:
                        # If we got None, this category might be exhausted
                        exhausted_categories.add(category_name)
                        logger.info(f"Category '{category_name}' appears to be exhausted")
                except Exception as e:
                    logger.error(f"Error generating {category_name} question: {e}")
                    # After an error, don't immediately mark as exhausted, but log it

                # Check if we've used all items in this category
                # (with a buffer since some might fail validation)
                if (
                    category_name == "capitals"
                    and len(self._used_countries) >= len(COUNTRIES) * 0.9
                ):
                    exhausted_categories.add(category_name)
                    logger.info(
                        f"Used most countries ({len(self._used_countries)}/{len(COUNTRIES)}), marking capitals as exhausted"
                    )
                elif (
                    category_name == "mountains"
                    and len(self._used_mountains) >= len(MOUNTAINS) * 0.9
                ):
                    exhausted_categories.add(category_name)
                    logger.info(
                        f"Used most mountains ({len(self._used_mountains)}/{len(MOUNTAINS)}), marking mountains as exhausted"
                    )
                elif category_name == "rivers" and len(self._used_rivers) >= len(RIVERS) * 0.9:
                    exhausted_categories.add(category_name)
                    logger.info(
                        f"Used most rivers ({len(self._used_rivers)}/{len(RIVERS)}), marking rivers as exhausted"
                    )
                elif category_name == "cities" and len(self._used_cities) >= len(CITIES) * 0.9:
                    exhausted_categories.add(category_name)
                    logger.info(
                        f"Used most cities ({len(self._used_cities)}/{len(CITIES)}), marking cities as exhausted"
                    )

        # If we've exhausted all the predefined entries, switch to freestyle generation
        logger.info(
            "All specialized categories exhausted, switching to freestyle geography question generation"
        )
        yield from self._generate_freestyle_questions()

    def _generate_capital_question(self) -> Optional[BenchmarkQuestion]:
        """
        Generate a question about a country's capital using LLM.

        Returns:
            A BenchmarkQuestion or None if generation fails
        """
        # Find countries we haven't used yet
        available_countries = [c for c in COUNTRIES if c not in self._used_countries]

        # If we've used all countries, reset the tracking set
        if len(available_countries) < 4:
            self._used_countries.clear()
            available_countries = COUNTRIES

        # Select countries for this question
        countries = random.sample(available_countries, 4)
        main_country = countries[0]
        self._used_countries.add(main_country)

        # Get capital from LLM
        prompt = f"What is the capital city of {main_country}? Provide just the name of the capital city, nothing else."
        try:
            capital = self.get_llm_question(prompt)

            # Now generate the question
            question_text = f"What is the capital city of {main_country}?"
            choices = [capital]

            # Get plausible alternative capitals for other countries
            for country in countries[1:]:
                alt_prompt = f"What is the capital city of {country}? Provide just the name of the capital city, nothing else."
                alt_capital = self.get_llm_question(alt_prompt)
                choices.append(alt_capital)

            # Shuffle choices
            correct_answer = choices[0]
            random.shuffle(choices)

            return BenchmarkQuestion(
                question_text=question_text,
                answer_type=AnswerType.MULTIPLE_CHOICE,
                correct_answer=correct_answer,
                choices=choices,
                category="Capitals",
                difficulty=Difficulty.MEDIUM,
                tags=["geography", "capitals"],
            )
        except Exception as e:
            logger.error(f"Error generating capital question: {e}")
            return None

    def _generate_mountain_location_question(self) -> Optional[BenchmarkQuestion]:
        """
        Generate a question about which country a mountain is located in using LLM.

        Returns:
            A BenchmarkQuestion or None if generation fails
        """
        # Find mountains we haven't used yet
        available_mountains = [m for m in MOUNTAINS if m not in self._used_mountains]

        # If we've used all mountains, reset the tracking set
        if not available_mountains:
            self._used_mountains.clear()
            available_mountains = MOUNTAINS

        # Select a random mountain
        mountain = random.choice(available_mountains)
        self._used_mountains.add(mountain)

        # Get the country from LLM
        prompt = f"In which country is {mountain} located? Provide just the name of the country, nothing else."
        try:
            country = self.get_llm_question(prompt)

            # Generate question
            question_text = f"In which country is {mountain} located?"

            # Use country as correct answer, and sample others as alternatives
            countries_sample = random.sample([c for c in COUNTRIES if c != country], 3)
            choices = [country] + countries_sample
            random.shuffle(choices)

            return BenchmarkQuestion(
                question_text=question_text,
                answer_type=AnswerType.MULTIPLE_CHOICE,
                correct_answer=country,
                choices=choices,
                category="Mountains",
                difficulty=Difficulty.MEDIUM,
                tags=["geography", "mountains"],
            )
        except Exception as e:
            logger.error(f"Error generating mountain location question: {e}")
            return None

    def _generate_river_location_question(self) -> Optional[BenchmarkQuestion]:
        """
        Generate a question about which continent a river flows through using LLM.

        Returns:
            A BenchmarkQuestion or None if generation fails
        """
        # Find rivers we haven't used yet
        available_rivers = [r for r in RIVERS if r not in self._used_rivers]

        # If we've used all rivers, reset the tracking set
        if not available_rivers:
            self._used_rivers.clear()
            available_rivers = RIVERS

        # Select a random river
        river = random.choice(available_rivers)
        self._used_rivers.add(river)

        # Get the continent from LLM
        prompt = f"On which continent does the {river} River primarily flow? Provide just the name of the continent, nothing else."
        try:
            continent = self.get_llm_question(prompt)

            # Generate question
            question_text = f"On which continent does the {river} River primarily flow?"

            # Continents as choices
            continents = [
                "Africa",
                "Asia",
                "Europe",
                "North America",
                "South America",
                "Australia",
                "Antarctica",
            ]
            if continent not in continents:
                continents.append(continent)

            # Use continent as correct answer, and sample others as alternatives
            choices = [continent] + random.sample([c for c in continents if c != continent], 3)
            random.shuffle(choices)

            return BenchmarkQuestion(
                question_text=question_text,
                answer_type=AnswerType.MULTIPLE_CHOICE,
                correct_answer=continent,
                choices=choices,
                category="Rivers",
                difficulty=Difficulty.MEDIUM,
                tags=["geography", "rivers"],
            )
        except Exception as e:
            logger.error(f"Error generating river location question: {e}")
            return None

    def _generate_city_country_question(self) -> Optional[BenchmarkQuestion]:
        """
        Generate a question about which country a city is located in using LLM.

        Returns:
            A BenchmarkQuestion or None if generation fails
        """
        # Find cities we haven't used yet
        available_cities = [c for c in CITIES if c not in self._used_cities]

        # If we've used all cities, reset the tracking set
        if not available_cities:
            self._used_cities.clear()
            available_cities = CITIES

        # Select a random city
        city = random.choice(available_cities)
        self._used_cities.add(city)

        # Get the country from LLM
        prompt = f"In which country is the city of {city} located? Provide just the name of the country, nothing else."
        try:
            country = self.get_llm_question(prompt)

            # Generate question
            question_text = f"In which country is the city of {city} located?"

            # Use country as correct answer, and sample others as alternatives
            countries_sample = random.sample([c for c in COUNTRIES if c != country], 3)
            choices = [country] + countries_sample
            random.shuffle(choices)

            return BenchmarkQuestion(
                question_text=question_text,
                answer_type=AnswerType.MULTIPLE_CHOICE,
                correct_answer=country,
                choices=choices,
                category="Cities",
                difficulty=Difficulty.MEDIUM,
                tags=["geography", "cities"],
            )
        except Exception as e:
            logger.error(f"Error generating city country question: {e}")
            return None

    def _generate_freestyle_questions(self) -> Iterator[BenchmarkQuestion]:
        """
        Generate completely freestyle geography questions when predefined lists are exhausted.

        This method generates geography questions from a wider variety of categories
        without relying on the predefined data lists.

        Yields:
            BenchmarkQuestion objects
        """
        # Categories for freestyle questions
        categories = [
            "Country Borders",
            "Natural Landmarks",
            "Islands",
            "Oceans and Seas",
            "Deserts",
            "Lakes",
            "Geography Extremes",
            "Political Geography",
        ]

        difficulty_levels = [Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD]

        schema = {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The geography question text"},
                "correct_answer": {"type": "string", "description": "The correct answer"},
                "incorrect_answers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "Three incorrect but plausible answer options",
                },
                "category": {
                    "type": "string",
                    "description": "The category of geography knowledge being tested",
                },
                "difficulty": {
                    "type": "string",
                    "enum": ["easy", "medium", "hard"],
                    "description": "The difficulty level of the question",
                },
            },
            "required": [
                "question",
                "correct_answer",
                "incorrect_answers",
                "category",
                "difficulty",
            ],
        }

        # Generate an ongoing stream of questions
        while True:
            category = random.choice(categories)
            difficulty = random.choice(difficulty_levels)

            prompt = f"""
            Create a geography multiple-choice question about {category}. 
            The difficulty should be {difficulty.value}.
            
            The question should have one clearly correct answer and three incorrect but plausible alternatives.
            Make sure the question is unambiguous and factually accurate.
            All answers should be concise - ideally just a place name or short phrase.
            """

            try:
                response = self.get_llm_question(prompt, schema=schema)

                # Create a BenchmarkQuestion from the response
                choices = [response["correct_answer"]] + response["incorrect_answers"]
                random.shuffle(choices)

                question = BenchmarkQuestion(
                    question_text=response["question"],
                    answer_type=AnswerType.MULTIPLE_CHOICE,
                    correct_answer=response["correct_answer"],
                    choices=choices,
                    category=response["category"],
                    difficulty=Difficulty(response["difficulty"]),
                    tags=["geography", response["category"].lower().replace(" ", "_")],
                )

                yield question

            except Exception as e:
                logger.error(f"Error generating freestyle question: {e}")
                continue
