"""Bounded bulk writes for mechanical generation; interactive edits keep normal CRUD."""

import json
from types import TracebackType
from typing import Any, Optional, cast

from sqlalchemy.orm import Session

from langtools.mechanical_inputs import MechanicalInputs
from storage.models.grammar_fact import GrammarFact
from storage.models.operation_log import OperationLog
from storage.models.schema import DerivativeForm, WordToken
from storage.models.variant_form import VariantForm
from storage.models.uncertain_llm_result import UncertainLLMResult


class MechanicalBatch:
    def __init__(self, session: Session, lemma_ids: list[int], language: str) -> None:
        self.session = session
        self.language = language
        self.inputs = MechanicalInputs.load(session, lemma_ids)
        self.forms: list[dict[str, Any]] = []
        self.variants: list[dict[str, Any]] = []
        self.facts: list[dict[str, Any]] = []
        self.logs: list[dict[str, Any]] = []
        self.resolved_facts: dict[str, set[int]] = {}

    def __enter__(self) -> "MechanicalBatch":
        if "mechanical_batch" in self.session.info:
            raise RuntimeError("Mechanical generation batches cannot be nested")
        self.session.info["mechanical_batch"] = self
        self.session.info["mechanical_inputs"] = self.inputs
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.session.info.pop("mechanical_inputs", None)
        self.session.info.pop("mechanical_batch", None)

    def add_fact(self, lemma_id: int, fact_type: str, value: str) -> None:
        # add_grammar_fact's confidence gate clears prior uncertainty even
        # when an existing empty fact prevents inserting the derived value.
        self.resolved_facts.setdefault(fact_type, set()).add(lemma_id)
        identity = (lemma_id, self.language, fact_type)
        # Existing NULL/empty facts are also left alone, just like add_grammar_fact.
        if identity in self.inputs.facts:
            return
        self.inputs.facts[identity] = value
        self.facts.append(
            dict(
                lemma_id=lemma_id,
                language_code=self.language,
                fact_type=fact_type,
                fact_value=value,
                notes="derived mechanically by generate_mechanical_forms",
                verified=False,
            )
        )

    def add_log(self, lemma_id: int, details: dict[str, Any]) -> None:
        self.logs.append(
            dict(
                lemma_id=lemma_id,
                source="generate_mechanical_forms",
                operation_type="mechanical_forms_generated",
                fact=json.dumps({**details, "entity_type": "derivative_form"}),
            )
        )

    def flush(self) -> None:
        """Insert without committing; the outer loop owns the transaction boundary."""
        for fact_type, lemma_ids in self.resolved_facts.items():
            self.session.query(UncertainLLMResult).filter(
                UncertainLLMResult.topic == fact_type,
                UncertainLLMResult.language_code == self.language,
                UncertainLLMResult.lemma_id.in_(lemma_ids),
            ).delete(synchronize_session="fetch")
        texts = sorted(
            {row["derivative_form_text"] for row in self.forms}
            | {row["variant_form_text"] for row in self.variants}
        )
        token_ids: dict[str, int] = {}
        for start in range(0, len(texts), 500):
            chunk = texts[start : start + 500]
            existing = dict(
                self.session.query(WordToken.token, WordToken.id)
                .filter(WordToken.language_code == self.language, WordToken.token.in_(chunk))
                .all()
            )
            missing = [
                dict(token=value, language_code=self.language)
                for value in chunk
                if value not in existing
            ]
            if missing:
                self.session.bulk_insert_mappings(WordToken, missing)
                existing = dict(
                    self.session.query(WordToken.token, WordToken.id)
                    .filter(WordToken.language_code == self.language, WordToken.token.in_(chunk))
                    .all()
                )
            token_ids.update(existing)
        for row in self.forms:
            row["word_token_id"] = token_ids[row["derivative_form_text"]]
        for row in self.variants:
            row["word_token_id"] = token_ids[row["variant_form_text"]]
        # These forms have no pronunciation; their rhyme key is necessarily NULL.
        # Bulk mappings intentionally avoid per-row ORM insert hooks/refreshes.
        for model, rows in (
            (GrammarFact, self.facts),
            (DerivativeForm, self.forms),
            (VariantForm, self.variants),
            (OperationLog, self.logs),
        ):
            if rows:
                self.session.bulk_insert_mappings(model, rows)


def current_batch(session: Session) -> Optional[MechanicalBatch]:
    return cast(Optional[MechanicalBatch], session.info.get("mechanical_batch"))
