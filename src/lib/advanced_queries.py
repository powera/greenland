#!/usr/bin/python3

"""Advanced query functions for generating explanations and analyzing text."""

import logging
from enum import Enum
from typing import Tuple, Dict, List

from clients import unified_client
from telemetry import LLMUsage

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemma2:9b"

class ResponseType(Enum):
    """Available response types for different kinds of topics."""
    HISTORICAL = "historical"    # Historical events, contexts, developments
    SCIENTIFIC = "scientific"    # Natural phenomena and scientific concepts
    TECHNICAL = "technical"      # Engineering and technology topics
    BIOGRAPHICAL = "biographical"  # Living or recently deceased people
    ANALYTICAL = "analytical"    # Critical analysis and evaluation
    LITERARY = "literary"        # Plot summaries and narrative descriptions
    CULTURAL = "cultural"        # Broader cultural movements and traditions

def categorize_topic(topic: str, model: str = DEFAULT_MODEL) -> Tuple[Dict, LLMUsage]:
    """Determine appropriate response type for a given topic.
    
    Args:
        topic: The topic to categorize (e.g., "French Revolution", "Jane Eyre")
        model: Model to use for analysis
        
    Returns:
        Tuple containing (categorization_results, usage_metrics)
    """
    context = """You are categorizing topics to determine the most appropriate response type.
Consider these response types and their use cases:

- Historical: Historical events, contexts, and developments (e.g., "the writing and publication history of Jane Eyre")
- Scientific: Natural phenomena, physical processes, biology, chemistry, physics
- Technical: Engineering, technology, programming, systems
- Biographical: Living or recently deceased people
- Analytical: Critical analysis and evaluation (e.g., "analysis of Gothic elements in Jane Eyre")
- Literary: Plot summaries and narrative descriptions (e.g., "what happens in Jane Eyre")
- Cultural: Broader cultural movements and traditions

For literary works, carefully distinguish between:
- Literary response for plot summaries and character descriptions
- Analytical response for thematic analysis and critical interpretation
- Historical response for publication history and historical context
- Cultural response for influence and role in cultural movements

Select the response type that best matches how the topic should be approached."""

    schema = {
        "type": "object",
        "properties": {
            "response_type": {
                "type": "string",
                "enum": ["historical", "scientific", "technical", "biographical", 
                        "analytical", "literary", "cultural"]
            },
            "explanation": {"type": "string"},
            "secondary_aspects": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["historical", "scientific", "technical", "biographical", 
                            "analytical", "literary", "cultural"]
                }
            }
        },
        "required": ["response_type", "explanation", "secondary_aspects"]
    }

    prompt = f"""Analyze this topic and determine the most appropriate response type: {topic}"""
    
    _, response, usage = unified_client.generate_chat(
        prompt=prompt,
        model=model,
        json_schema=schema,
        context=context
    )
    
    return response, usage


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

def generate_biographical_response(subject: str, target_length: int, model: str = DEFAULT_MODEL) -> Tuple[str, LLMUsage]:
    """Generate a biographical explanation of specified length.
    
    Args:
        subject: Person to describe (e.g., "Greta Thunberg")
        target_length: Desired length in words
        model: Model to use for generation
        
    Returns:
        Tuple containing (response_text, usage_metrics)
    """
    _validate_target_length(target_length)
    
    context = f"""You are writing biographical descriptions for an educated general audience. Your response should be:
- Approximately {target_length} words in length
- Lead with the person's most significant contributions or role
- Include key life events and their impact
- Mention current activities or legacy if applicable
- Maintain a neutral, factual tone
- Focus on verified information
Avoid speculation and unsubstantiated claims."""

    prompt = f"""Provide a {target_length}-word biographical description of {subject}."""
    
    response, _, usage = unified_client.generate_chat(
        prompt=prompt,
        model=model,
        context=context
    )
    
    return response.strip(), usage

def generate_technical_response(topic: str, target_length: int, model: str = DEFAULT_MODEL) -> Tuple[str, LLMUsage]:
    """Generate a technical explanation of specified length.
    
    Args:
        topic: Technical topic to explain (e.g., "how containerization works")
        target_length: Desired length in words
        model: Model to use for generation
        
    Returns:
        Tuple containing (response_text, usage_metrics)
    """
    _validate_target_length(target_length)
    
    context = f"""You are explaining technical concepts for an educated general audience. Your response should be:
- Approximately {target_length} words in length
- Begin with a high-level overview
- Break down complex concepts into understandable parts
- Include practical applications or examples
- Use technical terms with clear explanations
- Address both how it works and why it matters
Avoid oversimplification while maintaining clarity."""

    prompt = f"""Provide a {target_length}-word technical explanation of {topic}."""
    
    response, _, usage = unified_client.generate_chat(
        prompt=prompt,
        model=model,
        context=context
    )
    
    return response.strip(), usage

def generate_literary_response(work: str, target_length: int, model: str = DEFAULT_MODEL) -> Tuple[str, LLMUsage]:
    """Generate a literary explanation of specified length.
    
    Args:
        work: Literary work to describe (e.g., "The Great Gatsby")
        target_length: Desired length in words
        model: Model to use for generation
        
    Returns:
        Tuple containing (response_text, usage_metrics)
    """
    _validate_target_length(target_length)
    
    context = f"""You are providing plot summaries and narrative descriptions for an educated general audience. Your response should be:
- Approximately {target_length} words in length
- Begin with a brief introduction of the work
- Present the plot chronologically
- Focus on key events and character developments
- Include major plot points and resolution
- Avoid detailed analysis or interpretation
Maintain narrative flow while being concise."""

    prompt = f"""Provide a {target_length}-word plot summary of {work}."""
    
    response, _, usage = unified_client.generate_chat(
        prompt=prompt,
        model=model,
        context=context
    )
    
    return response.strip(), usage

def generate_cultural_response(topic: str, target_length: int, model: str = DEFAULT_MODEL) -> Tuple[str, LLMUsage]:
    """Generate a cultural explanation of specified length.
    
    Args:
        topic: Cultural topic to explain (e.g., "K-pop's global influence")
        target_length: Desired length in words
        model: Model to use for generation
        
    Returns:
        Tuple containing (response_text, usage_metrics)
    """
    _validate_target_length(target_length)
    
    context = f"""You are explaining cultural phenomena for an educated general audience. Your response should be:
- Approximately {target_length} words in length
- Provide relevant historical context
- Explain cultural significance and impact
- Include key trends and developments
- Address broader societal implications
- Recognize diverse perspectives
Maintain cultural sensitivity while being informative."""

    prompt = f"""Provide a {target_length}-word explanation of this cultural topic: {topic}."""
    
    response, _, usage = unified_client.generate_chat(
        prompt=prompt,
        model=model,
        context=context
    )
    
    return response.strip(), usage

def generate_analytical_response(topic: str, target_length: int, model: str = DEFAULT_MODEL) -> Tuple[str, LLMUsage]:
    """Generate an analytical response of specified length.
    
    Args:
        topic: Topic to analyze (e.g., "symbolism in Animal Farm")
        target_length: Desired length in words
        model: Model to use for generation
        
    Returns:
        Tuple containing (response_text, usage_metrics)
    """
    _validate_target_length(target_length)
    
    context = f"""You are providing critical analysis for an educated general audience. Your response should be:
- Approximately {target_length} words in length
- Present a clear analytical framework
- Support claims with specific evidence
- Consider multiple interpretations where relevant
- Connect to broader themes or patterns
- Develop a cohesive argument
Balance depth of analysis with clarity of expression."""

    prompt = f"""Provide a {target_length}-word analytical response about {topic}."""
    
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
