#!/usr/bin/python3

"""Generator for 0153 book-author matching benchmark."""

import random
from typing import Iterator, List

from benchmarks.lib.utils.base import BenchmarkGenerator
from benchmarks.lib.utils.data_models import (
    AnswerType,
    BenchmarkMetadata,
    BenchmarkQuestion,
    Difficulty,
    EvaluationCriteria,
)


class BookAuthorMatchGenerator(BenchmarkGenerator):
    """Generate book-to-author multiple-choice questions from seed data."""

    def __init__(self, metadata: BenchmarkMetadata, session=None):
        super().__init__(metadata, session)
        self.can_load_from_file = True
        self.can_generate_with_llm = True
        self.strategy_order = ["file"]

    def _load_pairs(self) -> List[dict]:
        data = self.load_json_file("book_author_pairs.json")
        if not isinstance(data, list):
            raise ValueError("book_author_pairs.json must contain a JSON array")
        return data

    def _generate_decoys(self, book: str, author: str, all_authors: List[str]) -> List[str]:
        prompt = (
            f"Create exactly 3 plausible but incorrect authors for the book '{book}'. "
            f"The correct author is '{author}'. Do not include the correct author."
        )
        schema = {
            "type": "object",
            "properties": {
                "decoys": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3}
            },
            "required": ["decoys"],
        }

        try:
            response = self.get_llm_question(prompt=prompt, schema=schema)
            decoys = [d.strip() for d in response["decoys"] if d.strip() and d.strip() != author]
            if len(decoys) >= 3:
                return decoys[:3]
        except Exception:
            pass

        fallback_pool = [a for a in all_authors if a != author]
        return random.sample(fallback_pool, k=min(3, len(fallback_pool)))

    def _generate_from_file(self, **kwargs) -> Iterator[BenchmarkQuestion]:
        pairs = self._load_pairs()
        random.shuffle(pairs)
        all_authors = sorted({item["author"] for item in pairs})

        for item in pairs:
            book = item["book"].strip()
            author = item["author"].strip()
            decoys = self._generate_decoys(book, author, all_authors)
            choices = [author] + decoys
            random.shuffle(choices)

            yield BenchmarkQuestion(
                question_text=f"Who wrote '{book}'?",
                answer_type=AnswerType.MULTIPLE_CHOICE,
                correct_answer=author,
                choices=choices,
                category="literature",
                difficulty=Difficulty(item.get("difficulty", "medium")),
                tags=["knowledge", "books", "authors"],
                evaluation_criteria=EvaluationCriteria(exact_match=True, case_sensitive=False),
            )
