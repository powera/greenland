"""Vocabulary coverage for generated dialogs: what do we already have?

Every token of a generated dialog is one of four things, and the whole
Barsukas-first flow hangs on telling them apart:

* a **grammatical word** ("the", "is") -- never a release lemma, ignored;
* a **known lemma** ("tomato") -- already vocabulary, and its difficulty level
  is what the sentence's ``minimum_level`` is computed from;
* a **name** ("George") -- a :class:`~storage.models.name_entity.Name`, not
  vocabulary, and deliberately excluded from the difficulty rollup;
* a **missing word** ("cashier") -- a real word we simply do not have yet, and
  the reason this module exists. These are what the reviewer stages as pending
  imports.

The fourth bucket is expected to be large at first and to shrink as the
dictionary fills in, which is why coverage is reported rather than enforced: a
dialog is not rejected for using a word we lack.

Difficulty note: a known lemma *above* the target level is not a defect either,
it is information. A handful of harder words is the expected shape of a natural
dialog, so the level is the 85th percentile of the vocabulary used rather than
its maximum -- see :func:`dialog_difficulty_level`.
"""

import logging
import math
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Sequence, Set

from sqlalchemy.orm import Session

from langtools.en.utils import candidate_base_forms
from langtools.grammatical_words import is_function_word, is_grammatical_word
from langtools.tokenizer import tokenize
from sentences.candidate_lookup import find_lemmas_for_token
from storage.crud.name_entity import find_name
from storage.models.name_entity import normalize_name_text
from storage.models.schema import Lemma

logger = logging.getLogger(__name__)

# Token classifications, in the order the review page groups them.
STATUS_KNOWN: str = "known"
STATUS_ABOVE_LEVEL: str = "above_level"
STATUS_NAME: str = "name"
STATUS_GRAMMATICAL: str = "grammatical"
STATUS_MISSING: str = "missing"

STATUS_LABELS: Dict[str, str] = {
    STATUS_KNOWN: "Known at level",
    STATUS_ABOVE_LEVEL: "Known, above level",
    STATUS_NAME: "Name",
    STATUS_GRAMMATICAL: "Grammatical",
    STATUS_MISSING: "Missing",
}

# part_of_speech values stored on SentenceWord for tokens that resolve to
# something other than a lemma. The column is free-form text, so these sit
# alongside the usual "noun"/"verb" values that come from a matched lemma.
POS_NAME: str = "name"
POS_GRAMMATICAL: str = "grammatical"
POS_UNKNOWN: str = "unknown"

# Share of a dialog's vocabulary that its computed level must cover. The top
# ~15% is allowed to sit above it: some words being harder (or missing entirely)
# is the expected shape of a natural dialog, not a generation defect.
DIFFICULTY_PERCENTILE: float = 0.85

# Characters stripped from token edges before classification. Kept in sync with
# the sentence tokenizer's expectations rather than re-tokenizing per status.
_PUNCTUATION_STRIP = ".,!?;:\"'()[]{}—-…"


@dataclass
class TokenCoverage:
    """One distinct token of a dialog and what we know about it."""

    surface: str
    status: str
    lemma_id: Optional[int] = None
    lemma_text: Optional[str] = None
    difficulty_level: Optional[int] = None
    name_id: Optional[int] = None
    # Line indices (into the dialog's turns) where this token appears.
    line_indices: List[int] = field(default_factory=list)
    # The first line it appears in, verbatim -- the example sentence a staged
    # pending import carries so the disambiguation step has context.
    example_line: Optional[str] = None

    @property
    def is_missing(self) -> bool:
        """True when this token is a word we do not have yet."""
        return self.status == STATUS_MISSING

    @property
    def status_label(self) -> str:
        """Human-readable label for the status."""
        return STATUS_LABELS.get(self.status, self.status)


@dataclass
class CoverageReport:
    """Coverage of one dialog against a target difficulty level."""

    target_level: int
    tokens: List[TokenCoverage] = field(default_factory=list)
    # Difficulty of the known lemmas used, at DIFFICULTY_PERCENTILE and floored
    # at target_level; None when the dialog uses no leveled vocabulary at all.
    # See dialog_difficulty_level.
    computed_minimum_level: Optional[int] = None

    def by_status(self, status: str) -> List[TokenCoverage]:
        """Tokens with one status, in first-appearance order."""
        return [token for token in self.tokens if token.status == status]

    @property
    def missing(self) -> List[TokenCoverage]:
        """Tokens that are words we do not have yet."""
        return self.by_status(STATUS_MISSING)

    @property
    def above_level(self) -> List[TokenCoverage]:
        """Known tokens whose difficulty exceeds the target level."""
        return self.by_status(STATUS_ABOVE_LEVEL)

    @property
    def names(self) -> List[TokenCoverage]:
        """Tokens resolved to registered names."""
        return self.by_status(STATUS_NAME)

    @property
    def counts(self) -> Dict[str, int]:
        """Token count per status, including statuses with no tokens."""
        counts = {status: 0 for status in STATUS_LABELS}
        for token in self.tokens:
            counts[token.status] = counts.get(token.status, 0) + 1
        return counts

    @property
    def vocabulary_token_count(self) -> int:
        """Tokens that are vocabulary candidates (everything but grammatical)."""
        return sum(1 for token in self.tokens if token.status != STATUS_GRAMMATICAL)

    @property
    def known_ratio(self) -> float:
        """Share of vocabulary tokens we already have, names included.

        Returns 1.0 for a dialog with no vocabulary tokens at all, which only
        happens for a dialog made entirely of function words.
        """
        total = self.vocabulary_token_count
        if total == 0:
            return 1.0
        covered = sum(
            1
            for token in self.tokens
            if token.status in (STATUS_KNOWN, STATUS_ABOVE_LEVEL, STATUS_NAME)
        )
        return covered / total


def dialog_difficulty_level(
    levels: Sequence[int],
    *,
    target_level: Optional[int] = None,
    percentile: float = DIFFICULTY_PERCENTILE,
) -> Optional[int]:
    """The difficulty level to assign a dialog that used ``levels``.

    Taking the maximum makes one rare word define the whole dialog, which is the
    wrong reading: a dialog is written *at* a level and is expected to reach past
    it occasionally. So the level is the 85th percentile of the levels used
    (nearest-rank, so the result is always a level some word actually has),
    floored at the level that was asked for.

    The floor is deliberate and one-directional. A dialog written for level 5
    that happens to use easy words is still level-5 material -- it was written
    for that learner. But a dialog whose vocabulary is *entirely* below the
    target is described by its words, not by the request, so the floor lifts and
    the percentile stands on its own.

    Args:
        levels: Difficulty levels of the vocabulary used, one entry per distinct
            word. Order does not matter; duplicates weight that level.
        target_level: Level the dialog was requested at, used as a floor. None
            (or an unleveled request) means no floor.
        percentile: Fraction in [0, 1]; the default is the project's 85th.

    Returns:
        The computed level, or None when no word carried a level at all.
    """
    if not levels:
        return None

    ordered = sorted(levels)
    # Nearest-rank: the smallest stored level at or above the percentile cut.
    rank = math.ceil(percentile * len(ordered))
    computed = ordered[max(0, min(rank, len(ordered)) - 1)]

    if target_level is None:
        return computed
    # Floor at the request -- unless every word used is below it, in which case
    # the dialog really is easier than it was asked to be.
    if ordered[-1] < target_level:
        return computed
    return max(computed, target_level)


def normalize_surface_token(token: str) -> str:
    """Strip edge punctuation; preserve case (names are case-significant)."""
    return token.strip(_PUNCTUATION_STRIP).strip()


def _pick_best_lemma(lemmas: Sequence[Lemma]) -> Lemma:
    """Choose which lemma a surface token counts as.

    Prefers the lowest difficulty level among the matches: when a token matches
    both an everyday sense and a rare one, the dialog almost certainly meant the
    everyday one, and treating it as the rare one would inflate the dialog's
    computed level. Unleveled lemmas sort last.
    """
    return min(
        lemmas,
        key=lambda lemma: (
            lemma.difficulty_level is None,
            lemma.difficulty_level if lemma.difficulty_level is not None else 0,
            lemma.id,
        ),
    )


def classify_token(
    session: Session,
    surface: str,
    *,
    target_level: int,
    language_code: str = "en",
    cast_names: Optional[Set[str]] = None,
) -> TokenCoverage:
    """Classify one surface token against the database.

    Names are checked before lemmas so a name that shares its spelling with a
    word ("Mark", "Rose") is not silently swallowed by the dictionary. Only
    capitalized tokens are name candidates, so "rose" the flower still resolves
    to its lemma.

    Args:
        session: Database session.
        surface: The token as it appeared, punctuation already acceptable.
        target_level: Level the dialog was written for.
        language_code: Language of the token.
        cast_names: Names the generator reported for this dialog. A token
            matching one counts as a name even before the Name row exists.

    Returns:
        The token's coverage entry (line indices are filled in by the caller).
    """
    cleaned = normalize_surface_token(surface)
    if not cleaned:
        return TokenCoverage(surface=surface, status=STATUS_GRAMMATICAL)

    if not any(char.isalpha() for char in cleaned):
        # Numerals and stray symbols are never dictionary entries.
        return TokenCoverage(surface=cleaned, status=STATUS_GRAMMATICAL)

    if is_grammatical_word(cleaned, language_code):
        return TokenCoverage(surface=cleaned, status=STATUS_GRAMMATICAL)

    looks_like_name = cleaned[:1].isupper()
    if looks_like_name:
        normalized_name = normalize_name_text(cleaned)
        if cast_names and normalized_name in cast_names:
            existing = find_name(session, normalized_name)
            return TokenCoverage(
                surface=cleaned,
                status=STATUS_NAME,
                name_id=existing.id if existing is not None else None,
            )
        registered = find_name(session, normalized_name)
        if registered is not None:
            return TokenCoverage(surface=cleaned, status=STATUS_NAME, name_id=registered.id)

    lemma = _resolve_lemma(session, cleaned, language_code)
    if lemma is not None:
        level = lemma.difficulty_level
        status = STATUS_ABOVE_LEVEL if level is not None and level > target_level else STATUS_KNOWN
        return TokenCoverage(
            surface=cleaned,
            status=status,
            lemma_id=lemma.id,
            lemma_text=lemma.lemma_text,
            difficulty_level=level,
        )

    # Conjunctions, prepositions, and demonstratives (tiers 3-4) are supposed to
    # be lemmas, but one that is not in the database yet is a gap in the
    # function-word data, not a vocabulary word to stage for import. Reporting
    # "of" as a missing dictionary word would only bury the real gaps.
    if is_function_word(cleaned, language_code):
        return TokenCoverage(surface=cleaned, status=STATUS_GRAMMATICAL)

    return TokenCoverage(surface=cleaned, status=STATUS_MISSING)


def _resolve_lemma(session: Session, token: str, language_code: str) -> Optional[Lemma]:
    """Find the lemma behind a surface token, falling back to de-inflection.

    Inflected forms normally resolve through stored ``DerivativeForm`` rows.
    When a lemma's forms have not been generated yet, regular English
    morphology is undone here so "tomatoes" still finds "tomato" instead of
    being reported as a word we do not have.

    Returns:
        The matching lemma, or None.
    """
    matches = find_lemmas_for_token(session, language_code, token)
    if matches:
        return _pick_best_lemma(matches)

    if language_code != "en":
        return None

    for base_form in candidate_base_forms(token):
        matches = find_lemmas_for_token(session, language_code, base_form)
        if matches:
            return _pick_best_lemma(matches)

    return None


def _coverage_key(cleaned_token: str, cast_names: Set[str]) -> str:
    """Cache/dedupe key for a token.

    Case-sensitive for name candidates, case-folded otherwise, so "George" and
    "george" stay separate entries while "Tomatoes" and "tomatoes" merge.
    """
    if cleaned_token[:1].isupper() and cleaned_token in cast_names:
        return cleaned_token
    return cleaned_token.lower()


def _surface_rank(surface: str) -> tuple[int, str]:
    """Sort key preferring an uncapitalized spelling of the same word."""
    return (1 if surface[:1].isupper() else 0, surface)


def classify_line_tokens(
    session: Session,
    line: str,
    *,
    target_level: int,
    language_code: str = "en",
    cast_names: Optional[Set[str]] = None,
    cache: Optional[Dict[str, TokenCoverage]] = None,
) -> List[TokenCoverage]:
    """Classify a line's tokens in order, keeping repeats.

    This is the positional view coverage is built from, and it is what the
    storage side needs: one ``SentenceWord`` row per token, in the order the
    tokens appear. :func:`analyze_lines` folds the repeats away for display.

    Args:
        session: Database session.
        line: One line of dialog.
        target_level: Level the dialog was written for.
        language_code: Language the line is written in.
        cast_names: Already-normalized names the generator reported.
        cache: Optional cross-line classification cache; supply the same dict
            for every line of a dialog to avoid re-querying repeated tokens.

    Returns:
        One entry per token, in order. Entries are copies, so callers may
        annotate them per position without affecting the cache.
    """
    normalized_cast = cast_names or set()
    shared_cache = cache if cache is not None else {}
    out: List[TokenCoverage] = []

    for raw_token in tokenize(line, language_code):
        cleaned = normalize_surface_token(raw_token)
        if not cleaned:
            continue
        key = _coverage_key(cleaned, normalized_cast)
        entry = shared_cache.get(key)
        if entry is None:
            entry = classify_token(
                session,
                cleaned,
                target_level=target_level,
                language_code=language_code,
                cast_names=normalized_cast,
            )
            shared_cache[key] = entry
        # surface comes from *this* occurrence, never the cached one. The cache
        # key folds case for non-cast words, so "My" and "my" share an entry;
        # keeping the cached surface would stamp whichever spelling was seen
        # first onto every later one, and a sentence-initial capital would leak
        # into mid-sentence positions (and into SentenceWord.english_text).
        out.append(replace(entry, surface=cleaned, line_indices=[], example_line=None))

    return out


def analyze_lines(
    session: Session,
    lines: Sequence[str],
    *,
    target_level: int,
    language_code: str = "en",
    cast_names: Optional[Sequence[str]] = None,
) -> CoverageReport:
    """Classify every distinct token across a dialog's lines.

    Tokens are de-duplicated case-insensitively except for name candidates,
    which keep their case so "Mark" and "mark" stay separate entries.

    Args:
        session: Database session.
        lines: The dialog's spoken lines, in order.
        target_level: Level the dialog was written for.
        language_code: Language the lines are written in.
        cast_names: Names the generator reported for this dialog.

    Returns:
        The coverage report, tokens in first-appearance order.
    """
    normalized_cast = {normalize_name_text(name) for name in (cast_names or []) if name.strip()}

    cache: Dict[str, TokenCoverage] = {}
    tokens_by_key: Dict[str, TokenCoverage] = {}
    ordered_keys: List[str] = []

    for line_index, line in enumerate(lines):
        for token in classify_line_tokens(
            session,
            line,
            target_level=target_level,
            language_code=language_code,
            cast_names=normalized_cast,
            cache=cache,
        ):
            key = _coverage_key(token.surface, normalized_cast)
            entry = tokens_by_key.get(key)
            if entry is None:
                entry = token
                entry.example_line = line
                tokens_by_key[key] = entry
                ordered_keys.append(key)
            elif entry.surface != token.surface and entry.status != STATUS_NAME:
                # Same word, different case across lines ("My" at the start of
                # one line, "my" inside another). The report drives pending
                # imports, so prefer the lowercase spelling -- staging a word
                # under its sentence-initial capital would import "My".
                entry.surface = min(entry.surface, token.surface, key=_surface_rank)
            if line_index not in entry.line_indices:
                entry.line_indices.append(line_index)

    tokens = [tokens_by_key[key] for key in ordered_keys]
    levels = [
        token.difficulty_level
        for token in tokens
        if token.difficulty_level is not None and token.status in (STATUS_KNOWN, STATUS_ABOVE_LEVEL)
    ]
    return CoverageReport(
        target_level=target_level,
        tokens=tokens,
        computed_minimum_level=dialog_difficulty_level(levels, target_level=target_level),
    )


def part_of_speech_for(token: TokenCoverage, lemma_pos: Optional[str] = None) -> str:
    """Return the ``SentenceWord.part_of_speech`` value for a classified token.

    A token that matched a lemma keeps that lemma's part of speech; everything
    else records *why* it has no lemma, which is what makes an unresolved word
    distinguishable from a name later.
    """
    if token.status == STATUS_NAME:
        return POS_NAME
    if token.status == STATUS_GRAMMATICAL:
        return POS_GRAMMATICAL
    if token.status == STATUS_MISSING:
        return POS_UNKNOWN
    return lemma_pos or POS_UNKNOWN


def analyze_line(
    session: Session,
    line: str,
    *,
    target_level: int,
    language_code: str = "en",
    cast_names: Optional[Sequence[str]] = None,
) -> CoverageReport:
    """Coverage for a single line; see :func:`analyze_lines`."""
    return analyze_lines(
        session,
        [line],
        target_level=target_level,
        language_code=language_code,
        cast_names=cast_names,
    )
