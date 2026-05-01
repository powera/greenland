"""Lexeme-level frequency rollup over per-WordToken WordFrequency rows.

Token frequency lives on WordToken (one count per surface string per language).
A Lexeme is one Lemma's surface-form set in one language; multiple lexemes can
share a surface form (homographs like "bank" the river edge vs. the financial
institution). When that happens we split the token's frequency across the
competing lexemes weighted by ``Lemma.sense_prominence`` (very_common=20,
common=5, uncommon=1). Single-sense words (the common case) get the full
token frequency regardless of their prominence label, since the weight only
matters relative to competitors.

We sum per-form per-corpus frequencies up to the lexeme. Rank rollup is
intentionally not provided here — ranks are not additive; if you need a rank
for a lexeme, derive it from the rolled-up frequency in a downstream pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from storage.lexeme import Lexeme, get_lexeme
from storage.models.schema import (
    SENSE_PROMINENCE_COMMON,
    SENSE_PROMINENCE_WEIGHTS,
    Corpus,
    DerivativeForm,
    Lemma,
    WordFrequency,
)


def _weight_for(prominence: Optional[str]) -> int:
    if prominence is None:
        return SENSE_PROMINENCE_WEIGHTS[SENSE_PROMINENCE_COMMON]
    return SENSE_PROMINENCE_WEIGHTS.get(
        prominence, SENSE_PROMINENCE_WEIGHTS[SENSE_PROMINENCE_COMMON]
    )


def get_token_share(session: Session, word_token_id: int, lemma_id: int) -> float:
    """Return this lemma's share (0.0–1.0) of the given WordToken's frequency.

    The share is ``weight(this_lemma) / sum(weight(every_lemma_attached_via_DerivativeForm))``.
    A token attached to only one lemma always returns 1.0, regardless of that
    lemma's prominence label. A token with no DerivativeForm attachments returns
    0.0 (no lexeme owns the frequency).
    """
    rows = (
        session.query(Lemma.id, Lemma.sense_prominence)
        .join(DerivativeForm, DerivativeForm.lemma_id == Lemma.id)
        .filter(DerivativeForm.word_token_id == word_token_id)
        .distinct()
        .all()
    )
    if not rows:
        return 0.0
    weights = {lid: _weight_for(prom) for lid, prom in rows}
    total = sum(weights.values())
    if total == 0:
        return 0.0
    own = weights.get(lemma_id, 0)
    return own / total


@dataclass(frozen=True)
class FormFrequency:
    """One rolled-up DerivativeForm contribution to a lexeme's frequency."""

    derivative_form_id: int
    derivative_form_text: str
    word_token_id: Optional[int]
    raw_frequency: float  # token's frequency in this corpus before share split
    share: float  # this lexeme's share (0.0–1.0)
    contribution: float  # raw_frequency * share


@dataclass(frozen=True)
class LexemeFrequency:
    """Lexeme-level frequency rollup for one corpus."""

    lemma_id: int
    language_code: str
    corpus_id: int
    corpus_name: str
    total_frequency: float
    form_breakdown: Tuple[FormFrequency, ...] = field(default_factory=tuple)


def get_lexeme_frequency(
    session: Session,
    lexeme: Lexeme,
    corpus_name: str,
) -> Optional[LexemeFrequency]:
    """Roll up token-level frequencies into a single lexeme frequency for a corpus.

    Returns None if the named corpus does not exist. Returns a zero-frequency
    LexemeFrequency (with empty breakdown) if the lexeme has no forms with
    matching WordFrequency rows.
    """
    corpus = session.query(Corpus).filter(Corpus.name == corpus_name).first()
    if corpus is None:
        return None

    breakdown: List[FormFrequency] = []
    total = 0.0
    for form in lexeme.forms:
        if form.word_token_id is None:
            continue
        wf = (
            session.query(WordFrequency)
            .filter(
                WordFrequency.word_token_id == form.word_token_id,
                WordFrequency.corpus_id == corpus.id,
            )
            .first()
        )
        if wf is None or wf.frequency is None:
            continue
        share = get_token_share(session, form.word_token_id, lexeme.lemma.id)
        contribution = wf.frequency * share
        total += contribution
        breakdown.append(
            FormFrequency(
                derivative_form_id=form.id,
                derivative_form_text=form.derivative_form_text,
                word_token_id=form.word_token_id,
                raw_frequency=wf.frequency,
                share=share,
                contribution=contribution,
            )
        )

    return LexemeFrequency(
        lemma_id=lexeme.lemma.id,
        language_code=lexeme.language_code,
        corpus_id=corpus.id,
        corpus_name=corpus.name,
        total_frequency=total,
        form_breakdown=tuple(breakdown),
    )


def get_lexeme_frequencies_all_corpora(
    session: Session,
    lexeme: Lexeme,
) -> Dict[str, LexemeFrequency]:
    """Roll up across every Corpus row in the database. Empty rollups are included."""
    out: Dict[str, LexemeFrequency] = {}
    for corpus in session.query(Corpus).all():
        rollup = get_lexeme_frequency(session, lexeme, corpus.name)
        if rollup is not None:
            out[corpus.name] = rollup
    return out


def get_lemma_frequency(
    session: Session,
    lemma_id: int,
    language_code: str,
    corpus_name: str,
) -> Optional[LexemeFrequency]:
    """Convenience: build the Lexeme for ``(lemma_id, language_code)`` and roll up."""
    lexeme = get_lexeme(session, lemma_id, language_code)
    if lexeme is None:
        return None
    return get_lexeme_frequency(session, lexeme, corpus_name)


__all__ = [
    "FormFrequency",
    "LexemeFrequency",
    "get_lemma_frequency",
    "get_lexeme_frequencies_all_corpora",
    "get_lexeme_frequency",
    "get_token_share",
]
