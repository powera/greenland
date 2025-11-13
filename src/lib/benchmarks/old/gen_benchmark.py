#!/usr/bin/python3

"""Generates benchmark questions and loads them into the database."""

import json
import os
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session

from clients import ollama_client
import benchmarks.datastore.benchmarks
import constants
import lib.validation
from lib.benchmarks.base import BenchmarkGenerator
from lib.benchmarks.spell_check import SpellCheckGenerator
from lib.benchmarks.definitions import DefinitionsGenerator
from lib.benchmarks.translation import TranslationGenerator

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
        session = datastore.benchmarks.create_dev_session()

    filename = "benchmarks/0030_analyze_paragraph/bigbench_understanding_fables.jsonl"
    with open(filename) as f:
        for idx, line in enumerate(f):
            if idx % 7 != 2:
                continue

            sentence = json.loads(line)
            if sentence["query"].endswith("\nAnswer: "):
                sentence["query"] = sentence["query"][:-9]

            datastore.benchmarks.insert_question(
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
        session = datastore.benchmarks.create_dev_session()

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
                    datastore.benchmarks.insert_question(
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
