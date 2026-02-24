#!/usr/bin/python3

"""Generator for 0155 historical event year benchmark."""

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


class HistoricalEventYearGenerator(BenchmarkGenerator):
    """Generate historical event year multiple-choice questions from seed data."""

    def __init__(self, metadata: BenchmarkMetadata, session=None):
        super().__init__(metadata, session)
        self.can_load_from_file = True
        self.can_generate_with_llm = True
        self.strategy_order = ["file"]

    def _load_events(self) -> List[dict]:
        data = self.load_json_file("historical_events.json")
        if not isinstance(data, list):
            raise ValueError("historical_events.json must contain a JSON array")
        return data

    def _generate_year_decoys(self, event: str, year: int) -> List[str]:
        schema = {
            "type": "object",
            "properties": {
                "decoy_years": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 3,
                    "maxItems": 3,
                }
            },
            "required": ["decoy_years"],
        }
        prompt = (
            f"Provide exactly 3 plausible but incorrect years for this event: '{event}'. "
            f"The correct year is {year}. Use integer years only and avoid duplicates."
        )

        try:
            response = self.get_llm_question(prompt=prompt, schema=schema)
            years = [str(y) for y in response["decoy_years"] if int(y) != int(year)]
            if len(set(years)) >= 3:
                return list(dict.fromkeys(years))[:3]
        except Exception:
            pass

        offsets = [-25, -10, -5, 5, 10, 25]
        candidates = [str(year + offset) for offset in offsets if year + offset > 0]
        random.shuffle(candidates)
        return candidates[:3]

    def _generate_from_file(self, **kwargs) -> Iterator[BenchmarkQuestion]:
        events = self._load_events()
        random.shuffle(events)

        for event in events:
            text = event["event"].strip()
            year = int(event["year"])
            answer = str(year)
            choices = [answer] + self._generate_year_decoys(text, year)
            choices = list(dict.fromkeys(choices))
            while len(choices) < 4:
                filler = str(year + random.choice([-50, -20, 20, 50]))
                if filler not in choices and int(filler) > 0:
                    choices.append(filler)
            random.shuffle(choices)

            yield BenchmarkQuestion(
                question_text=f"In what year did this event occur: {text}?",
                answer_type=AnswerType.MULTIPLE_CHOICE,
                correct_answer=answer,
                choices=choices,
                category="history",
                difficulty=Difficulty(event.get("difficulty", "medium")),
                tags=["knowledge", "history", "dates"],
                evaluation_criteria=EvaluationCriteria(exact_match=True, case_sensitive=False),
            )
