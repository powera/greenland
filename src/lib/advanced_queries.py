#!/usr/bin/python3

"""Advanced query functions for generating explanations and analyzing text."""

import logging
from typing import Tuple

from clients import unified_client
from telemetry import LLMUsage

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemma2:9b"

def generate_historical_response(topic: str, target_length: int, model: str = DEFAULT_MODEL) -> Tuple[str, LLMUsage]:
    """Generate a historical explanation of specified length.
    
    Args:
        topic: Historical topic to explain (e.g. "Battle of Hastings")
        target_length: Desired length in words
        model: Model to use for generation
        
    Returns:
        Tuple containing (response_text, usage_metrics)
    """
    _validate_target_length(target_length)
    
    context = f"""You are explaining historical topics to an educated general audience. Your response should be:
- Approximately {target_length} words in length
- Well-structured with clear chronology
- Include specific dates, key figures, and locations
- Focus on both what happened and why it matters
- Written in an engaging, narrative style
Avoid editorializing or modern political comparisons."""

    prompt = f"""Provide a {target_length}-word explanation of {topic}."""
    
    response, _, usage = unified_client.generate_chat(
        prompt=prompt,
        model=model,
        context=context
    )
    
    return response.strip(), usage

def generate_scientific_response(topic: str, target_length: int, model: str = DEFAULT_MODEL) -> Tuple[str, LLMUsage]:
    """Generate a scientific explanation of specified length.
    
    Args:
        topic: Scientific topic to explain (e.g. "how a lever functions")
        target_length: Desired length in words
        model: Model to use for generation
        
    Returns:
        Tuple containing (response_text, usage_metrics)
    """
    _validate_target_length(target_length)
    
    context = f"""You are explaining scientific concepts to an educated general audience. Your response should be:
- Approximately {target_length} words in length
- Start with fundamental principles
- Use precise scientific terminology with clear explanations
- Include real-world examples and applications
- Build from basic to more complex aspects
Avoid oversimplification while maintaining accessibility."""

    prompt = f"""Provide a {target_length}-word scientific explanation of {topic}."""
    
    response, _, usage = unified_client.generate_chat(
        prompt=prompt,
        model=model,
        context=context
    )
    
    return response.strip(), usage

def analyze_quotes(essay: str, model: str = DEFAULT_MODEL) -> Tuple[str, LLMUsage]:
    """Analyze quotes and cultural references in an essay.
    
    Args:
        essay: Text to analyze
        model: Model to use for analysis
        
    Returns:
        Tuple containing (analysis_text, usage_metrics)
        The analysis text will contain identified quotes and explanations in a readable format
    """
    _validate_input(essay)
    
    context = """You are analyzing text for an academic audience. For each quote or cultural reference, present your findings in this structure:
1. The exact quote or reference with preserved formatting
2. The source or cultural context
3. A 1-3 sentence explanation of its meaning
4. How it functions within the text's broader argument

List findings in order of appearance in the text."""

    prompt = f"""Identify and analyze all direct quotes and cultural references in this text:

{essay}"""
    
    response, _, usage = unified_client.generate_chat(
        prompt=prompt,
        model=model,
        context=context
    )
    
    return response.strip(), usage

def analyze_logic(essay: str, model: str = DEFAULT_MODEL) -> Tuple[str, LLMUsage]:
    """Analyze logical arguments in an essay.
    
    Args:
        essay: Text to analyze
        model: Model to use for analysis
        
    Returns:
        Tuple containing (analysis_text, usage_metrics)
        The analysis text will contain identified arguments and their evaluation in a readable format
    """
    _validate_input(essay)
    
    context = """You are conducting logical analysis for an academic audience. For each major argument, present your analysis in this structure:
1. The main conclusion being argued for
2. Both explicit and implicit premises
3. Evaluation of premise accuracy using available evidence
4. Assessment of the argument's logical validity
5. Identification of any logical fallacies or weaknesses

Focus on argument structure and logical relationships."""

    prompt = f"""Analyze the logical structure and validity of the arguments in this text:

{essay}"""
    
    response, _, usage = unified_client.generate_chat(
        prompt=prompt,
        model=model,
        context=context
    )
    
    return response.strip(), usage

def _validate_input(text: str, min_length: int = 10) -> None:
    """Validate input text meets minimum requirements."""
    if not text or len(text.strip()) < min_length:
        raise ValueError(f"Input text must be at least {min_length} characters long")

def _validate_target_length(length: int, min_length: int = 50, max_length: int = 2000) -> None:
    """Validate target length is within reasonable bounds."""
    if not min_length <= length <= max_length:
        raise ValueError(f"Target length must be between {min_length} and {max_length} words")
