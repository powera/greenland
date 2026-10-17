"""The form tables that can claim a corpus ``WordToken``, in one place.

A ``WordToken`` is one spelling a corpus counted ("John", "tops", "grey"). It
is *claimed* when some element spells it through a form row:

* ``DerivativeForm`` -- an inflection of a lemma ("tops" for "top");
* ``VariantForm`` -- an alternate spelling of a lemma ("grey" for "gray");
* ``NameDerivativeForm`` -- a form of a proper name ("John", "John's").

The first two belong to lemmas and the third to names, which deliberately live
in their own table (see ``storage.models.name_entity``). Code that asks a
question about *tokens* -- is this one claimed, who claims it, which token does
this form spell -- should not care which, so it iterates
:data:`TOKEN_FORM_SOURCES` instead of naming the tables. Adding a form table is
then one entry here, and the unlinked-token report, the token view and the
token linker all pick it up.

Code that asks a question about *lemmas* (levels, translations, exports) keeps
reading ``DerivativeForm`` directly: names are kept out of those on purpose.

Rows of every source satisfy :class:`storage.elements.interfaces.SurfaceForm`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Query, Session

from storage.models.name_entity import NameDerivativeForm
from storage.models.schema import DerivativeForm, WordToken
from storage.models.variant_form import VariantForm

# How an element reaches a token. A lemma may do both of the first two (a
# variant spelling that is also an inflected form).
ATTACHMENT_DERIVATIVE: str = "derivative"
ATTACHMENT_VARIANT: str = "variant"
ATTACHMENT_NAME: str = "name"


@dataclass(frozen=True)
class TokenFormSource:
    """One table of form rows that can carry a ``word_token_id``.

    ``model`` is the ORM class and ``text_column`` its surface-text column
    (the column the linker matches against ``WordToken.token``).
    ``element_type`` names the owner kind, matching ``ElementRef.element_type``;
    ``table_name`` keys per-source counts.

    ``exact_case_only`` turns off the linker's lowercase fallback. Names set it:
    a name is matched case-sensitively everywhere else ("Mark" the name is not
    "mark" the word), so the "Mark" form must not link to the "mark" token
    when no capitalized token exists.
    """

    model: Any
    text_column: Any
    element_type: str
    attachment_kind: str
    exact_case_only: bool = False

    @property
    def table_name(self) -> str:
        return str(self.model.__tablename__)


TOKEN_FORM_SOURCES: Tuple[TokenFormSource, ...] = (
    TokenFormSource(
        model=DerivativeForm,
        text_column=DerivativeForm.derivative_form_text,
        element_type="lemma",
        attachment_kind=ATTACHMENT_DERIVATIVE,
    ),
    TokenFormSource(
        model=VariantForm,
        text_column=VariantForm.variant_form_text,
        element_type="lemma",
        attachment_kind=ATTACHMENT_VARIANT,
    ),
    TokenFormSource(
        model=NameDerivativeForm,
        text_column=NameDerivativeForm.derivative_form_text,
        element_type="name",
        attachment_kind=ATTACHMENT_NAME,
        exact_case_only=True,
    ),
)


def claimed_word_token_ids(session: Session) -> Query[Any]:
    """Return a query of every ``word_token_id`` some form row claims.

    The union over :data:`TOKEN_FORM_SOURCES`, for use as
    ``WordToken.id.in_(claimed_word_token_ids(session))``.
    """
    queries: List[Query[Any]] = [
        session.query(source.model.word_token_id).filter(source.model.word_token_id.isnot(None))
        for source in TOKEN_FORM_SOURCES
    ]
    return queries[0].union(*queries[1:])


def token_preference_key(token: WordToken) -> Tuple[int, int, int]:
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


class WordTokenResolver:
    """Map a form's surface text to the ``WordToken`` it should link to.

    A form's own spelling is matched first, and only then its lowercased one.
    Both spellings can exist as tokens -- ``uq_word_token_language`` is
    case-sensitive, and the corpora count "March" apart from "march" -- so an
    exact match is the difference between the month's rank and the verb's.
    Where only a differently-cased token exists, :func:`token_preference_key`
    picks deterministically.
    """

    def __init__(self, tokens: List[WordToken]) -> None:
        self._by_exact: Dict[str, int] = {}
        best_by_lower: Dict[str, WordToken] = {}
        for token in tokens:
            self._by_exact[token.token] = token.id
            lowered = token.token.lower()
            incumbent = best_by_lower.get(lowered)
            if incumbent is None or token_preference_key(token) < token_preference_key(incumbent):
                best_by_lower[lowered] = token
        self._by_lower: Dict[str, int] = {
            lowered: token.id for lowered, token in best_by_lower.items()
        }

    @classmethod
    def for_language(cls, session: Session, language_code: str) -> "WordTokenResolver":
        """A resolver over every token in one language (for bulk linking)."""
        return cls(session.query(WordToken).filter(WordToken.language_code == language_code).all())

    @classmethod
    def for_text(cls, session: Session, text: str, language_code: str) -> "WordTokenResolver":
        """A resolver over just the case variants of one text (for linking one form)."""
        return cls(
            session.query(WordToken)
            .filter(
                WordToken.language_code == language_code,
                func.lower(WordToken.token) == text.lower(),
            )
            .all()
        )

    def __bool__(self) -> bool:
        return bool(self._by_exact)

    def resolve(self, text: str, exact_case_only: bool = False) -> Optional[int]:
        """The best token id for one surface text, or None."""
        if not text:
            return None
        exact = self._by_exact.get(text)
        if exact is not None or exact_case_only:
            return exact
        return self._by_lower.get(text.lower())


def source_for_form(form: Any) -> TokenFormSource:
    """The TOKEN_FORM_SOURCES entry a form row belongs to."""
    for source in TOKEN_FORM_SOURCES:
        if isinstance(form, source.model):
            return source
    raise TypeError(f"{type(form).__name__} is not a registered token form table")


def link_form_to_word_token(session: Session, form: Any) -> bool:
    """Set one form row's ``word_token_id`` now, when a matching token exists.

    For creation paths, so a new form claims its token without waiting for the
    next bulk :func:`link_unlinked_forms` run. Uses the same matching rule.
    Returns whether the row was linked. Does not commit.
    """
    if form.word_token_id is not None:
        return False
    source = source_for_form(form)
    resolver = WordTokenResolver.for_text(session, form.surface_text, form.language_code)
    token_id = resolver.resolve(form.surface_text, source.exact_case_only)
    if token_id is None:
        return False
    form.word_token_id = token_id
    return True


def link_unlinked_forms(session: Session, language_code: str) -> Dict[str, int]:
    """Set ``word_token_id`` on every unlinked form row in one language.

    Only rows whose FK is NULL are touched, so this is idempotent. Does not
    commit. Returns ``{table_name: rows linked}`` for each source.
    """
    counts: Dict[str, int] = {source.table_name: 0 for source in TOKEN_FORM_SOURCES}
    resolver = WordTokenResolver.for_language(session, language_code)
    if not resolver:
        return counts

    for source in TOKEN_FORM_SOURCES:
        rows = (
            session.query(source.model)
            .filter(
                source.model.language_code == language_code,
                source.model.word_token_id.is_(None),
            )
            .all()
        )
        for row in rows:
            token_id = resolver.resolve(row.surface_text or "", source.exact_case_only)
            if token_id is not None:
                row.word_token_id = token_id
                counts[source.table_name] += 1
    return counts


__all__ = [
    "ATTACHMENT_DERIVATIVE",
    "ATTACHMENT_NAME",
    "ATTACHMENT_VARIANT",
    "TOKEN_FORM_SOURCES",
    "TokenFormSource",
    "WordTokenResolver",
    "claimed_word_token_ids",
    "link_form_to_word_token",
    "link_unlinked_forms",
    "source_for_form",
    "token_preference_key",
]
