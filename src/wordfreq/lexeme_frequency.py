"""Lexeme-level frequency rollup over external lexeme annotations.

Token frequency lives on ExternalLexemeAnnotation (one row per surface form per
source per language). A Lexeme is one Lemma's surface-form set in one language;
multiple lexemes can share a surface form (homographs like "bank" the river
edge vs. the financial institution). When that happens we split the token's
frequency across the competing lexemes weighted by ``Lemma.sense_prominence``
(very_common=20, common=5, uncommon=1, rare=0.15). Single-sense words (the
common case) get the full token frequency regardless of their prominence label,
since the weight only matters relative to competitors.

We sum per-form per-corpus frequencies up to the lexeme. Ranks are not summed,
because ranks are not additive: ``get_lexeme_form_rank_shares`` hands the raw
ranks and their homograph shares to ``wordfreq.frequency.zipf``, which converts
each to an implied frequency, applies the share, sums, and converts back.

Spelling variants count toward their lemma. "aluminium" is the same lexeme as
"aluminum", so a corpus that spells it the British way is still measuring how
often this word is used. Variant forms live in ``variant_forms`` rather than
``derivative_forms`` (see ``storage.models.variant_form``), so they are
collected by a separate query here and folded into the same total.

The ``corpus_name`` argument is the wordfreq corpus identifier (e.g.
``"19th_books"``); internally it maps to annotation source ``wordfreq_<name>``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union

from sqlalchemy.orm import Session

from storage.lexeme import Lexeme, get_lexeme
from storage.models.schema import (
    SENSE_PROMINENCE_COMMON,
    SENSE_PROMINENCE_WEIGHTS,
    DerivativeForm,
    ExternalLexemeAnnotation,
    Lemma,
    WordToken,
)
from storage.models.variant_form import VariantForm
from wordfreq.frequency.corpus import get_enabled_corpus_configs


def _token_sort_key(token: WordToken) -> Tuple[int, int, int]:
    """Order case-variant tokens best-first for the case-insensitive fallback.

    A ranked token beats an unranked one, then the better (lower) rank wins,
    then the lower id, so the choice never depends on query order. An unranked
    token is one no corpus reached -- typically a tier import's capitalized
    spelling -- and is the worse thing to link a form to.
    """
    rank = token.frequency_rank
    if rank is None:
        return (1, 0, token.id)
    return (0, rank, token.id)


def link_forms_to_word_tokens(session: Session, language_code: str = "en") -> Dict[str, int]:
    """Set ``word_token_id`` on forms whose surface text matches a ``WordToken``.

    Forms arrive from the release files with no ``word_token_id``: the release
    format carries no tokens, and the wordfreq importer creates ``WordToken``
    rows only once a corpus is loaded. Until the two are wired together every
    rollup here skips every form (they all filter on ``word_token_id is not
    None``), so a database can hold a full set of corpus annotations and still
    roll up zero -- combined ranks then quietly collapse to the tier signals
    (CEFR / Cambridge YLE / Basic English) alone.

    Both ``derivative_forms`` and ``variant_forms`` are linked: a variant counts
    toward its lemma (see the module docstring), so leaving variants unlinked
    would drop the British spelling of a word from its own frequency.

    A form's own spelling is matched first, and only then its lowercased one.
    Both spellings can exist as tokens -- ``uq_word_token_language`` is
    case-sensitive, and the corpora now count "March" apart from "march" -- so
    an exact match is the difference between the month's rank and the verb's.

    Where only a differently-cased token exists, the fallback picks
    deterministically: a ranked row beats an unranked one, then the better
    rank, then the lower id. It used to be whichever row the unordered query
    happened to return first, which is how the "London" lemma ended up on a
    rankless tier-import row while "China" landed on its corpus-ranked one.

    Only rows whose FK is currently NULL are touched, so this is idempotent and
    safe to re-run.

    Returns a dict of ``{"derivative_forms": n, "variant_forms": n}``.
    """
    tokens = session.query(WordToken).filter(WordToken.language_code == language_code).all()

    token_id_by_exact: Dict[str, int] = {}
    best_by_lower: Dict[str, WordToken] = {}
    for token in tokens:
        token_id_by_exact[token.token] = token.id
        lowered = token.token.lower()
        incumbent = best_by_lower.get(lowered)
        if incumbent is None or _token_sort_key(token) < _token_sort_key(incumbent):
            best_by_lower[lowered] = token
    token_id_by_lower: Dict[str, int] = {
        lowered: token.id for lowered, token in best_by_lower.items()
    }

    def resolve(text: str) -> Optional[int]:
        """The best token id for one form's surface text, or None."""
        if not text:
            return None
        exact = token_id_by_exact.get(text)
        if exact is not None:
            return exact
        return token_id_by_lower.get(text.lower())

    counts: Dict[str, int] = {"derivative_forms": 0, "variant_forms": 0}
    if not token_id_by_exact:
        return counts

    derivative_forms = (
        session.query(DerivativeForm)
        .filter(
            DerivativeForm.language_code == language_code,
            DerivativeForm.word_token_id.is_(None),
        )
        .all()
    )
    for derivative_form in derivative_forms:
        token_id = resolve(derivative_form.derivative_form_text or "")
        if token_id is not None:
            derivative_form.word_token_id = token_id
            counts["derivative_forms"] += 1

    variant_forms = (
        session.query(VariantForm)
        .filter(
            VariantForm.language_code == language_code,
            VariantForm.word_token_id.is_(None),
        )
        .all()
    )
    for variant_form in variant_forms:
        token_id = resolve(variant_form.variant_form_text or "")
        if token_id is not None:
            variant_form.word_token_id = token_id
            counts["variant_forms"] += 1

    if counts["derivative_forms"] or counts["variant_forms"]:
        session.commit()
    return counts


def _weight_for(prominence: Optional[str]) -> float:
    if prominence is None:
        return SENSE_PROMINENCE_WEIGHTS[SENSE_PROMINENCE_COMMON]
    return SENSE_PROMINENCE_WEIGHTS.get(
        prominence, SENSE_PROMINENCE_WEIGHTS[SENSE_PROMINENCE_COMMON]
    )


def get_token_share(session: Session, word_token_id: int, lemma_id: int) -> float:
    """Return this lemma's share (0.0–1.0) of the given WordToken's frequency.

    The share is ``weight(this_lemma) / sum(weight(every_attached_lemma))``. A
    lemma is attached when it owns the token through a ``DerivativeForm`` or
    through a ``VariantForm``: a lemma reaching a token only by a variant must
    still be a claimant, or the frequency of that spelling is charged to nobody.

    A token attached to only one lemma always returns 1.0, regardless of that
    lemma's prominence label. A token with no attachments returns 0.0 (no
    lexeme owns the frequency).
    """
    rows = (
        session.query(Lemma.id, Lemma.sense_prominence)
        .join(DerivativeForm, DerivativeForm.lemma_id == Lemma.id)
        .filter(DerivativeForm.word_token_id == word_token_id)
        .distinct()
        .all()
    ) + (
        session.query(Lemma.id, Lemma.sense_prominence)
        .join(VariantForm, VariantForm.lemma_id == Lemma.id)
        .filter(VariantForm.word_token_id == word_token_id)
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
    corpus_name: str
    source: str
    total_frequency: float
    form_breakdown: Tuple[FormFrequency, ...] = field(default_factory=tuple)


def _source_for_corpus(corpus_name: str) -> str:
    return f"wordfreq_{corpus_name}"


def _form_text(form: Union[DerivativeForm, VariantForm]) -> str:
    """Surface text of a form row from either table.

    The two models spell the column differently (``derivative_form_text`` vs.
    ``variant_form_text``) but the rollup treats them alike.
    """
    if isinstance(form, VariantForm):
        return form.variant_form_text
    return form.derivative_form_text


def get_lexeme_frequency(
    session: Session,
    lexeme: Lexeme,
    corpus_name: str,
) -> LexemeFrequency:
    """Roll up token-level frequencies into a single lexeme frequency for a corpus.

    Both the lexeme's own forms and its variant spellings contribute:
    "aluminium" is the same word as "aluminum", so a corpus using the British
    spelling is still counting this lexeme.

    Returns a zero-frequency LexemeFrequency (with empty breakdown) if the
    lexeme has no forms with matching ExternalLexemeAnnotation rows for the
    corpus.
    """
    source = _source_for_corpus(corpus_name)

    breakdown: List[FormFrequency] = []
    total = 0.0

    # A Lexeme is deliberately a facade over derivative_forms alone, so that an
    # unfiltered read of a lemma's forms does not return "grey"; frequency is
    # one of the consumers that opts into variants explicitly.
    variant_forms = (
        session.query(VariantForm)
        .filter(
            VariantForm.lemma_id == lexeme.lemma.id,
            VariantForm.language_code == lexeme.language_code,
        )
        .all()
    )

    # One contribution per distinct token, not per form row. A word usually
    # fills several grammatical slots -- English collapses person and number in
    # the past tense, so "refined" is stored once per slot and all seven rows
    # point at the same token. Adding each row would multiply that word's
    # frequency by the size of the paradigm table, which is why verbs used to
    # rank far more common than the corpora support.
    counted_token_ids: set[int] = set()

    for form in list(lexeme.forms) + variant_forms:
        if form.word_token_id is None or form.word_token_id in counted_token_ids:
            continue
        counted_token_ids.add(form.word_token_id)
        annotation = (
            session.query(ExternalLexemeAnnotation)
            .filter(
                ExternalLexemeAnnotation.word_token_id == form.word_token_id,
                ExternalLexemeAnnotation.source == source,
            )
            .first()
        )
        if annotation is None or annotation.frequency is None:
            continue
        share = get_token_share(session, form.word_token_id, lexeme.lemma.id)
        contribution = annotation.frequency * share
        total += contribution
        breakdown.append(
            FormFrequency(
                derivative_form_id=form.id,
                derivative_form_text=_form_text(form),
                word_token_id=form.word_token_id,
                raw_frequency=annotation.frequency,
                share=share,
                contribution=contribution,
            )
        )

    return LexemeFrequency(
        lemma_id=lexeme.lemma.id,
        language_code=lexeme.language_code,
        corpus_name=corpus_name,
        source=source,
        total_frequency=total,
        form_breakdown=tuple(breakdown),
    )


def get_lexeme_form_ranks(
    session: Session,
    lexeme: Lexeme,
    corpus_name: str,
) -> List[int]:
    """Every stored corpus rank among this lexeme's forms, variants included.

    Share-blind: a form contested by several senses yields its full rank here.
    Prefer :func:`get_lexeme_form_rank_shares`, which pairs each rank with this
    lemma's share of it; combining these bare ranks gives every sense of a
    homograph the same rank no matter how the frequency divides.

    Returns:
        The ranks, in no particular order. Empty when the lexeme has no ranked
        form in this corpus.
    """
    return [rank for rank, _share in get_lexeme_form_rank_shares(session, lexeme, corpus_name)]


def get_lexeme_form_rank_shares(
    session: Session,
    lexeme: Lexeme,
    corpus_name: str,
) -> List[Tuple[int, float]]:
    """Each stored corpus rank among this lexeme's forms, with its share.

    The corpus files carry a rank as well as a frequency for each surface form,
    and both are kept on the annotation. The ranks are returned as they were
    imported, for ``wordfreq.frequency.zipf.combine_weighted_ranks`` to fold
    into one rank for the lexeme -- rather than re-derived by sorting lemmas
    against each other.

    A rank is a property of the surface form, and the corpus cannot say which
    sense of "bank" it counted. So each rank is paired with this lemma's
    ``get_token_share`` of the form: the same split that divides the form's
    frequency divides the frequency its rank implies. Without that pairing every
    sense of a homograph combines to an identical rank while their rolled-up
    frequencies differ by orders of magnitude -- "top" the spinning toy holding
    0.6% of the token's frequency but ranking exactly as well as "top" the
    highest point.

    An uncontested form has a share of 1.0, so a word with no homograph is
    unaffected.

    Returns:
        ``(rank, share)`` pairs, in no particular order. Empty when the lexeme
        has no ranked form in this corpus.
    """
    source = _source_for_corpus(corpus_name)

    variant_forms = (
        session.query(VariantForm)
        .filter(
            VariantForm.lemma_id == lexeme.lemma.id,
            VariantForm.language_code == lexeme.language_code,
        )
        .all()
    )

    token_ids = {
        form.word_token_id
        for form in list(lexeme.forms) + variant_forms
        if form.word_token_id is not None
    }
    if not token_ids:
        return []

    rows = (
        session.query(
            ExternalLexemeAnnotation.ordinal_rank,
            ExternalLexemeAnnotation.word_token_id,
        )
        .filter(
            ExternalLexemeAnnotation.word_token_id.in_(token_ids),
            ExternalLexemeAnnotation.source == source,
            ExternalLexemeAnnotation.ordinal_rank.isnot(None),
        )
        .all()
    )

    # One share lookup per token, not per annotation row: a token may be ranked
    # by several corpora, but its claimants do not change between them.
    shares: Dict[int, float] = {}
    out: List[Tuple[int, float]] = []
    for rank, token_id in rows:
        if rank is None or rank <= 0 or token_id is None:
            continue
        if token_id not in shares:
            shares[token_id] = get_token_share(session, token_id, lexeme.lemma.id)
        out.append((rank, shares[token_id]))
    return out


def get_lexeme_frequencies_all_corpora(
    session: Session,
    lexeme: Lexeme,
) -> Dict[str, LexemeFrequency]:
    """Roll up across every enabled wordfreq corpus. Empty rollups are included."""
    out: Dict[str, LexemeFrequency] = {}
    for cfg in get_enabled_corpus_configs():
        out[cfg.name] = get_lexeme_frequency(session, lexeme, cfg.name)
    return out


def get_lemma_frequency(
    session: Session,
    lemma_id: int,
    language_code: str,
    corpus_name: str,
) -> Optional[LexemeFrequency]:
    """Convenience: build the Lexeme for ``(lemma_id, language_code)`` and roll up.

    Returns None only if the lemma has no Lexeme (no derivative forms in the
    requested language).
    """
    lexeme = get_lexeme(session, lemma_id, language_code)
    if lexeme is None:
        return None
    return get_lexeme_frequency(session, lexeme, corpus_name)


__all__ = [
    "FormFrequency",
    "LexemeFrequency",
    "get_lemma_frequency",
    "get_lexeme_frequencies_all_corpora",
    "get_lexeme_form_rank_shares",
    "get_lexeme_form_ranks",
    "get_lexeme_frequency",
    "get_token_share",
]
