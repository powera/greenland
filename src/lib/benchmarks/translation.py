#!/usr/bin/python3

"""Translation benchmark implementation."""

import json
import logging
import random
from typing import Dict, Optional, List
from sqlalchemy import text
from sqlalchemy.orm import Session

from clients import unified_client
from clients.ollama_client import OllamaTimeoutError
from lib.benchmarks.base import BenchmarkRunner, BenchmarkResult, BenchmarkGenerator
from benchmarks.data.wordlist_extended import TRANSLATIONS, TranslationEntry

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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

class TranslationBenchmark(BenchmarkRunner):
    """Benchmark for testing language translation abilities."""
    
    def __init__(self, model: str, origin_lang: str, target_lang: str):
        """
        Initialize benchmark runner with model and language pair.
        
        Args:
            model: Name of the model to test
            origin_lang: Source language code (fr, de, ind, sw, ko, kn, zh)
            target_lang: Target language code (en, fr, de, ind, sw, ko, kn, zh)
        """
        super().__init__(model)
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
    
    def run(self) -> None:
        """Execute the translation benchmark."""
        questions = self.load_questions(self.benchmark_codename)
        self.warm_up()
        
        schema = {
            "type": "object",
            "properties": {
                "translation": {"type": "string"}
            },
            "required": ["translation"]
        }
        
        # Set task context
        context = f"""You are helping with a language translation task.
When translating a word from {self.origin_lang.upper()} to {self.target_lang.upper()}:
- Provide the most direct and common translation
- Give only the base form of the word
- Do not include articles unless they are part of the standard translation
- Do not provide explanations or alternative translations"""
        
        results = []
        for question in questions:
            info = json.loads(question["question_info_json"])
            
            prompt = f"""Translate this word: "{info['word']}" """
            if info.get("choices"):
                prompt += f"\nPossible translations: {', '.join(info['choices'])}"

            try:
                response = unified_client.generate_chat(
                    prompt,
                    self.remote_model,
                    json_schema=schema,
                    context=context
                )
                
                try:
                    translated = response.structured_data["translation"].lower().strip()
                    
                    # Get correct answer based on target language
                    correct = info[self.target_lang].lower()
                    
                    # If choices are provided, validate against them
                    if info.get("choices"):
                        is_correct = translated in [c.lower() for c in info["choices"]] and translated == correct
                    else:
                        is_correct = translated == correct
                        
                    debug_info = None if is_correct else {
                        "response": response.structured_data["translation"],
                        "expected": info[self.target_lang]
                    }
                    
                    # Include any relevant usage details in debug info
                    if debug_info and info.get("origin_details"):
                        debug_info["origin_word_details"] = info["origin_details"]
                    if debug_info and info.get("target_details"):
                        debug_info["target_word_details"] = info["target_details"]
                except (json.JSONDecodeError, KeyError):
                    is_correct = False
                    debug_info = response.structured_data

                results.append(BenchmarkResult(
                    question["question_id"],
                    is_correct,
                    int(response.usage.total_msec),
                    json.dumps(debug_info) if debug_info else None
                ))
            except OllamaTimeoutError as e:
                results.append(self.handle_timeout(question["question_id"], e))

        score = sum(r.score for r in results) * 2
        if score > 100: score=100  # 51 questions
        self.save_results(self.benchmark_codename, score, results)
        print(f"Correct: {score}/{len(questions)}")
