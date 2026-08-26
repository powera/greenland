"""Read facade over a single WordToken: the surface string, not the sense.

``WordToken`` is the row for one spelling in one language -- "top", "will",
"ice cream".  It already is the string-level identity this view needs, so this
module introduces no new noun and no new table: it gathers what the database
knows about one existing ``WordToken`` row into one shape a page can render.

The distinction from :mod:`storage.lexeme` matters and runs the other way.  A
``Lexeme`` there is one *sense* -- one Lemma paired with its forms in one
language -- so the three lemmas that spell themselves "top" are three Lexemes.
Here they are three attachments to a single WordToken.  Frequency is measured
at this level: a corpus counts the string "top" and cannot say which sense it
saw, which is why ``wordfreq.lexeme_frequency`` has to split a token's count
across the competing senses.  This view shows the count before that split, and
the split itself, side by side.

A token is reached from a lemma two ways, and both are collected here:

* ``DerivativeForm`` -- an inflection or synonym of the lemma.  "tops" and
  "topped" are derivative forms whose token differs from the lemma's own.
* ``VariantForm`` -- an alternate spelling of the same word ("grey" for
  "gray").  Variants live in their own table so that an unfiltered read of a
  lemma's forms does not return them (see :mod:`storage.models.variant_form`),
  so reaching them takes a second query.

Both are claimants on the token's frequency, which is why
``wordfreq.lexeme_frequency.get_token_share`` counts both, and why this module
reports both rather than only the derivative forms.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from storage.models.schema import (
    DerivativeForm,
    ExternalLexemeAnnotation,
    Lemma,
    WordToken,
)
from storage.models.variant_form import VariantForm

# How a lemma reaches this token.  A lemma may do both (a variant spelling that
# is also an inflected form), in which case it appears once per attachment.
ATTACHMENT_DERIVATIVE: str = "derivative"
ATTACHMENT_VARIANT: str = "variant"


@dataclass(frozen=True)
class TokenAttachment:
    """One lemma's claim on this token, through one form row.

    ``share`` is this lemma's portion of the token's frequency, as computed by
    ``wordfreq.lexeme_frequency.get_token_share``.  It is filled in only when
    the caller asks for shares; otherwise it is None, because computing it
    costs a query per token and most callers listing many tokens do not need it.
    """

    lemma_id: int
    lemma_text: str
    definition_text: str
    pos_type: str
    disambiguation: Optional[str]
    sense_prominence: str
    guid: Optional[str]
    attachment_kind: str  # ATTACHMENT_DERIVATIVE or ATTACHMENT_VARIANT
    form_id: int
    form_text: str
    grammatical_form: Optional[str]
    is_base_form: bool
    # Which variant of the lemma this row belongs to ("grey", "donut"), for a
    # variant attachment only. None for a derivative form, which is not a
    # variant of anything.
    variant_kind: Optional[str] = None
    variant_key: Optional[str] = None
    share: Optional[float] = None

    @property
    def display_text(self) -> str:
        """The lemma with its sense disambiguation, matching ``Lemma.display_text``."""
        if self.disambiguation:
            return f"{self.lemma_text} ({self.disambiguation})"
        return self.lemma_text


@dataclass(frozen=True)
class TokenCorpusStat:
    """This token's standing in one annotation source.

    ``source`` is the raw annotation source (``wordfreq_cooking``,
    ``cambridge_yle``); ``corpus_name`` is the wordfreq corpus it came from
    (``cooking``) or None for a tier source, which carries a tier name instead
    of a rank.
    """

    source: str
    corpus_name: Optional[str]
    tier_name: str
    ordinal_rank: Optional[int]
    frequency: Optional[float]
    pos_hint: Optional[str]
    sense_hint: Optional[str]


@dataclass(frozen=True)
class WordTokenView:
    """Everything this database knows about one surface string in one language.

    Identity is the underlying ``WordToken`` row, so ``(token, language_code)``
    -- the table's own unique key.
    """

    word_token: WordToken
    attachments: List[TokenAttachment] = field(default_factory=list)
    corpus_stats: List[TokenCorpusStat] = field(default_factory=list)

    @property
    def token(self) -> str:
        return self.word_token.token

    @property
    def language_code(self) -> str:
        return self.word_token.language_code

    @property
    def is_multiword(self) -> bool:
        """Whether the string spans more than one whitespace-separated word.

        "ice cream" and "a lot of" are stored as single tokens, so a token is
        not always a word.
        """
        return " " in self.word_token.token.strip()

    @property
    def lemma_ids(self) -> List[int]:
        """Distinct lemma ids attached to this token, in first-seen order."""
        seen: List[int] = []
        for attachment in self.attachments:
            if attachment.lemma_id not in seen:
                seen.append(attachment.lemma_id)
        return seen

    @property
    def is_homograph(self) -> bool:
        """Whether more than one lemma competes for this string."""
        return len(self.lemma_ids) > 1

    @property
    def wordfreq_stats(self) -> List[TokenCorpusStat]:
        """Only the stats from wordfreq corpora, which carry ranks."""
        return [stat for stat in self.corpus_stats if stat.corpus_name is not None]

    @property
    def tier_stats(self) -> List[TokenCorpusStat]:
        """Only the stats from tier sources (YLE, CEFR, Basic English)."""
        return [stat for stat in self.corpus_stats if stat.corpus_name is None]


WORDFREQ_SOURCE_PREFIX: str = "wordfreq_"


def corpus_name_for_source(source: str) -> Optional[str]:
    """Return the wordfreq corpus behind an annotation source, or None.

    The inverse of ``wordfreq.lexeme_frequency._source_for_corpus``. A tier
    source such as ``cefr`` is not a corpus and yields None.
    """
    if source.startswith(WORDFREQ_SOURCE_PREFIX):
        return source[len(WORDFREQ_SOURCE_PREFIX) :]
    return None


def _attachments_for_token(session: Session, word_token_id: int) -> List[TokenAttachment]:
    """Collect every lemma claim on a token, from both form tables."""
    attachments: List[TokenAttachment] = []

    derivative_rows = (
        session.query(DerivativeForm, Lemma)
        .join(Lemma, DerivativeForm.lemma_id == Lemma.id)
        .filter(DerivativeForm.word_token_id == word_token_id)
        .all()
    )
    for form, lemma in derivative_rows:
        attachments.append(
            TokenAttachment(
                lemma_id=lemma.id,
                lemma_text=lemma.lemma_text,
                definition_text=lemma.definition_text,
                pos_type=lemma.pos_type,
                disambiguation=lemma.disambiguation,
                sense_prominence=lemma.sense_prominence,
                guid=lemma.guid,
                attachment_kind=ATTACHMENT_DERIVATIVE,
                form_id=form.id,
                form_text=form.derivative_form_text,
                grammatical_form=form.grammatical_form,
                is_base_form=bool(form.is_base_form),
            )
        )

    variant_rows = (
        session.query(VariantForm, Lemma)
        .join(Lemma, VariantForm.lemma_id == Lemma.id)
        .filter(VariantForm.word_token_id == word_token_id)
        .all()
    )
    for variant, lemma in variant_rows:
        attachments.append(
            TokenAttachment(
                lemma_id=lemma.id,
                lemma_text=lemma.lemma_text,
                definition_text=lemma.definition_text,
                pos_type=lemma.pos_type,
                disambiguation=lemma.disambiguation,
                sense_prominence=lemma.sense_prominence,
                guid=lemma.guid,
                attachment_kind=ATTACHMENT_VARIANT,
                form_id=variant.id,
                form_text=variant.variant_form_text,
                # VariantForm carries a real grammatical slot in the same
                # vocabulary as DerivativeForm; variant_kind is a separate
                # axis and is reported in its own field.
                grammatical_form=variant.grammatical_form,
                is_base_form=bool(variant.is_base_form),
                variant_kind=variant.variant_kind,
                variant_key=variant.variant_key,
            )
        )

    # Base forms first, then by lemma then form text, so the page opens on the
    # dictionary headword rather than an arbitrary inflection.
    attachments.sort(
        key=lambda a: (not a.is_base_form, a.lemma_text, a.lemma_id, a.form_text, a.form_id)
    )
    return attachments


def _corpus_stats_for_token(session: Session, word_token_id: int) -> List[TokenCorpusStat]:
    """Every annotation row for a token, corpus and tier sources alike."""
    rows: List[ExternalLexemeAnnotation] = (
        session.query(ExternalLexemeAnnotation)
        .filter(ExternalLexemeAnnotation.word_token_id == word_token_id)
        .all()
    )
    stats = [
        TokenCorpusStat(
            source=row.source,
            corpus_name=corpus_name_for_source(row.source),
            tier_name=row.tier_name,
            ordinal_rank=row.ordinal_rank,
            frequency=row.frequency,
            pos_hint=row.pos_hint,
            sense_hint=row.sense_hint,
        )
        for row in rows
    ]
    # Ranked corpora first and best rank first: the most informative line at the
    # top. Tier rows have no rank and sort after, by source name.
    stats.sort(
        key=lambda s: (
            s.corpus_name is None,
            s.ordinal_rank if s.ordinal_rank is not None else 1 << 30,
            s.source,
        )
    )
    return stats


def _with_shares(session: Session, view: WordTokenView) -> WordTokenView:
    """Return a copy of ``view`` with ``share`` filled on every attachment.

    Imported lazily because ``wordfreq`` depends on ``storage``; importing it
    at module scope would make this module's import order matter.
    """
    from wordfreq.lexeme_frequency import get_token_share

    # One lookup per lemma, not per attachment: a lemma reaching the token
    # through both a derivative form and a variant spelling is one claimant
    # with one share, and get_token_share already counts it once.
    shares: Dict[int, float] = {}
    for attachment in view.attachments:
        if attachment.lemma_id not in shares:
            shares[attachment.lemma_id] = get_token_share(
                session, view.word_token.id, attachment.lemma_id
            )

    attachments = [
        TokenAttachment(
            lemma_id=a.lemma_id,
            lemma_text=a.lemma_text,
            definition_text=a.definition_text,
            pos_type=a.pos_type,
            disambiguation=a.disambiguation,
            sense_prominence=a.sense_prominence,
            guid=a.guid,
            attachment_kind=a.attachment_kind,
            form_id=a.form_id,
            form_text=a.form_text,
            grammatical_form=a.grammatical_form,
            is_base_form=a.is_base_form,
            variant_kind=a.variant_kind,
            variant_key=a.variant_key,
            share=shares[a.lemma_id],
        )
        for a in view.attachments
    ]
    return WordTokenView(
        word_token=view.word_token,
        attachments=attachments,
        corpus_stats=view.corpus_stats,
    )


def get_word_token_view(
    session: Session,
    word_token_id: int,
    include_shares: bool = True,
) -> Optional[WordTokenView]:
    """Build the view for a ``WordToken`` by id, or None if no such row.

    Args:
        session: Open session.
        word_token_id: The ``word_tokens.id`` to describe.
        include_shares: Whether to compute each lemma's share of the token's
            frequency. Costs a query per distinct lemma; pass False when
            listing many tokens.
    """
    token = session.query(WordToken).filter(WordToken.id == word_token_id).first()
    if token is None:
        return None
    view = WordTokenView(
        word_token=token,
        attachments=_attachments_for_token(session, token.id),
        corpus_stats=_corpus_stats_for_token(session, token.id),
    )
    if include_shares and view.attachments:
        view = _with_shares(session, view)
    return view


def get_word_token_view_by_text(
    session: Session,
    token_text: str,
    language_code: str,
    include_shares: bool = True,
) -> Optional[WordTokenView]:
    """Build the view for a surface string, or None if the token is unknown.

    ``(token, language_code)`` is unique in ``word_tokens``, so this is an
    exact lookup rather than a search.
    """
    token = (
        session.query(WordToken)
        .filter(
            WordToken.token == token_text,
            WordToken.language_code == language_code,
        )
        .first()
    )
    if token is None:
        return None
    return get_word_token_view(session, token.id, include_shares=include_shares)


def search_word_tokens(
    session: Session,
    query_text: str,
    language_code: str,
    limit: int = 50,
) -> List[WordToken]:
    """Return tokens whose text contains ``query_text``, exact matches first.

    Ordered so that typing "top" puts the token "top" above "topic" and
    "stopped", then the rest by frequency rank (unranked last) and alphabet.
    """
    needle = query_text.strip()
    if not needle:
        return []
    rows: List[WordToken] = (
        session.query(WordToken)
        .filter(
            WordToken.language_code == language_code,
            WordToken.token.ilike(f"%{needle}%"),
        )
        .limit(max(limit * 4, limit))
        .all()
    )
    lowered = needle.lower()
    rows.sort(
        key=lambda t: (
            t.token.lower() != lowered,
            not t.token.lower().startswith(lowered),
            t.frequency_rank if t.frequency_rank is not None else 1 << 30,
            t.token,
        )
    )
    return rows[:limit]


__all__ = [
    "ATTACHMENT_DERIVATIVE",
    "ATTACHMENT_VARIANT",
    "TokenAttachment",
    "TokenCorpusStat",
    "WORDFREQ_SOURCE_PREFIX",
    "WordTokenView",
    "corpus_name_for_source",
    "get_word_token_view",
    "get_word_token_view_by_text",
    "search_word_tokens",
]
