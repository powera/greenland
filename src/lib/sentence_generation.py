#!/usr/bin/python3

"""
Sentence Generation Library

Core functionality for generating multi-word phrases from a matrix of linguistic options
and using LLM to create properly structured sentences in target languages.

This library provides:
1. Pattern-based sentence generation from word matrices
2. LLM-enhanced sentence construction with proper grammar
3. Support for multiple languages with case systems
"""

import json
import logging
import random
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from clients.unified_client import UnifiedLLMClient
from clients.types import Schema, SchemaProperty

logger = logging.getLogger(__name__)

class SentenceGenerator:
    """
    Core sentence generation engine that creates sentences from word matrices.
    
    Supports both pattern-based generation and LLM-enhanced construction
    for languages with complex grammar systems.
    """
    
    def __init__(self, word_matrices: Dict[str, Dict[str, Dict]], 
                 grammar_rules: Dict[str, Any],
                 llm_client: Optional[UnifiedLLMClient] = None):
        """
        Initialize the sentence generator.
        
        Args:
            word_matrices: Dictionary of word categories with their entries
            grammar_rules: Language-specific grammar rules and conjugations
            llm_client: Optional LLM client for enhanced generation
        """
        self.word_matrices = word_matrices
        self.grammar_rules = grammar_rules
        self.llm_client = llm_client
        
    def create_sentence_pattern(self, pattern_type: str = "SVO") -> Optional[Dict[str, Any]]:
        """
        Create a sentence pattern by selecting compatible words from matrices.
        
        Args:
            pattern_type: Type of sentence pattern (SVO, SVAO, etc.)
            
        Returns:
            Dictionary containing the sentence pattern or None if incompatible
        """
        if pattern_type not in ["SVO", "SVAO"]:
            raise ValueError(f"Unsupported pattern type: {pattern_type}")
            
        # Select verb first to determine compatibility constraints
        verbs = self.word_matrices.get("verbs", {})
        if not verbs:
            return None
            
        verb_key = random.choice(list(verbs.keys()))
        verb_data = verbs[verb_key]
        
        # Get compatible subjects and objects based on verb constraints
        compatible_subjects = self._get_compatible_words("subjects", verb_data)
        compatible_objects = self._get_compatible_words("objects", verb_data)
        
        if not compatible_subjects or not compatible_objects:
            return None
            
        subject_key, subject_data = random.choice(compatible_subjects)
        object_key, object_data = random.choice(compatible_objects)
        tense = random.choice(["present", "past", "future"])
        
        pattern = {
            "subject": {"key": subject_key, "data": subject_data},
            "verb": {"key": verb_key, "data": verb_data},
            "object": {"key": object_key, "data": object_data},
            "tense": tense,
            "pattern_type": pattern_type
        }
        
        # Add adjective for SVAO pattern
        if pattern_type == "SVAO":
            adjectives = self._get_available_adjectives()
            if adjectives:
                adj_key, adj_data = random.choice(adjectives)
                pattern["adjective"] = {"key": adj_key, "data": adj_data}
        
        return pattern
        
    def pattern_to_sentences(self, pattern: Dict[str, Any], 
                           target_languages: List[str]) -> Dict[str, str]:
        """
        Convert a sentence pattern to sentences in target languages.
        
        Args:
            pattern: Sentence pattern from create_sentence_pattern
            target_languages: List of language codes (e.g., ['en', 'lt'])
            
        Returns:
            Dictionary mapping language codes to sentences
        """
        sentences = {}
        
        for lang_code in target_languages:
            if lang_code == "en":
                sentences[lang_code] = self._build_english_sentence(pattern)
            else:
                # Use grammar rules for other languages
                sentences[lang_code] = self._build_target_language_sentence(pattern, lang_code)
                
        return sentences
        
    def generate_with_llm(self, pattern: Dict[str, Any], 
                         target_language: str,
                         model: str = "gpt-4o-mini") -> Optional[Dict[str, Any]]:
        """
        Use LLM to generate a properly structured sentence from pattern components.
        
        Args:
            pattern: Sentence pattern with word components
            target_language: Target language code
            model: LLM model to use
            
        Returns:
            Dictionary with generated sentences and metadata, or None if failed
        """
        if not self.llm_client:
            return None
            
        # Build context for LLM
        subject_info = pattern['subject']['data']
        verb_info = pattern['verb']['data']
        object_info = pattern['object']['data']
        
        # Get available adjectives for context
        available_adjectives = [key for key, _ in self._get_available_adjectives()]
        adj_list = ", ".join(available_adjectives[:10])  # Limit for prompt size
        
        prompt = f"""
        Create a natural {target_language} sentence for language learning using these components:
        
        Subject: {pattern['subject']['key']} (Target: {subject_info.get(target_language, 'unknown')})
        Verb: {pattern['verb']['key']} in {pattern['tense']} tense
        Object: {pattern['object']['key']} (Target: {object_info.get(target_language, 'unknown')})
        
        Available adjectives to optionally include: {adj_list}
        
        Requirements:
        1. Create a grammatically correct sentence using proper cases and conjugations
        2. Use the correct verb form for the tense and subject
        3. Optionally include ONE appropriate adjective if it enhances the sentence
        4. Make sure the sentence is logical and natural
        5. Provide both English and target language versions
        
        If the combination doesn't make logical sense, explain why.
        """
        
        # Define response schema
        schema = Schema(
            "SentenceGeneration",
            f"Generated {target_language} sentence with proper grammar",
            {
                "makes_sense": SchemaProperty("boolean", "Whether the sentence combination makes logical sense"),
                "reason": SchemaProperty("string", "Explanation if the sentence doesn't make sense", required=False),
                "english": SchemaProperty("string", "Natural English sentence", required=False),
                "target_sentence": SchemaProperty("string", f"Grammatically correct {target_language} sentence", required=False),
                "adjective_used": SchemaProperty("string", "Adjective that was included, or null", required=False)
            }
        )
        
        try:
            response = self.llm_client.generate_chat(
                prompt=prompt,
                model=model,
                json_schema=schema
            )
            
            result = response.structured_data
            
            if result.get("makes_sense", False):
                return {
                    "english": result.get("english", ""),
                    "target_sentence": result.get("target_sentence", ""),
                    "target_language": target_language,
                    "adjective_used": result.get("adjective_used"),
                    "llm_generated": True,
                    "pattern": pattern
                }
            else:
                logger.debug(f"LLM rejected pattern: {result.get('reason', 'Unknown reason')}")
                return None
                
        except Exception as e:
            logger.debug(f"LLM generation failed: {e}")
            return None
    
    def _get_compatible_words(self, word_type: str, verb_data: Dict[str, Any]) -> List[Tuple[str, Dict]]:
        """Get words compatible with the given verb constraints."""
        compatible_types = verb_data.get(f"compatible_{word_type}", [])
        compatible_words = []
        
        for category in compatible_types:
            if category in self.word_matrices:
                compatible_words.extend(list(self.word_matrices[category].items()))
                
        return compatible_words
        
    def _get_available_adjectives(self) -> List[Tuple[str, Dict]]:
        """Get all available adjectives from word matrices."""
        adjectives = []
        
        # Collect from various adjective categories
        for category in ["colors", "quality", "numbers"]:
            if category in self.word_matrices:
                adjectives.extend(list(self.word_matrices[category].items()))
                
        return adjectives
        
    def _build_english_sentence(self, pattern: Dict[str, Any]) -> str:
        """Build English sentence from pattern."""
        subject = pattern["subject"]["key"]
        verb = pattern["verb"]["key"]
        obj = pattern["object"]["key"]
        tense = pattern["tense"]
        
        # Apply English grammar rules
        verb_form = self._get_english_verb_form(verb, subject, tense)
        
        parts = []
        
        # Handle articles and capitalization
        if self._needs_article(subject):
            parts.append(f"The {subject}")
        else:
            parts.append(subject.capitalize())
            
        parts.append(verb_form)
        
        # Handle adjectives
        if "adjective" in pattern:
            adj = pattern["adjective"]["key"]
            parts.append(adj)
            
        # Handle object articles
        if self._needs_article(obj):
            parts.append(f"the {obj}")
        else:
            parts.append(obj)
            
        return " ".join(parts) + "."
        
    def _build_target_language_sentence(self, pattern: Dict[str, Any], lang_code: str) -> str:
        """Build target language sentence using grammar rules."""
        # This would use the grammar_rules to apply proper conjugations,
        # case endings, etc. for the target language
        
        subject_data = pattern["subject"]["data"]
        verb_data = pattern["verb"]["data"]
        object_data = pattern["object"]["data"]
        
        # Get base forms
        subject_word = subject_data.get(lang_code, subject_data.get("english", ""))
        verb_word = verb_data.get(lang_code, verb_data.get("english", ""))
        object_word = object_data.get(lang_code, object_data.get("english", ""))
        
        # Apply grammar rules (simplified - would need full implementation)
        if lang_code in self.grammar_rules:
            rules = self.grammar_rules[lang_code]
            
            # Apply case system if present
            if "cases" in rules:
                object_word = self._apply_case(object_word, "accusative", rules["cases"])
                
            # Apply verb conjugation
            if "verb_conjugation" in rules:
                verb_word = self._apply_conjugation(verb_word, pattern["tense"], 
                                                  subject_word, rules["verb_conjugation"])
        
        parts = [subject_word.capitalize(), verb_word, object_word]
        
        # Handle adjectives
        if "adjective" in pattern:
            adj_data = pattern["adjective"]["data"]
            adj_word = adj_data.get(lang_code, adj_data.get("english", ""))
            if lang_code in self.grammar_rules and "cases" in self.grammar_rules[lang_code]:
                adj_word = self._apply_case(adj_word, "accusative", 
                                          self.grammar_rules[lang_code]["cases"])
            parts.insert(-1, adj_word)  # Insert before object
            
        return " ".join(parts) + "."
        
    def _get_english_verb_form(self, verb: str, subject: str, tense: str) -> str:
        """Get correct English verb form based on subject and tense."""
        # Simplified English conjugation rules
        if tense == "present":
            if subject.lower() in ["i", "you", "we", "they"]:
                return verb
            else:
                # Third person singular
                if verb.endswith(('s', 'sh', 'ch', 'x', 'z')):
                    return verb + "es"
                elif verb.endswith('y') and verb[-2] not in 'aeiou':
                    return verb[:-1] + "ies"
                else:
                    return verb + "s"
        elif tense == "past":
            # Would need irregular verb handling
            return verb + "ed"
        else:  # future
            return f"will {verb}"
            
    def _needs_article(self, word: str) -> bool:
        """Determine if a word needs 'the' article in English."""
        # Simplified logic - would need more sophisticated rules
        return word.lower() not in ["i", "you", "he", "she", "we", "they"]
        
    def _apply_case(self, word: str, case: str, case_rules: Dict[str, Any]) -> str:
        """Apply case ending to a word."""
        # Simplified case application - would need full morphological rules
        if case in case_rules and "endings" in case_rules[case]:
            endings = case_rules[case]["endings"]
            # Apply appropriate ending based on word characteristics
            return word + endings.get("default", "")
        return word
        
    def _apply_conjugation(self, verb: str, tense: str, subject: str, 
                          conjugation_rules: Dict[str, Any]) -> str:
        """Apply verb conjugation rules."""
        # Simplified conjugation - would need full verb paradigms
        if tense in conjugation_rules:
            tense_rules = conjugation_rules[tense]
            return tense_rules.get(subject, tense_rules.get("default", verb))
        return verb