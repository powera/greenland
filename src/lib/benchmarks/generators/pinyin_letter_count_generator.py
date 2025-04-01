#!/usr/bin/python3

"""Generator for the Pinyin Letter Count benchmark."""

import json
import random
import logging
from typing import Dict, List, Optional, Iterator, Any

from pypinyin import pinyin, Style
import jieba

from lib.benchmarks.base import BenchmarkGenerator
from lib.benchmarks.data_models import (
    BenchmarkQuestion, BenchmarkMetadata,
    AnswerType, Difficulty, EvaluationCriteria
)
from lib.benchmarks.factory import generator, register_benchmark_metadata

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Sample Chinese sentences
SAMPLE_SENTENCES = [
    "我喜欢学习中文",
    "北京是中国的首都",
    "今天天气很好",
    "他的哥哥八岁了",
    "我们一起去公园吧",
    "这本书非常有趣",
    "你明天有什么计划",
    "我的猫喜欢睡觉",
    "中国有很长的历史",
    "昨天我去了图书馆"
]

# Define benchmark metadata
BENCHMARK_METADATA = BenchmarkMetadata(
    code="0051_pinyin_letters",
    name="Pinyin Letter Count",
    description="A benchmark to evaluate a model's ability to count how many times a specific letter appears in the Pinyin representation of a Chinese sentence."
)

# Register benchmark metadata
register_benchmark_metadata(BENCHMARK_METADATA)

@generator("0051_pinyin_letters")
class PinyinLetterCountGenerator(BenchmarkGenerator):
    """Generator for Pinyin letter count benchmark questions."""
    
    def __init__(self, metadata: BenchmarkMetadata, session=None):
        """Initialize generator with benchmark metadata."""
        super().__init__(metadata, session)
        
        # Enable generation strategies
        self.can_load_from_file = False
        self.can_generate_locally = True
        self.can_generate_with_llm = True
        
        # Default context for LLM-based generation
        self.context = """
        You are generating Chinese sentences for a benchmark test.
        Generate natural, everyday Chinese sentences that a beginner to intermediate
        Chinese language learner might encounter.
        The sentences should be 4-10 characters long.
        """
    
    def _get_pinyin_representation(self, chinese_text: str) -> str:
        """Convert Chinese text to Pinyin."""
        # Split text into words for better pinyin conversion
        words = jieba.cut(chinese_text)
        
        # Convert to pinyin
        pinyin_list = pinyin(words, style=Style.NORMAL)
        
        # Flatten the list and join with spaces
        pinyin_str = " ".join([p[0] for p in pinyin_list])
        
        return pinyin_str.upper()
    
    def _count_letter_in_pinyin(self, chinese_text: str, letter: str) -> int:
        """Count occurrences of a specific letter in the Pinyin representation."""
        pinyin_str = self._get_pinyin_representation(chinese_text)
        return pinyin_str.count(letter.upper())
    
    def _generate_locally(self, **kwargs) -> Iterator[BenchmarkQuestion]:
        """Generate questions algorithmically."""
        # Use predefined Chinese sentences
        for sentence in SAMPLE_SENTENCES:
            # Get Pinyin representation
            pinyin_repr = self._get_pinyin_representation(sentence)
            
            # Create a set of letters that appear in the Pinyin
            letters_in_pinyin = set(pinyin_repr.upper().replace(" ", ""))
            letters_in_pinyin = [l for l in letters_in_pinyin if l.isalpha()]
            
            if not letters_in_pinyin:
                continue
                
            # Select a random letter to count
            target_letter = random.choice(letters_in_pinyin)
            
            # Count occurrences
            count = pinyin_repr.count(target_letter)
            
            # Create question
            question = BenchmarkQuestion(
                question_text=f"Count how many times the letter '{target_letter}' appears in the Pinyin representation of the following Chinese sentence: {sentence}",
                answer_type=AnswerType.NUMERIC,
                correct_answer=count,
                category="pinyin_letter_count",
                difficulty=Difficulty.MEDIUM,
                tags=["chinese", "pinyin", "letter_count"]
            )
            
            # Add debug info in evaluation criteria
            question.evaluation_criteria = EvaluationCriteria(
                exact_match=True,
                tolerance=0.0  # Exact match required for counting
            )
            
            yield question
    
    def _generate_with_llm(self, **kwargs) -> Iterator[BenchmarkQuestion]:
        """Generate questions using a language model."""
        # Define schema for LLM response
        schema = {
            "type": "object",
            "properties": {
                "chinese_sentences": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "A list of 10 natural Chinese sentences, 4-10 characters long"
                }
            },
            "required": ["chinese_sentences"]
        }
        
        # Prompt for generating Chinese sentences
        prompt = """
        Generate 10 natural, everyday Chinese sentences that a beginner to intermediate
        Chinese language learner might encounter. The sentences should be 4-10 characters long.
        Each sentence should use common vocabulary and be grammatically correct.
        """
        
        try:
            # Generate sentences using LLM
            response = self.get_llm_question(prompt, schema=schema)
            
            if "chinese_sentences" not in response:
                logger.error("LLM response missing 'chinese_sentences' field")
                return
                
            sentences = response["chinese_sentences"]
            
            for sentence in sentences:
                # Skip if sentence is too long or short
                if len(sentence) < 4 or len(sentence) > 15:
                    continue
                    
                # Get Pinyin representation
                pinyin_repr = self._get_pinyin_representation(sentence)
                
                # Create a set of letters that appear in the Pinyin
                letters_in_pinyin = set(pinyin_repr.upper().replace(" ", ""))
                letters_in_pinyin = [l for l in letters_in_pinyin if l.isalpha()]
                
                if not letters_in_pinyin:
                    continue
                    
                # Select a random letter to count
                target_letter = random.choice(letters_in_pinyin)
                
                # Count occurrences
                count = pinyin_repr.count(target_letter)
                
                # Create question
                question = BenchmarkQuestion(
                    question_text=f"Count how many times the letter '{target_letter}' appears in the Pinyin representation of the following Chinese sentence: {sentence}",
                    answer_type=AnswerType.NUMERIC,
                    correct_answer=count,
                    category="pinyin_letter_count",
                    difficulty=Difficulty.MEDIUM,
                    tags=["chinese", "pinyin", "letter_count"]
                )
                
                # Add debug info in evaluation criteria
                question.evaluation_criteria = EvaluationCriteria(
                    exact_match=True,
                    tolerance=0.0  # Exact match required for counting
                )
                
                yield question
                
        except Exception as e:
            logger.error(f"Error generating questions with LLM: {e}")