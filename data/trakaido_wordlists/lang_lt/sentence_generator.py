#!/usr/bin/python3

"""
Final Sentence Generator for Level 20 Lithuanian Learning

This script generates simple sentences using pattern-based generation
with proper dictionary integration and Lithuanian grammar.
Focus on simple patterns for level 20, saving complex ones for later levels.
"""

import json
import logging
import random
import sys
import os
import time
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

# Configure logging
# To see debug logs for sentence generation rejections, change level to logging.DEBUG
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add the src directory to the path to import LLM clients and sentence generation library
sys.path.append(str(Path(__file__).parent.parent.parent.parent / "src"))

try:
    from clients.unified_client import UnifiedLLMClient
    from clients.types import Schema, SchemaProperty
    from lib.sentence_generation import SentenceGenerator, LithuanianSentenceGenerator

except ImportError:
    raise( ImportError("Required libraries not found. Please ensure you have the LLM client and sentence generation library installed."))

# Import verb conjugations from verbs.py
from verbs import verbs_new

class SimpleSentenceGenerator:
    def __init__(self, debug_http: bool = False):
        self.base_path = Path(__file__).parent
        self.dictionary_path = self.base_path / "generated" / "dictionary"
        self.debug_http = debug_http
        
        # Load dictionaries
        self.animals = self._load_dictionary("animal_dictionary.py")
        self.foods = self._load_dictionary("food_drink_dictionary.py")
        self.buildings = self._load_dictionary("building_structure_dictionary.py")
        self.colors = self._load_dictionary("color_dictionary.py")
        self.objects = self._load_dictionary("small_movable_object_dictionary.py")
        self.humans = self._load_dictionary("human_dictionary.py")
        self.clothing = self._load_dictionary("clothing_accessory_dictionary.py")
        self.body_parts = self._load_dictionary("body_part_dictionary.py")
        self.tools = self._load_dictionary("tool_machine_dictionary.py")
        self.locations = self._load_dictionary("location_dictionary.py")
        
        # Debug log dictionary sizes
        logger.debug(f"Loaded dictionaries: animals={len(self.animals)}, foods={len(self.foods)}, buildings={len(self.buildings)}, colors={len(self.colors)}, objects={len(self.objects)}, humans={len(self.humans)}")
        logger.debug(f"Additional dictionaries: clothing={len(self.clothing)}, body_parts={len(self.body_parts)}, tools={len(self.tools)}, locations={len(self.locations)}")
        
        # Load adjective dictionaries
        self.quality_raw = self._load_dictionary("quality_dictionary.py")
        self.numbers_raw = self._load_dictionary("definite_quantity_dictionary.py")
        
        # Filter quality adjectives for level 20 (basic descriptive adjectives)
        quality_whitelist = ["big", "small", "good", "bad", "hot", "cold", "new", "long", "short", "high", "low", "dark"]
        self.quality = {k: v for k, v in self.quality_raw.items() if k in quality_whitelist}
        
        # Filter numbers 1-8 only
        numbers_whitelist = ["one", "two", "three", "four", "five", "six", "seven", "eight"]
        self.numbers = {k: v for k, v in self.numbers_raw.items() if k in numbers_whitelist}
        
        # Debug log filtered dictionary sizes
        logger.debug(f"Filtered dictionaries: quality={len(self.quality)} (from {len(self.quality_raw)}), numbers={len(self.numbers)} (from {len(self.numbers_raw)})")
        
        # Subjects with cases and GUIDs
        self.pronouns = {
            "I": {"nom": "aš", "acc": "mane", "gen": "manęs", "guid": "PRON_001"},
            "you": {"nom": "tu", "acc": "tave", "gen": "tavęs", "guid": "PRON_002"},
            "he": {"nom": "jis", "acc": "jį", "gen": "jo", "guid": "PRON_003"},
            "she": {"nom": "ji", "acc": "ją", "gen": "jos", "guid": "PRON_004"},
            "we": {"nom": "mes", "acc": "mus", "gen": "mūsų", "guid": "PRON_005"},
            "they": {"nom": "jie", "acc": "juos", "gen": "jų", "guid": "PRON_006"},
        }
        
        # Load verbs from verbs.py or use fallback
        self.verbs = self._load_verbs_from_file()

        # Initialize LLM client if available
        self.llm_client = None
        try:
            self.llm_client = UnifiedLLMClient(debug=self.debug_http)
            if self.debug_http:
                print("HTTP request logging enabled - you will see full JSON responses with 1-second delays.")
        except Exception as e:
            print(f"Warning: Could not initialize LLM client: {e}")
        
        # Initialize sentence generation library if available
        self.sentence_generator = None
        if self.llm_client:
            try:
                # Prepare word matrices for the sentence generation library
                word_matrices = {
                    "verbs": self.verbs,
                    "pronouns": self.pronouns,
                    "animals": self.animals,
                    "foods": self.foods,
                    "objects": self.objects,
                    "humans": self.humans,
                    "colors": self.colors,
                    "quality": self.quality,
                    "numbers": self.numbers,
                    "clothing": self.clothing,
                    "body_parts": self.body_parts,
                    "tools": self.tools,
                    "locations": self.locations
                }
                
                # Prepare Lithuanian grammar rules
                grammar_rules = {
                    "lt": {
                        "cases": {
                            "accusative": {
                                "endings": {"default": "ą"}  # Simplified
                            }
                        },
                        "verb_conjugation": {
                            "present": {"default": ""},
                            "past": {"default": ""},
                            "future": {"default": ""}
                        }
                    }
                }
                
                self.sentence_generator = LithuanianSentenceGenerator(
                    word_matrices=word_matrices,
                    grammar_rules=grammar_rules,
                    llm_client=self.llm_client
                )
                
                # Debug: Check if the sentence generator is using our LLM client
                if self.debug_http:
                    print(f"Debug: Main LLM client debug flag: {self.llm_client.debug}")
                    if hasattr(self.sentence_generator, 'llm_client'):
                        print(f"Debug: Sentence generator LLM client debug flag: {self.sentence_generator.llm_client.debug}")
                        print(f"Debug: Same client instance? {self.sentence_generator.llm_client is self.llm_client}")
                    else:
                        print("Debug: Sentence generator has no llm_client attribute")
                
                logger.debug("Sentence generation library initialized successfully")
            except Exception as e:
                print(f"Warning: Could not initialize sentence generation library: {e}")
                logger.debug(f"Sentence generation library initialization failed: {e}")

    def _load_dictionary(self, filename: str) -> Dict[str, Dict]:
        """Load a dictionary file and extract word entries"""
        file_path = self.dictionary_path / filename
        if not file_path.exists():
            logger.debug(f"Dictionary loading rejected: file {filename} not found at {file_path}")
            print(f"Warning: Dictionary file {filename} not found")
            return {}
        
        words = {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            namespace = {}
            exec(content, namespace)
            
            for name, value in namespace.items():
                if (isinstance(value, dict) and 
                    (name.startswith('N') or name.startswith('A') or name.startswith('D')) and 
                    'english' in value and 
                    'lithuanian' in value):
                    words[value['english']] = value
                    
        except Exception as e:
            logger.debug(f"Dictionary loading rejected: error loading {filename}: {e}")
            print(f"Error loading {filename}: {e}")
            
        logger.debug(f"Dictionary loaded: {filename} contains {len(words)} words")
        return words

    def _load_verbs_from_file(self) -> Dict[str, Dict]:
        """Load verb conjugations from verbs.py"""
        # Define which verbs to use for level 20 and their compatibility
        # ALL THESE VERBS SHOULD BE USED - comprehensive list for Lithuanian learning
        verb_config = {
            # Basic Needs & Daily Life
            "eat": {
                "infinitive": "valgyti",
                "compatible_objects": ["foods"],
                "compatible_subjects": ["pronouns", "humans"]
            },
            "drink": {
                "infinitive": "gerti",
                "compatible_objects": ["drinks"],
                "compatible_subjects": ["pronouns", "humans"]
            },
            "sleep": {
                "infinitive": "miegoti",
                "compatible_objects": [],
                "compatible_subjects": ["pronouns", "humans", "animals"]
            },
            "live": {
                "infinitive": "gyventi",
                "compatible_objects": ["locations"],
                "compatible_subjects": ["pronouns", "humans", "animals"]
            },
            "work": {
                "infinitive": "dirbti",
                "compatible_objects": ["locations"],
                "compatible_subjects": ["pronouns", "humans"]
            },
            "play": {
                "infinitive": "žaisti",
                "compatible_objects": ["objects", "tools"],
                "compatible_subjects": ["pronouns", "humans", "animals"]
            },
            
            # Mental & Emotional
            "like": {
                "infinitive": "mėgti",
                "compatible_objects": ["foods", "objects", "animals", "clothing"],
                "compatible_subjects": ["pronouns", "humans"]
            },
            "know": {
                "infinitive": "žinoti",
                "compatible_objects": ["humans", "locations"],
                "compatible_subjects": ["pronouns", "humans"]
            },
            "want": {
                "infinitive": "norėti",
                "compatible_objects": ["foods", "objects", "clothing", "tools"],
                "compatible_subjects": ["pronouns", "humans"]
            },
            "can": {
                "infinitive": "galėti",
                "compatible_objects": [],
                "compatible_subjects": ["pronouns", "humans"]
            },
            
            # Sensory Perception
            "see": {
                "infinitive": "matyti",
                "compatible_objects": ["foods", "objects", "animals", "clothing", "body_parts", "locations"],
                "compatible_subjects": ["pronouns", "humans", "animals"]
            },
            "speak": {
                "infinitive": "kalbėti",
                "compatible_objects": [],
                "compatible_subjects": ["pronouns", "humans"]
            },
            "listen": {
                "infinitive": "klausyti",
                "compatible_objects": ["humans"],
                "compatible_subjects": ["pronouns", "humans"]
            },
            
            # Actions & Transactions
            "be": {
                "infinitive": "būti",
                "compatible_objects": ["locations"],
                "compatible_subjects": ["pronouns", "humans", "animals", "objects"]
            },
            "have": {
                "infinitive": "turėti",
                "compatible_objects": ["foods", "objects", "clothing", "tools", "body_parts"],
                "compatible_subjects": ["pronouns", "humans", "animals"]
            },
            "buy": {
                "infinitive": "pirkti",
                "compatible_objects": ["foods", "objects", "clothing", "tools"],
                "compatible_subjects": ["pronouns", "humans"]
            },
            "give": {
                "infinitive": "duoti",
                "compatible_objects": ["foods", "objects", "clothing", "tools"],
                "compatible_subjects": ["pronouns", "humans"]
            },
            "take": {
                "infinitive": "imti",
                "compatible_objects": ["foods", "objects", "clothing", "tools"],
                "compatible_subjects": ["pronouns", "humans"]
            },
            "make": {
                "infinitive": "gaminti",
                "compatible_objects": ["foods", "objects", "tools"],
                "compatible_subjects": ["pronouns", "humans"]
            }
        }
        
        verbs = {}
        
        for english_verb, config in verb_config.items():
            infinitive = config["infinitive"]
            
            if infinitive in verbs_new:
                verb_data = verbs_new[infinitive]
                
                # Convert from verbs.py format to sentence generator format
                verbs[english_verb] = {
                    "infinitive": infinitive,
                    "present": self._convert_tense_conjugations(verb_data.get("present_tense", {})),
                    "past": self._convert_tense_conjugations(verb_data.get("past_tense", {})),
                    "future": self._convert_tense_conjugations(verb_data.get("future", {})),
                    "compatible_objects": config["compatible_objects"],
                    "compatible_subjects": config["compatible_subjects"]
                }
            else:
                logger.debug(f"Verb {infinitive} not found in verbs.py, skipping")
        
        logger.debug(f"Loaded {len(verbs)} verbs from verbs.py")
        return verbs
    
    def _convert_tense_conjugations(self, tense_data: Dict[str, Dict]) -> Dict[str, str]:
        """Convert verbs.py tense format to sentence generator format"""
        # Map from verbs.py person codes to sentence generator keys
        person_mapping = {
            "1s": "I",
            "2s": "you", 
            "3s-m": "he",
            "3s-f": "she",
            "1p": "we",
            "3p-m": "they",
            "3p-f": "they"  # Use same as 3p-m for simplicity
        }
        
        conjugations = {}
        
        for person_code, conjugation_data in tense_data.items():
            if person_code in person_mapping:
                key = person_mapping[person_code]
                lithuanian_form = conjugation_data.get("lithuanian", "").replace("aš ", "").replace("tu ", "").replace("jis ", "").replace("ji ", "").replace("mes ", "").replace("jie ", "").replace("jos ", "")
                conjugations[key] = lithuanian_form
        
        # Add animal and person forms (use 3rd person singular)
        if "he" in conjugations:
            conjugations["animal"] = conjugations["he"]
            conjugations["person"] = conjugations["he"]
        
        return conjugations

    def _llm_generate_with_delay(self, *args, **kwargs):
        """Call LLM generate_chat with optional delay for HTTP request logging."""
        if self.debug_http:
            # Add 1-second delay before HTTP request to limit log spam
            time.sleep(1.0)
        return self.llm_client.generate_chat(*args, **kwargs)
    
    def _library_generate_with_delay(self, pattern, language, model):
        """Call sentence library generate_with_llm with optional delay for HTTP request logging."""
        if self.debug_http:
            # Add 1-second delay before HTTP request to limit log spam
            time.sleep(1.0)
        return self.sentence_generator.generate_with_llm(pattern, language, model)

    def _get_accusative_form(self, word: str, lithuanian: str) -> str:
        """Get accusative form of Lithuanian word - delegates to library"""
        if hasattr(self.sentence_generator, 'get_accusative_form'):
            return self.sentence_generator.get_accusative_form(word, lithuanian)
        
        # If library is not available, this method shouldn't be called
        raise RuntimeError("Lithuanian sentence generation library not available")

    def _get_compatible_objects(self, verb: str) -> List[Tuple[str, Dict]]:
        """Get objects compatible with a given verb"""
        compatible_objects = []
        verb_info = self.verbs.get(verb, {})
        compatible_types = verb_info.get("compatible_objects", ["foods", "objects"])
        
        for obj_type in compatible_types:
            if obj_type == "foods":
                compatible_objects.extend(list(self.foods.items()))
            elif obj_type == "drinks":
                drinks = ["water", "coffee", "milk", "beer", "tea", "juice", "wine"]
                for drink in drinks:
                    if drink in self.foods:
                        compatible_objects.append((drink, self.foods[drink]))
            elif obj_type == "objects":
                compatible_objects.extend(list(self.objects.items()))
            elif obj_type == "animals":
                compatible_objects.extend(list(self.animals.items()))
            elif obj_type == "clothing":
                compatible_objects.extend(list(self.clothing.items()))
            elif obj_type == "body_parts":
                compatible_objects.extend(list(self.body_parts.items()))
            elif obj_type == "tools":
                compatible_objects.extend(list(self.tools.items()))
            elif obj_type == "locations":
                compatible_objects.extend(list(self.locations.items()))
        
        return compatible_objects

    def _get_compatible_subjects(self, verb: str) -> List[Tuple[str, Dict]]:
        """Get subjects compatible with a given verb"""
        compatible_subjects = []
        verb_info = self.verbs.get(verb, {})
        compatible_types = verb_info.get("compatible_subjects", ["pronouns", "humans", "animals"])
        
        for subj_type in compatible_types:
            if subj_type == "pronouns":
                for pronoun, data in self.pronouns.items():
                    compatible_subjects.append((pronoun, {"lithuanian": data["nom"], "guid": data["guid"]}))
            elif subj_type == "humans":
                # Use all available humans from the loaded dictionary
                for human_en, human_data in self.humans.items():
                    compatible_subjects.append((human_en, human_data))
            elif subj_type == "animals":
                # Use all available animals from the loaded dictionary
                for animal_en, animal_data in self.animals.items():
                    compatible_subjects.append((animal_en, animal_data))
        
        return compatible_subjects

    def _get_subject_type(self, subject_en: str) -> str:
        """Determine subject type for verb conjugation - delegates to library"""
        if hasattr(self.sentence_generator, 'get_subject_type'):
            return self.sentence_generator.get_subject_type(subject_en)
        
        # If library is not available, this method shouldn't be called
        raise RuntimeError("Lithuanian sentence generation library not available")


    def _create_simple_sentence_pattern(self) -> Optional[Dict[str, Any]]:
        """Create a simple sentence pattern (SVO or SVAO only)"""
        verb = random.choice(list(self.verbs.keys()))
        
        compatible_subjects = self._get_compatible_subjects(verb)
        compatible_objects = self._get_compatible_objects(verb)
        
        if not compatible_subjects or not compatible_objects:
            logger.debug(f"Sentence generation rejected: verb '{verb}' has no compatible subjects ({len(compatible_subjects)}) or objects ({len(compatible_objects)})")
            return None
            
        subject_en, subject_data = random.choice(compatible_subjects)
        obj_en, obj_data = random.choice(compatible_objects)
        tense = random.choice(["present", "past", "future"])
        
        pattern = {
            "subject": {"english": subject_en, "data": subject_data},
            "verb": {"english": verb, "data": self.verbs[verb]},
            "object": {"english": obj_en, "data": obj_data},
            "tense": tense
        }
        
        # Add adjective sometimes (30% chance for level 20)
        if random.random() < 0.3:
            # Choose from colors, quality adjectives, or numbers
            adjective_sources = []
            if self.colors:
                adjective_sources.append(("colors", self.colors))
            if self.quality:
                adjective_sources.append(("quality", self.quality))
            if self.numbers:
                adjective_sources.append(("numbers", self.numbers))
            
            if adjective_sources:
                source_name, source_dict = random.choice(adjective_sources)
                adjective_en = random.choice(list(source_dict.keys()))
                pattern["adjective"] = {
                    "english": adjective_en, 
                    "data": source_dict[adjective_en],
                    "type": source_name
                }
        
        return pattern

    def _pattern_to_sentence(self, pattern: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a pattern to English and Lithuanian sentences"""
        # Try to use the library's Lithuanian sentence builder if available
        if hasattr(self.sentence_generator, 'build_lithuanian_sentence'):
            return self.sentence_generator.build_lithuanian_sentence(pattern)
        
        # If library is not available, this method shouldn't be called
        raise RuntimeError("Lithuanian sentence generation library not available")

    def _generate_sentence_with_llm(self, pattern: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Use LLM to generate a complete sentence from the pattern"""
        # Use our own Lithuanian LLM generation method
        return self.generate_lithuanian_with_llm(pattern)

    def generate_with_sentence_library(self, count: int = 10, model: str = "gpt-5-mini") -> List[Dict[str, Any]]:
        """Generate sentences using the sentence generation library"""
        if not self.sentence_generator:
            print("Sentence generation library not available. Falling back to simple generation.")
            return self.generate_simple_sentences(count=count, use_llm=True)
        
        sentences = []
        attempts = 0
        max_attempts = count * 3
        
        print(f"Generating {count} sentences using sentence generation library...")
        logger.debug(f"Starting library-based sentence generation: target={count}, max_attempts={max_attempts}")
        
        while len(sentences) < count and attempts < max_attempts:
            attempts += 1
            
            # Create pattern using the library
            pattern = self.sentence_generator.create_sentence_pattern("SVO")
            if not pattern:
                logger.debug(f"Library sentence generation attempt {attempts}: Pattern creation failed")
                continue
            
            # Generate sentence using the library's LLM method
            result = self._library_generate_with_delay(pattern, "lt", model)
            if result:
                # Convert library result to our format
                sentence = {
                    "english": result["english"],
                    "lithuanian": result["target_sentence"],
                    "subject": pattern["subject"]["key"],
                    "verb": pattern["verb"]["key"],
                    "object": pattern["object"]["key"],
                    "tense": pattern["tense"],
                    "pattern": pattern["pattern_type"],
                    "llm_generated": True,
                    "library_generated": True
                }
                
                # Build words_used array
                words_used = []
                
                # Add subject
                subject_data = pattern["subject"]["data"]
                words_used.append({
                    "english": pattern["subject"]["key"],
                    "lithuanian": subject_data.get("lithuanian", subject_data.get("nom", "")),
                    "type": "subject",
                    "guid": subject_data.get("guid", "")
                })
                
                # Add verb
                verb_data = pattern["verb"]["data"]
                words_used.append({
                    "english": pattern["verb"]["key"],
                    "lithuanian": verb_data.get("infinitive", verb_data.get("lithuanian", "")),
                    "type": "verb"
                })
                
                # Add adjective if used
                if result.get("adjective_used"):
                    adj_key = result["adjective_used"]
                    if "adjective" in pattern:
                        adj_data = pattern["adjective"]["data"]
                        words_used.append({
                            "english": adj_key,
                            "lithuanian": adj_data.get("lithuanian", ""),
                            "type": "adjective",
                            "guid": adj_data.get("guid", "")
                        })
                        sentence["adjective"] = adj_key
                        sentence["adjective_guid"] = adj_data.get("guid", "")
                
                # Add object
                object_data = pattern["object"]["data"]
                words_used.append({
                    "english": pattern["object"]["key"],
                    "lithuanian": object_data.get("lithuanian", ""),
                    "type": "object",
                    "guid": object_data.get("guid", "")
                })
                
                sentence["words_used"] = words_used
                sentences.append(sentence)
                logger.debug(f"Library sentence generation attempt {attempts}: Successfully generated sentence")
            else:
                logger.debug(f"Library sentence generation attempt {attempts}: Library rejected pattern")
                continue
            
            if len(sentences) % 10 == 0:
                print(f"  Generated {len(sentences)}/{count} sentences...")
        
        print(f"Generated {len(sentences)} sentences in {attempts} attempts using library")
        logger.debug(f"Library sentence generation completed: generated={len(sentences)}, target={count}, attempts={attempts}")
        return sentences

    def generate_simple_sentences(self, count: int = 10, use_llm: bool = False, use_library: bool = False) -> List[Dict[str, Any]]:
        """Generate simple sentences for level 20"""
        # Use sentence generation library if requested and available
        if use_library and self.sentence_generator:
            return self.generate_with_sentence_library(count)
        
        sentences = []
        attempts = 0
        max_attempts = count * 2
        
        print(f"Generating {count} simple sentences for level 20...")
        if use_llm:
            print("Using LLM for quality control...")
        
        logger.debug(f"Starting sentence generation: target={count}, use_llm={use_llm}, max_attempts={max_attempts}")
        
        while len(sentences) < count and attempts < max_attempts:
            attempts += 1
            
            pattern = self._create_simple_sentence_pattern()
            if not pattern:
                logger.debug(f"Sentence generation attempt {attempts}: Pattern creation failed")
                continue
            
            # Generate sentence with LLM or pattern-based approach
            if use_llm:
                # Use LLM to generate the complete sentence
                llm_sentence = self._generate_sentence_with_llm(pattern)
                if llm_sentence:
                    # Add pattern information for reference
                    llm_sentence.update({
                        "subject": pattern["subject"]["english"],
                        "verb": pattern["verb"]["english"],
                        "object": pattern["object"]["english"],
                        "tense": pattern["tense"],
                        "pattern": "SVO"
                    })
                    
                    # Build words_used array with GUIDs for LLM sentences
                    words_used = []
                    
                    # Add subject with GUID
                    subject_lt = pattern["subject"]["data"]["lithuanian"] if pattern["subject"]["english"] not in self.pronouns else self.pronouns[pattern["subject"]["english"]]["nom"]
                    words_used.append({
                        "english": pattern["subject"]["english"],
                        "lithuanian": subject_lt,
                        "type": "subject",
                        "guid": pattern["subject"]["data"].get("guid", "")
                    })
                    
                    # Add verb (no GUID for verbs)
                    words_used.append({
                        "english": pattern["verb"]["english"],
                        "lithuanian": pattern["verb"]["data"]["infinitive"],
                        "type": "verb"
                    })
                    
                    # Add object with GUID
                    words_used.append({
                        "english": pattern["object"]["english"],
                        "lithuanian": pattern["object"]["data"]["lithuanian"],
                        "type": "object",
                        "guid": pattern["object"]["data"].get("guid", "")
                    })
                    
                    llm_sentence["words_used"] = words_used
                    sentence = llm_sentence
                else:
                    # LLM rejected the pattern, skip this attempt
                    logger.debug(f"Sentence generation attempt {attempts}: LLM rejected pattern ({pattern['subject']['english']} {pattern['verb']['english']} {pattern['object']['english']})")
                    if attempts % 50 == 0:
                        print(f"  LLM rejected pattern, trying another...")
                    continue
            else:
                # Use pattern-based generation
                sentence = self._pattern_to_sentence(pattern)
            
            sentences.append(sentence)
            logger.debug(f"Sentence generation attempt {attempts}: Successfully generated sentence ({pattern['subject']['english']} {pattern['verb']['english']} {pattern['object']['english']})")
            
            if len(sentences) % 10 == 0:
                print(f"  Generated {len(sentences)}/{count} sentences...")
        
        print(f"Generated {len(sentences)} sentences in {attempts} attempts")
        logger.debug(f"Sentence generation completed: generated={len(sentences)}, target={count}, attempts={attempts}, success_rate={len(sentences)/attempts*100:.1f}%")
        return sentences

    def generate_lithuanian_with_llm(self, pattern: Dict[str, Any], 
                                     model: str = "gpt-4o-mini") -> Optional[Dict[str, Any]]:
        """
        Use LLM to generate a Lithuanian sentence with proper grammar checking.
        
        Args:
            pattern: Sentence pattern with word components
            model: LLM model to use
            
        Returns:
            Dictionary with generated sentences and metadata, or None if failed
        """
        if not self.llm_client:
            return None
            
        # Get context about the words
        subject_info = pattern['subject']['data'] if 'data' in pattern['subject'] else {}
        verb_info = pattern['verb']
        object_info = pattern['object']['data'] if 'data' in pattern['object'] else {}
        
        prompt = f"""Create a natural Lithuanian sentence for language learning using these components:

Subject: {pattern['subject']['english']} (Lithuanian: {subject_info.get('lithuanian', 'unknown')})
Verb: {pattern['verb']['english']} ({verb_info.get('infinitive', 'unknown')})
Tense: {pattern['tense']}
Object: {pattern['object']['english']} (Lithuanian: {object_info.get('lithuanian', 'unknown')})

Requirements:
1. Create a grammatically correct Lithuanian sentence using proper cases (nominative for subject, accusative for object)
2. Use the correct verb conjugation for the tense and subject
3. Other forms of the verb (such as prefixed or modified forms) are permitted if they are more natural
4. Make sure the sentence is logical and natural
5. Provide both English and Lithuanian versions"""
        
        # Define response schema
        schema = Schema(
            "LithuanianSentenceGeneration",
            "Generated Lithuanian sentence with proper grammar",
            {
                "makes_sense": SchemaProperty("boolean", "Whether the sentence combination makes logical sense"),
                "english": SchemaProperty("string", "Natural English sentence", required=False),
                "lithuanian": SchemaProperty("string", "Grammatically correct Lithuanian sentence", required=False)
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
                    "lithuanian": result.get("lithuanian", ""),
                    "llm_generated": True,
                    "pattern": pattern
                }
            else:
                logger.debug(f"LLM rejected Lithuanian pattern: {result.get('reason', 'Unknown reason')}")
                return None
                
        except Exception as e:
            logger.debug(f"Lithuanian LLM generation failed: {e}")
            return None
    


def load_existing_sentences(file_path):
    """Load existing sentences from a JSON file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        # Return empty structure if file doesn't exist or is invalid
        return {
            "metadata": {
                "level": "level_20",
                "total_sentences": 0,
                "generated_date": "2025-08-01",
                "description": "Simple sentences for Lithuanian learning level 20 - SVO and SVAO patterns only",
                "version": "final",
                "patterns_used": ["SVO", "SVAO"],
                "llm_quality_control": False,
                "sentence_library_used": False,
                "generation_method": "pattern",
                "dictionaries_used": {}
            },
            "sentences": []
        }

def main():
    """Main function that adds 10 sentences to the existing file"""
    print("Simple Lithuanian Sentence Generator for Level 20")
    print("================================================")
    print("Adding 10 new sentences to the existing file...")
    
    # Create generator with default settings
    generator = SimpleSentenceGenerator(debug_http=False)
    
    # Determine if we can use the sentence library
    use_library = generator.sentence_generator is not None
    use_llm = False  # Default to not using LLM for quality control
    
    # Load existing sentences
    output_path = generator.base_path / "level_20_sentences.json"
    existing_data = load_existing_sentences(output_path)
    existing_sentences = existing_data["sentences"]
    
    # Generate 10 new sentences
    new_sentences = generator.generate_simple_sentences(count=10, use_llm=use_llm, use_library=use_library)
    
    # Combine existing and new sentences
    all_sentences = existing_sentences + new_sentences
    
    # Update metadata
    existing_data["metadata"]["total_sentences"] = len(all_sentences)
    existing_data["metadata"]["llm_quality_control"] = use_llm
    existing_data["metadata"]["sentence_library_used"] = use_library
    existing_data["metadata"]["generation_method"] = "library" if use_library else ("llm" if use_llm else "pattern")
    existing_data["metadata"]["dictionaries_used"] = {
        "animals": len(generator.animals),
        "foods": len(generator.foods),
        "buildings": len(generator.buildings),
        "colors": len(generator.colors),
        "objects": len(generator.objects),
        "humans": len(generator.humans)
    }
    
    # Update sentences
    existing_data["sentences"] = all_sentences
    
    # Save to JSON file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)
    
    print(f"\nAdded {len(new_sentences)} new sentences to {output_path}")
    print(f"Total sentences in file: {len(all_sentences)}")
    
    # Print examples of new sentences
    print("\nNew sentences added:")
    for i, sentence in enumerate(new_sentences[:5]):
        print(f"{i+1}. EN: {sentence['english']}")
        print(f"   LT: {sentence['lithuanian']}")
        print(f"   Pattern: {sentence['pattern']}, Tense: {sentence['tense']}")
        if sentence.get('library_generated'):
            print("   (Generated using sentence library)")
        elif sentence.get('llm_generated'):
            print("   (LLM generated)")
        elif sentence.get('llm_improved'):
            print("   (LLM improved)")
        print()

if __name__ == "__main__":
    main()