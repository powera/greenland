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

A token can also be spelled by a proper name, through ``NameDerivativeForm``
("John", "John's"). A name is not a sense and takes no share of the frequency,
but it does claim the token: it is listed as an attachment and keeps the token
off :func:`unlinked_word_tokens`. The form tables are iterated from
``storage.token_forms.TOKEN_FORM_SOURCES`` rather than named here.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from storage.models.name_entity import Name
from storage.models.schema import (
    ExternalLexemeAnnotation,
    Lemma,
    WordToken,
)
from storage.token_forms import (
    ATTACHMENT_DERIVATIVE,
    ATTACHMENT_NAME,
    ATTACHMENT_VARIANT,
    TOKEN_FORM_SOURCES,
    claimed_word_token_ids,
)


@dataclass(frozen=True)
class TokenAttachment:
    """One element's claim on this token, through one form row.

    The element is a lemma (``element_type == "lemma"``) or a proper name
    (``"name"``). The ``lemma_*`` fields are named for the common case:
    ``lemma_text`` is the name's text for a name, ``pos_type`` its kind label,
    and ``lemma_id``, ``definition_text`` and ``sense_prominence`` are None.

    ``share`` is this lemma's portion of the token's frequency, as computed by
    ``wordfreq.lexeme_frequency.get_token_share``.  It is filled in only when
    the caller asks for shares; otherwise it is None, because computing it
    costs a query per token and most callers listing many tokens do not need it.
    A name never has a share.
    """

    lemma_id: Optional[int]
    lemma_text: str
    definition_text: Optional[str]
    pos_type: Optional[str]
    disambiguation: Optional[str]
    # None when the sense has never been rated; readers treat that as "common".
    sense_prominence: Optional[str]
    guid: Optional[str]
    attachment_kind: str  # an ATTACHMENT_* constant from storage.token_forms
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
    element_type: str = "lemma"
    name_id: Optional[int] = None

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
            if attachment.lemma_id is not None and attachment.lemma_id not in seen:
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
    """Collect every claim on a token, from each table in TOKEN_FORM_SOURCES."""
    attachments: List[TokenAttachment] = []

    for source in TOKEN_FORM_SOURCES:
        forms = session.query(source.model).filter(source.model.word_token_id == word_token_id)
        for form in forms.all():
            attachments.append(_attachment_for_form(session, form, source.attachment_kind))

    # Base forms first, then by owner then form text, so the page opens on the
    # dictionary headword rather than an arbitrary inflection.
    attachments.sort(
        key=lambda a: (
            not a.is_base_form,
            a.lemma_text,
            a.element_type,
            a.lemma_id or a.name_id or 0,
            a.form_text,
            a.form_id,
        )
    )
    return attachments


def _attachment_for_form(session: Session, form: Any, attachment_kind: str) -> TokenAttachment:
    """Build one attachment from a SurfaceForm row and the element that owns it."""
    owner = form.owner
    if owner.element_type == "name":
        name = session.get(Name, owner.element_id)
        assert name is not None, f"name form {form.id} has no name"
        return TokenAttachment(
            lemma_id=None,
            lemma_text=name.name_text,
            definition_text=None,
            pos_type=name.kind_label,
            disambiguation=name.disambiguation,
            sense_prominence=None,
            guid=name.guid,
            attachment_kind=attachment_kind,
            form_id=form.id,
            form_text=form.surface_text,
            grammatical_form=form.grammatical_form,
            is_base_form=bool(form.is_base_form),
            element_type="name",
            name_id=name.id,
        )

    lemma = session.get(Lemma, owner.element_id)
    assert lemma is not None, f"{attachment_kind} form {form.id} has no lemma"
    return TokenAttachment(
        lemma_id=lemma.id,
        lemma_text=lemma.lemma_text,
        definition_text=lemma.definition_text,
        pos_type=lemma.pos_type,
        disambiguation=lemma.disambiguation,
        sense_prominence=lemma.sense_prominence,
        guid=lemma.guid,
        attachment_kind=attachment_kind,
        form_id=form.id,
        form_text=form.surface_text,
        # VariantForm carries a real grammatical slot in the same vocabulary as
        # DerivativeForm; variant_kind is a separate axis, reported in its own
        # field (and absent on the other form tables).
        grammatical_form=form.grammatical_form,
        is_base_form=bool(form.is_base_form),
        variant_kind=getattr(form, "variant_kind", None),
        variant_key=getattr(form, "variant_key", None),
    )


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
    # A name is not a sense and has no share; its attachment keeps share=None.
    shares: Dict[int, float] = {}
    for lemma_id in view.lemma_ids:
        shares[lemma_id] = get_token_share(session, view.word_token.id, lemma_id)

    attachments = [
        replace(a, share=shares[a.lemma_id]) if a.lemma_id is not None else a
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


def unlinked_word_tokens(
    session: Session,
    language_code: str,
    limit: int = 200,
    max_rank: Optional[int] = None,
    exclude_function_words: bool = True,
) -> List[WordToken]:
    """Return the most frequent tokens no lemma claims, best rank first.

    A token is "linked" when some form row claims it -- any table in
    ``storage.token_forms.TOKEN_FORM_SOURCES``, the same claims
    :func:`_attachments_for_token` collects: a lemma's derivative or variant
    form, or a name's form.  A token with none is a word the corpora measured
    but the database does not know, which is what makes this listing a work
    queue: the top of it is the next word worth adding.

    Tokens with no ``frequency_rank`` are excluded rather than sorted last: the
    rank is a dense ordinal written by
    ``wordfreq.frequency.combined_rank.calculate_token_combined_ranks``, so a
    NULL means that pass has not been run, not that the token is rare. Ordering
    those in among ranked rows would put unscored tokens at an arbitrary spot.

    ``exclude_function_words`` applies the missing-word report's candidate
    filter, and defaults on because without it the whole head of the list is
    "the", "of", "a", "in" -- function words, contractions and bare initials
    that rank high precisely because they are not vocabulary anyone needs to
    add. Turn it off to audit coverage rather than to pick the next word.
    Filtering happens in Python, so the query fetches a multiple of ``limit``
    to leave room for what the filter drops.
    """
    query = session.query(WordToken).filter(
        WordToken.language_code == language_code,
        WordToken.frequency_rank.isnot(None),
        ~WordToken.id.in_(claimed_word_token_ids(session)),
    )
    if max_rank is not None:
        query = query.filter(WordToken.frequency_rank <= max_rank)

    query = query.order_by(WordToken.frequency_rank.asc(), WordToken.token.asc())

    if not exclude_function_words:
        return list(query.limit(limit).all())

    # Imported here rather than at module scope: storage must not depend on
    # reports at import time, and this is the only path that needs the filter.
    from reports.missing_words import is_valid_frequency_candidate

    kept: List[WordToken] = []
    for row in query.limit(max(limit * 8, limit)).all():
        if not is_valid_frequency_candidate(row.token):
            continue
        kept.append(row)
        if len(kept) >= limit:
            break
    return kept


__all__ = [
    "ATTACHMENT_DERIVATIVE",
    "ATTACHMENT_NAME",
    "ATTACHMENT_VARIANT",
    "TokenAttachment",
    "TokenCorpusStat",
    "WORDFREQ_SOURCE_PREFIX",
    "WordTokenView",
    "corpus_name_for_source",
    "get_word_token_view",
    "get_word_token_view_by_text",
    "search_word_tokens",
    "unlinked_word_tokens",
]
