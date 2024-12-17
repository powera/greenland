#!/usr/bin/python3

"""Generates benchmark questions and loads them into the database."""

import json
import os
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session

from clients import ollama_client
import benchmarks.datastore
from benchmarks.data.wordlist_extended import TRANSLATIONS, TranslationEntry
import constants
import lib.validation

class BenchmarkGenerator:
    """Base class for generating benchmark questions."""
    
    def __init__(self, session: Optional[Session] = None):
        """Initialize generator with optional database session."""
        self.session = session or benchmarks.datastore.create_dev_session()

    def save_question(self, question_id: str, benchmark_name: str, 
                     question_info: Dict[str, Any]) -> None:
        """Save generated question to database."""
        benchmarks.datastore.insert_question(
            self.session,
            question_id,
            benchmark_name,
            json.dumps(question_info)
        )

class SpellCheckGenerator(BenchmarkGenerator):
    """Generator for spell check benchmark questions."""
    
    def __init__(self, session: Optional[Session] = None):
        super().__init__(session)
        self.context = """You are a creative writing assistant. Write a natural-sounding sentence that:
1. Uses the specified word as its subject or object
2. Introduces a spelling error in that word
3. Maintains proper grammar and natural flow aside from the misspelling
4. Is written at roughly an 8th grade reading level"""

    def generate_sentence(self, start_word: str, model: str = "gemma2:9b") -> str:
        """Generate a sentence using start_word but spelled incorrectly."""
        prompt = f"Write a sentence using the word '{start_word}', but spell it incorrectly."
        
        free_response, _, _ = ollama_client.generate_chat(
            prompt=prompt,
            model=model,
            context=self.context
        )
            
        return free_response.strip()

    def generate_batch(self, start_word: str) -> None:
        """Generate 10 sentences for a given word."""
        sentences = []
        for _ in range(10):
            sentence = self.generate_sentence(start_word)
            sentences.append({
                "sentence": sentence,
                "incorrect": "",  # To be filled in by human annotator
                "correct": start_word
            })

        with open(f"benchmarks/0015_spell_check/{start_word}.json", "w") as f:
            json.dump(sentences, f, indent=2)

    def load_to_database(self) -> None:
        """Load generated spell check questions into database."""
        DIR = os.path.join(constants.BENCHMARK_DATA_DIR, "0015_spell_check")
        files = sorted(os.listdir(DIR))

        idx = 0
        for filename in files:
            if not filename.endswith(".json"):
                continue
                
            with open(os.path.join(DIR, filename)) as f:
                sentences = json.load(f)
                for sentence in sentences:
                    self.save_question(
                        f"0015:{sentence['correct']}:{idx}",
                        "0015_spell_check",
                        sentence
                    )
                    idx += 1

class DefinitionsGenerator(BenchmarkGenerator):
    """Generator for definitions benchmark questions."""

    def __init__(self, session: Optional[Session] = None):
        super().__init__(session)
        self.context = """You are a lexicographer writing clear, concise definitions. For each word:
1. Write a single-sentence definition
2. Do not use the word itself in the definition
3. Focus on the most common meaning of the word
4. Use simple, clear language"""
        
        self.schema = {
            "type": "object",
            "properties": {
                "definition": {"type": "string"},
                "explanation": {"type": "string"},
            },
            "required": ["definition"],
        }

    def generate_question(self, model: str = "gemma2:9b") -> Dict:
        """Generate a single definition question."""
        with open("benchmarks/0020_definitions/wordlist.txt") as f:
            words = [line.strip().lower() for line in f]

        choices = random.sample(words, 10)
        correct = choices[0]
        choices.sort()

        prompt = f'Define the word "{correct}"'
        
        _, structured_response, _ = ollama_client.generate_chat(
            prompt=prompt,
            model=model,
            json_schema=self.schema,
            context=self.context
        )
        
        definition = structured_response["definition"]

        question = f'Which word has this definition: {definition}\n\nThe choices are: {", ".join(choices)}'

        return {
            "question": question,
            "definition": definition,
            "correct": correct,
            "choices": choices
        }

    def generate_validated_question(self, model: str = "gemma2:9b", max_attempts: int = 3) -> Dict:
        """Generate a question with validated definition."""
        for attempt in range(max_attempts):
            question = self.generate_question(model)
            validation = lib.validation.validate_definition(
                question["definition"],
                question["correct"]
            )

            if validation.valid:
                return question

            print(f"Attempt {attempt + 1} failed validation:")
            print(json.dumps(vars(validation), indent=2))

        raise ValueError(f"Failed to generate valid definition after {max_attempts} attempts")

    def load_to_database(self) -> None:
        """Load generated definition questions into database."""
        for idx in range(100):
            question = self.generate_validated_question()
            self.save_question(
                f"0020:{question['correct']}:{idx}",
                "0020_definitions",
                question
            )

class SimpleHaystackGenerator(BenchmarkGenerator):
    """Generator for simple haystack benchmark questions."""
    
    def __init__(self, session: Optional[Session] = None):
        super().__init__(session)
        self.context = """You are writing simple, clear sentences that each contain:
1. A specific person or entity (the subject)
2. An action they are performing
3. A location where the action takes place
Use natural language and vary the sentence structure."""
    
    def generate_sentence(self, name: str, action: str, location: str, 
                         model: str = "gemma2:9b") -> str:
        """Generate a simple sentence with given elements."""
        prompt = f"""Create a sentence using:
- Name: {name}
- Action: {action}
- Location: {location}"""

        free_response, _, _ = ollama_client.generate_chat(
            prompt=prompt,
            model=model,
            context=self.context
        )
        
        return free_response.strip()

    def generate_question(self, names: List[str], actions: List[str], 
                         locations: List[str]) -> Dict:
        """Generate a question with 6 simple sentences."""
        count = 6
        selected = {
            'names': random.sample(names, count),
            'actions': random.sample(actions, count),
            'locations': random.sample(locations, count)
        }
        
        sentences = [
            self.generate_sentence(n, a, l)
            for n, a, l in zip(selected['names'], selected['actions'], selected['locations'])
        ]

        return {
            "sentences": sentences,
            "correct": {
                "sentence": sentences[-1],
                "name": selected['names'][-1],
                "action": selected['actions'][-1],
                "location": selected['locations'][-1],
            }
        }

    def load_to_database(self) -> None:
        """Load generated haystack questions into database."""
        def load_list(filename: str) -> List[str]:
            with open(f"benchmarks/0035_simple_haystack/{filename}") as f:
                return [line.strip() for line in f]

        resources = {
            'names': load_list('names.txt'),
            'actions': load_list('actions.txt'),
            'locations': load_list('locations.txt')
        }

        for idx in range(25):
            question = self.generate_question(**resources)
            self.save_question(
                f"0035:haystack:{idx}",
                "0035_simple_haystack",
                question
            )

def load_paragraph_analysis_to_database(session: Optional[Session] = None) -> None:
    """Load paragraph analysis questions from file into database."""
    if not session:
        session = benchmarks.datastore.create_dev_session()

    filename = "benchmarks/0030_analyze_paragraph/bigbench_understanding_fables.jsonl"
    with open(filename) as f:
        for idx, line in enumerate(f):
            if idx % 7 != 2:
                continue

            sentence = json.loads(line)
            if sentence["query"].endswith("\nAnswer: "):
                sentence["query"] = sentence["query"][:-9]

            benchmarks.datastore.insert_question(
                session,
                f"0030:fable:{idx // 7 + 1}",
                "0030_analyze_paragraph",
                json.dumps(sentence)
            )
            
            if idx // 7 + 1 >= 10:
                break

def load_general_knowledge_to_database(session: Optional[Session] = None) -> None:
    """Load general knowledge questions from files into database."""
    if not session:
        session = benchmarks.datastore.create_dev_session()

    DIR = os.path.join(constants.BENCHMARK_DATA_DIR, "0040_general_knowledge")
    files = sorted(os.listdir(DIR))

    idx = 0
    for filename in files:
        if not filename.endswith(".jsonl"):
            continue
            
        with open(os.path.join(DIR, filename)) as f:
            for line in f:
                if idx % 17 == 0:
                    sentence = json.loads(line)
                    benchmarks.datastore.insert_question(
                        session,
                        f"0040:{sentence['category']}:{idx // 17 + 1}",
                        "0040_general_knowledge",
                        json.dumps(sentence)
                    )
                idx += 1
                if idx // 17 + 1 > 100:
                    break
        if idx // 17 + 1 > 100:
            break


class TranslationGenerator(BenchmarkGenerator):
    """Generator for translation benchmark questions."""
    
    def __init__(self, origin_lang: str, target_lang: str, session: Optional[Session] = None):
        """
        Initialize generator with language pair.
        
        Args:
            origin_lang: Source language code (fr, de, ind, sw, ko, kn, zh)
            target_lang: Target language code (en, fr, de, ind, sw, ko, kn, zh)
            session: Optional database session
        """
        super().__init__(session)
        self.origin_lang = origin_lang
        self.target_lang = target_lang
        
        # Validate language codes
        valid_langs = {'en', 'fr', 'de', 'ind', 'sw', 'ko', 'kn', 'zh'}
        if origin_lang not in valid_langs or target_lang not in valid_langs:
            raise ValueError(f"Language codes must be one of: {', '.join(valid_langs)}")
        if origin_lang == target_lang:
            raise ValueError("Origin and target languages must be different")
            
    @property
    def benchmark_codename(self) -> str:
        """Get unique benchmark codename for this language pair."""
        return f"0050_translation_{self.origin_lang}_{self.target_lang}"

    def get_translation(self, entry: TranslationEntry, lang: str) -> str:
        """Get translation for a specific language from entry."""
        return getattr(entry, lang)

    def get_translation_details(self, entry: TranslationEntry, lang: str) -> Optional[str]:
        """Get translation details for a specific language from entry."""
        return getattr(entry, f"{lang}_details", None)

    def generate_question(self, word_entry: TranslationEntry, include_choices: bool = True) -> Dict:
        """Generate a single translation question."""
        # Get translations for origin and target languages
        origin_word = self.get_translation(word_entry, self.origin_lang)
        target_word = self.get_translation(word_entry, self.target_lang)
        
        # Get any special notes about usage
        origin_details = self.get_translation_details(word_entry, self.origin_lang)
        target_details = self.get_translation_details(word_entry, self.target_lang)
        
        # Create list of possible answers for multiple choice
        if include_choices:
            all_translations = [
                self.get_translation(entry, self.target_lang) 
                for entry in TRANSLATIONS 
                if self.get_translation(entry, self.target_lang)
            ]
            incorrect_choices = [t for t in all_translations if t != target_word]
            
            # Select 7 random incorrect choices
            choices = random.sample(incorrect_choices, min(7, len(incorrect_choices)))
            # Add the correct answer
            choices.append(target_word)
            # Shuffle the choices
            random.shuffle(choices)
        else:
            choices = None
        
        question = {
            "word": origin_word,  # Word to translate
            f"{self.target_lang}": target_word,  # Correct translation
            "origin_lang": self.origin_lang,
            "target_lang": self.target_lang
        }
        
        # Add any available usage details
        if origin_details:
            question["origin_details"] = origin_details
        if target_details:
            question["target_details"] = target_details
        if choices:
            question["choices"] = choices
            
        return question

    def load_to_database(self) -> None:
        """Load generated translation questions into database."""
        from sqlalchemy import text
        
        # Filter for entries that have valid translations for both languages
        valid_entries = [
            entry for entry in TRANSLATIONS 
            if self.get_translation(entry, self.origin_lang) and 
               self.get_translation(entry, self.target_lang)
        ]
        
        if not valid_entries:
            raise ValueError(f"No valid translations found for {self.origin_lang} to {self.target_lang}")
        
        for idx, entry in enumerate(valid_entries):
            question = self.generate_question(entry)
            self.save_question(
                f"{self.benchmark_codename}:{idx}",
                self.benchmark_codename,
                question,
            )

        # Add benchmark metadata with unique codename for this language pair
        benchmark_name = f"Translation ({self.origin_lang.upper()} → {self.target_lang.upper()})"
        self.session.execute(text("""
            INSERT INTO benchmark (codename, displayname, description)
            VALUES (
                :codename,
                :displayname,
                :description
            )
            ON CONFLICT DO NOTHING
        """), {
            "codename": self.benchmark_codename,
            "displayname": benchmark_name,
            "description": f"Tests ability to translate {self.origin_lang.upper()} words to {self.target_lang.upper()} with multiple choice validation"
        })
        self.session.commit()
