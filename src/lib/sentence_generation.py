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
        
        # Debug logging
        logger.debug(f"Verb: {verb_key}, Compatible subjects: {len(compatible_subjects)}, Compatible objects: {len(compatible_objects)}")
        if not compatible_subjects:
            logger.debug(f"No compatible subjects found for verb {verb_key} with data: {verb_data}")
        if not compatible_objects:
            logger.debug(f"No compatible objects found for verb {verb_key} with data: {verb_data}")
        
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
        subject_info = pattern['subject'].get('data', pattern['subject'])
        verb_info = pattern['verb'].get('data', pattern['verb'])
        object_info = pattern['object'].get('data', pattern['object'])
        
        # Get subject, verb, object keys
        subject_key = pattern['subject'].get('key') or pattern['subject'].get('english')
        verb_key = pattern['verb'].get('key') or pattern['verb'].get('english')
        object_key = pattern['object'].get('key') or pattern['object'].get('english')
        
        # Get available adjectives for context
        available_adjectives = [key for key, _ in self._get_available_adjectives()]
        adj_list = ", ".join(available_adjectives[:10])  # Limit for prompt size
        
        prompt = f"""
        Create a natural {target_language} sentence for language learning using these components:
        
        Subject: {subject_key} (Target: {subject_info.get(target_language, 'unknown')})
        Verb: {verb_key} in {pattern['tense']} tense
        Object: {object_key} (Target: {object_info.get(target_language, 'unknown')})
        
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
        # Defensive programming: check pattern structure
        if "subject" not in pattern:
            raise ValueError("Pattern missing 'subject' field")
        if "verb" not in pattern:
            raise ValueError("Pattern missing 'verb' field")
        if "object" not in pattern:
            raise ValueError("Pattern missing 'object' field")
        if "tense" not in pattern:
            raise ValueError("Pattern missing 'tense' field")
            
        # Check nested structure and extract keys
        if not isinstance(pattern["subject"], dict):
            raise ValueError(f"Pattern subject malformed: {pattern['subject']}")
        if not isinstance(pattern["verb"], dict):
            raise ValueError(f"Pattern verb malformed: {pattern['verb']}")
        if not isinstance(pattern["object"], dict):
            raise ValueError(f"Pattern object malformed: {pattern['object']}")
        
        # Handle both 'key' and 'english' field names for backward compatibility
        subject = pattern["subject"].get("key") or pattern["subject"].get("english")
        verb = pattern["verb"].get("key") or pattern["verb"].get("english")
        obj = pattern["object"].get("key") or pattern["object"].get("english")
        
        if not subject:
            raise ValueError(f"Pattern subject missing key/english field: {pattern['subject']}")
        if not verb:
            raise ValueError(f"Pattern verb missing key/english field: {pattern['verb']}")
        if not obj:
            raise ValueError(f"Pattern object missing key/english field: {pattern['object']}")
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
            adj = pattern["adjective"].get("key") or pattern["adjective"].get("english")
            if adj:
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
        
        # Handle both pattern structures: {"key": x, "data": y} and {"english": x, "data": y}
        subject_data = pattern["subject"].get("data", pattern["subject"])
        verb_data = pattern["verb"].get("data", pattern["verb"])
        object_data = pattern["object"].get("data", pattern["object"])
        
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
            adj_data = pattern["adjective"].get("data", pattern["adjective"])
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


class LithuanianSentenceGenerator(SentenceGenerator):
    """
    Lithuanian-specific sentence generator with proper case system and gender handling.
    
    Extends the base SentenceGenerator with Lithuanian morphological rules,
    including accusative case formation, gender agreement, and proper conjugations.
    """
    
    def __init__(self, word_matrices: Dict[str, Dict[str, Dict]], 
                 grammar_rules: Dict[str, Any],
                 llm_client: Optional[UnifiedLLMClient] = None):
        """
        Initialize Lithuanian sentence generator.
        
        Args:
            word_matrices: Dictionary of word categories with their entries
            grammar_rules: Language-specific grammar rules and conjugations
            llm_client: Optional LLM client for enhanced generation
        """
        super().__init__(word_matrices, grammar_rules, llm_client)
        
        # Lithuanian pronouns with full case declensions
        self.lithuanian_pronouns = {
            "I": {"nom": "aš", "acc": "mane", "gen": "manęs", "guid": "PRON_001"},
            "you": {"nom": "tu", "acc": "tave", "gen": "tavęs", "guid": "PRON_002"},
            "he": {"nom": "jis", "acc": "jį", "gen": "jo", "guid": "PRON_003"},
            "she": {"nom": "ji", "acc": "ją", "gen": "jos", "guid": "PRON_004"},
            "we": {"nom": "mes", "acc": "mus", "gen": "mūsų", "guid": "PRON_005"},
            "they": {"nom": "jie", "acc": "juos", "gen": "jų", "guid": "PRON_006"},
        }
        
        # Gender mapping for Lithuanian words (simplified but comprehensive)
        self.word_genders = {
            # Foods - mostly feminine
            "bread": "f", "coffee": "f", "milk": "m", "water": "m", "apple": "m",
            "cheese": "m", "fish": "f", "meat": "f", "soup": "f", "cake": "m",
            "beer": "m", "tea": "f", "juice": "m", "wine": "m", "egg": "m",
            
            # Objects - mixed
            "book": "f", "paper": "m", "pen": "m", "table": "m", "chair": "f",
            "car": "m", "house": "m", "phone": "m", "computer": "m", "bag": "m",
            
            # Animals - based on Lithuanian gender
            "dog": "m", "cat": "f", "horse": "m", "bird": "m", "cow": "f",
            "pig": "f", "rabbit": "m", "mouse": "f",
            
            # Quality adjectives - Lithuanian gender
            "big": "m", "small": "m", "good": "m", "bad": "m", "hot": "m", "cold": "m",
            "new": "m", "long": "m", "short": "m", "high": "m", "low": "m", "dark": "m",
            
            # Numbers - Lithuanian gender (masculine forms)
            "one": "m", "two": "m", "three": "m", "four": "m", 
            "five": "m", "six": "m", "seven": "m", "eight": "m"
        }
        
        # Lithuanian number accusative forms (irregular)
        self.number_accusatives = {
            "vienas": "vieną",
            "du": "du",  # "du" stays the same in accusative
            "trys": "tris",
            "keturi": "keturis",
            "penki": "penkis",
            "šeši": "šešis",
            "septyni": "septynis",
            "aštuoni": "aštuonis"
        }
    
    def get_accusative_form(self, word: str, lithuanian: str) -> str:
        """
        Get accusative form of Lithuanian word with proper morphological rules.
        
        Args:
            word: English word for gender lookup
            lithuanian: Lithuanian nominative form
            
        Returns:
            Lithuanian accusative form
        """
        # Special cases for numbers (irregular accusative forms)
        if lithuanian in self.number_accusatives:
            return self.number_accusatives[lithuanian]
        
        gender = self.word_genders.get(word, "m")
        
        if gender == "m":
            # Masculine declension patterns
            if lithuanian.endswith("as"):
                return lithuanian[:-2] + "ą"
            elif lithuanian.endswith("is") or lithuanian.endswith("ys"):
                return lithuanian[:-2] + "į"
            elif lithuanian.endswith("us"):
                return lithuanian[:-2] + "ų"
            else:
                return lithuanian + "ą"
        else:
            # Feminine declension patterns
            if lithuanian.endswith("a"):
                return lithuanian[:-1] + "ą"
            elif lithuanian.endswith("ė"):
                return lithuanian[:-1] + "ę"
            elif lithuanian.endswith("is"):
                return lithuanian[:-2] + "į"
            else:
                return lithuanian + "ą"
    
    def get_subject_type(self, subject_en: str) -> str:
        """
        Determine subject type for Lithuanian verb conjugation.
        
        Args:
            subject_en: English subject word
            
        Returns:
            Subject type for conjugation lookup
        """
        if subject_en in ["I", "you", "he", "she", "we", "they"]:
            return subject_en
        elif subject_en in self.word_matrices.get("animals", {}):
            return "animal"
        else:
            return "person"
    
    def build_lithuanian_sentence(self, pattern: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build a complete Lithuanian sentence from a pattern with proper grammar.
        
        Args:
            pattern: Sentence pattern with subject, verb, object, tense
            
        Returns:
            Dictionary with English and Lithuanian sentences plus word tracking
        """
        subject_en = pattern["subject"]["english"]
        verb_en = pattern["verb"]["english"]
        obj_en = pattern["object"]["english"]
        tense = pattern["tense"]
        
        # Build English sentence first
        english_sentence = self._build_english_sentence(pattern)
        
        # Build Lithuanian sentence
        subject_type = self.get_subject_type(subject_en)
        
        # Get Lithuanian forms
        if subject_en in self.lithuanian_pronouns:
            subject_lt = self.lithuanian_pronouns[subject_en]["nom"]
        else:
            subject_lt = pattern["subject"]["data"]["lithuanian"]
        
        verb_lt = pattern["verb"]["data"][tense][subject_type]
        obj_lt_nom = pattern["object"]["data"]["lithuanian"]
        obj_lt_acc = self.get_accusative_form(obj_en, obj_lt_nom)
        
        lt_parts = []
        lt_parts.append(subject_lt.capitalize())
        lt_parts.append(verb_lt)
        
        # Handle adjectives with proper case agreement
        if "adjective" in pattern:
            adj_lt = pattern["adjective"]["data"]["lithuanian"]
            adj_acc = self.get_accusative_form(pattern["adjective"]["english"], adj_lt)
            lt_parts.append(adj_acc)
        
        lt_parts.append(obj_lt_acc)
        
        lithuanian_sentence = " ".join(lt_parts) + "."
        
        # Track words used with GUIDs
        words_used = []
        
        words_used.extend([
            {
                "english": subject_en, 
                "lithuanian": subject_lt, 
                "type": "subject", 
                "guid": pattern["subject"]["data"].get("guid", "")
            },
            {
                "english": verb_en, 
                "lithuanian": pattern["verb"]["data"]["infinitive"], 
                "type": "verb"
            },
        ])
        
        if "adjective" in pattern:
            words_used.append({
                "english": pattern["adjective"]["english"],
                "lithuanian": pattern["adjective"]["data"]["lithuanian"],
                "type": "adjective",
                "guid": pattern["adjective"]["data"]["guid"]
            })
        
        words_used.append({
            "english": obj_en,
            "lithuanian": obj_lt_nom,
            "type": "object",
            "guid": pattern["object"]["data"]["guid"]
        })
        
        return {
            "english": english_sentence,
            "lithuanian": lithuanian_sentence,
            "words_used": words_used,
            "pattern": "SVAO" if "adjective" in pattern else "SVO",
            "tense": tense
        }
    

    def _build_target_language_sentence(self, pattern: Dict[str, Any], lang_code: str) -> str:
        """
        Override to use Lithuanian-specific sentence building for 'lt' language code.
        
        Args:
            pattern: Sentence pattern
            lang_code: Target language code
            
        Returns:
            Sentence in target language
        """
        if lang_code == "lt":
            # Use Lithuanian-specific sentence building
            result = self.build_lithuanian_sentence(pattern)
            return result["lithuanian"]
        else:
            # Fall back to parent implementation for other languages
            return super()._build_target_language_sentence(pattern, lang_code)