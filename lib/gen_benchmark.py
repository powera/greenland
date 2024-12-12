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

@dataclass
class ValidationResult:
    """Stores validation results for generated definitions."""
    is_valid: bool
    validation_score: float
    validator_results: List[Dict]
    definition: str
    expected_word: str

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
    
    def generate_sentence(self, start_word: str, model: str = "gemma2:9b") -> str:
        """Generate a sentence using start_word but spelled incorrectly."""
        prompt = f"""Write a sentence using the word {start_word}, but spelling it incorrectly.
Reply with only the single sentence, do not include additional conversation.
The sentence should be at about an 8th grade reading level."""
        
        response, _ = ollama_client.generate_chat(prompt, model)
        return response.strip()

    def generate_batch(self, start_word: str) -> None:
        """Generate 10 sentences for a given word."""
        sentences = []
        for _ in range(10):
            sentence = self.generate_sentence(start_word)
            sentences.append({
                "sentence": sentence,
                "incorrect": "",
                "correct": start_word
            })

        with open(f"benchmarks/0015_spell_check/{start_word}.json", "w") as f:
            json.dump(sentences, f, indent=2)

    def load_to_database(self) -> None:
        """Load generated spell check questions into database."""
        DIR = "benchmarks/0015_spell_check"
        files = sorted(os.listdir(DIR))

        for idx, filename in enumerate(files):
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

class DefinitionsGenerator(BenchmarkGenerator):
    """Generator for definitions benchmark questions."""

    def validate_definition(self, definition: str, expected_word: str,
        validator_models: tuple = ("granite3-dense:8b:Q4_K_M", 
                                   "qwen2.5:7b:Q4_K_M")) -> ValidationResult:
        """Validate that a definition correctly defines the expected word."""
        validation_results = []
        schema = {
            "type": "object",
            "properties": {
                "explanation": {"type": "string"}
                "matches_word": {"type": "boolean"},
                "likely_word": {"type": "string"},
                "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
            },
            "required": ["matches_word", "likely_word"]
        }

        for model in validator_models:
            ollama_model = ":".join(model.split(":")[:-1])
            prompt = f"""Given this definition: "{definition}"

Does this definition accurately describe the word "{expected_word}"?

Respond in JSON format with these fields:
- explanation: brief reason for your decision
- matches_word: boolean indicating if the definition matches the word
- likely_word: what word you think this actually defines
- confidence: 0-100 score of your confidence"""

            response_text, _ = ollama_client.generate_chat(
                prompt,
                ollama_model,
                json_schema=schema,
                structured_json=True
            )

            try:
                result = json.loads(response_text)
                validation_results.append({"validator_model": model, **result})
            except json.JSONDecodeError:
                validation_results.append({
                    "validator_model": model,
                    "matches_word": False,
                    "likely_word": "INVALID_RESPONSE",
                    "confidence": 0,
                    "explanation": "Failed to parse validator response"
                })

        valid_count = sum(1 for r in validation_results if r["matches_word"])
        avg_confidence = sum(r.get("confidence", 0) for r in validation_results) / len(validation_results)

        return ValidationResult(
            is_valid=valid_count >= len(validator_models) / 2,
            validation_score=avg_confidence,
            validator_results=validation_results,
            definition=definition,
            expected_word=expected_word
        )

    def generate_question(self, model: str = "gemma2:9b") -> Dict:
        """Generate a single definition question."""
        with open("benchmarks/0020_definitions/wordlist.txt") as f:
            words = [line.strip().lower() for line in f]

        choices = random.sample(words, 10)
        correct = choices[0]
        choices.sort()

        schema = {
            "type": "object",
            "properties": {
                "definition": {"type": "string"},
                "explanation": {"type": "string"},
            },
            "required": ["definition"],
        }

        prompt = f"""Write a one-sentence definition of the word "{correct}".
Do not use the word "{correct}" in the response; just provide the definition.
Respond in JSON, with the definition in "definition" and an (optional) explanation in "explanation"."""

        response_text, _ = ollama_client.generate_chat(prompt, model, json_schema=schema)
        response = json.loads(response_text)
        definition = response["definition"]

        question = f'Which of the following ten words has this definition: {definition}\n\nJust give the single correct word, do not give a long explanation.\n\nThe choices are: {", ".join(choices)}'
        
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
            validation = self.validate_definition(
                question["definition"],
                question["correct"]
            )
            
            if validation.is_valid:
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
    
    def generate_sentence(self, name: str, action: str, location: str, 
                         model: str = "gemma2:9b") -> str:
        """Generate a simple sentence with given elements."""
        prompt = f"""Write a simple sentence with the following elements:
    - Name: {name}
    - Action: {action}
    - Location: {location}
Only reply with the single sentence, do not include any other text or punctuation."""

        response, _ = ollama_client.generate_chat(prompt, model)
        return response.strip()

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

        for idx in range(10):
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

    DIR = "benchmarks/0040_general_knowledge"
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
