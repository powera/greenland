#!/usr/bin/python3

"""Selecting learnable vocabulary out of the corpus frequency data.

The corpus-skew and exclusive-word scores in
:mod:`wordfreq.frequency.corpus_skew` answer a measurement question -- which
words lean toward one corpus -- and answer it about every token in the
database, function words and markup fragments included.  Turning one of those
rankings into a wordlist someone would actually study takes a second pass, and
that pass had been done by hand each time: pull a few hundred rows out of the
barsukas page, delete the ones that are obviously not vocabulary, paste the
rest into a script as a literal tuple.

Doing it by hand made each list unreproducible.  The tuple in a generated
import script records *what* was chosen but not *why*, so a list could not be
regenerated after the corpora changed, and the same judgements ("drop the
function words", "drop the capitalized residue") were re-applied slightly
differently every time.

The three entry points here are that pass, written down:

* :func:`filter_function_words` -- drop the closed-class words.
* :func:`high_skew_words` -- the corpus-characteristic vocabulary, filtered.
* :func:`corpus_exclusive_words` -- the corpus-*only* vocabulary, filtered.

The two selectors wrap :func:`~wordfreq.frequency.corpus_skew.score_corpus_skew`
and :func:`~wordfreq.frequency.corpus_skew.exclusive_words` respectively;
neither reimplements a score.  What they add is the cleanup every caller was
doing anyway, in one place with one set of defaults.

Cleanup is deliberately conservative.  Anything it removes is something a
frequency count cannot represent as a word at all -- a closed-class item, a
capitalized proper-noun residue, a markup fragment -- and never a judgement
about whether a real word is worth learning.  That judgement belongs to
whoever reads the list.
"""

from typing import Iterable, List, Optional, Sequence, Set, TypeVar

from sqlalchemy.orm import Session

from langtools.grammatical_words import GRAMMATICAL_WORDS_BY_LANGUAGE, is_function_word
from wordfreq.frequency.corpus_skew import (
    ExclusiveWord,
    SkewedWord,
    exclusive_words,
    score_corpus_skew,
)

# Tokens shorter than this are almost always initials, list markers or
# tokenizer debris rather than words.  "ox" and "id" are three letters short of
# interesting; the loss is real but small, and the noise removed is large.
MIN_TOKEN_LENGTH: int = 3

_T = TypeVar("_T", SkewedWord, ExclusiveWord)


def is_probable_proper_noun(token: str) -> bool:
    """Whether a token looks like proper-noun residue.

    The corpus builder separates proper nouns per document, but a word that is
    capitalized in most of its occurrences still reaches the frequency data
    capitalized -- "River", "Empire", "Shakespeare".  A skew score cannot tell
    those from common nouns, because being characteristic of one corpus is
    exactly what a proper noun is.

    This is a heuristic on the stored surface form, not a claim about the word:
    a sentence-initial "The" would look the same.  It holds up here because the
    corpus stores one lowercased entry per token, so a capital that survived is
    evidence the word is *usually* capitalized.
    """
    return bool(token) and token[0].isupper()


def is_probable_fragment(token: str) -> bool:
    """Whether a token is markup or URL debris rather than a word.

    Wiki markup ("sup", "ref"), URL pieces ("com", "www") and stray Latin
    ("et", "al", "de") all reach the frequency data as ordinary tokens.  Only
    the structural cases are caught here -- anything with a digit, an
    underscore or no vowel -- because a list of known-bad words would go stale
    against the next corpus.
    """
    if any(character.isdigit() or character == "_" for character in token):
        return True
    return not any(character in "aeiouy" for character in token.lower())


def filter_function_words(
    tokens: Iterable[str], language_code: str = "en", keep_unknown_language: bool = True
) -> List[str]:
    """Drop the closed-class words from ``tokens``.

    Function words dominate any raw frequency ranking and teach nothing: a
    learner meets "the", "of" and "which" in their first week, and a list of
    them is not a lesson.  The closed-class inventory is
    :mod:`langtools.grammatical_words`, which is per-language and already
    registered for the eleven languages that have a grammar module -- this does
    not define a stoplist of its own.

    All four tiers are checked (personal pronouns, grammatical words,
    conjunctions and prepositions, non-personal pronouns), which is the broad
    sense of "function word": everything that is grammar rather than content.

    Args:
        tokens: Surface forms to filter.
        language_code: Which language's inventory to check against.
        keep_unknown_language: What to do when no grammar module is registered
            for ``language_code``.  ``is_function_word`` returns False for
            every word in that case, so the default keeps the list whole rather
            than silently filtering nothing and implying it filtered.  Pass
            False to treat an unregistered language as an error instead.

    Returns:
        The tokens that are not function words, in the order given.

    Raises:
        ValueError: If ``keep_unknown_language`` is False and no inventory is
            registered for ``language_code``.
    """
    materialized = list(tokens)
    if not _language_is_registered(language_code):
        if keep_unknown_language:
            return materialized
        raise ValueError(
            f"no grammatical-word inventory registered for {language_code!r}; "
            "pass keep_unknown_language=True to skip filtering instead"
        )
    return [token for token in materialized if not is_function_word(token, language_code)]


def _language_is_registered(language_code: str) -> bool:
    """Whether :mod:`langtools.grammatical_words` has an inventory for this language.

    ``GRAMMATICAL_WORDS_BY_LANGUAGE`` is the public registry of all four tiers
    and raises :class:`KeyError` for a language with no grammar module, which
    is the distinction wanted here: ``is_function_word`` cannot express it,
    since it returns False both for an ordinary word and for every word of an
    unregistered language.
    """
    try:
        GRAMMATICAL_WORDS_BY_LANGUAGE[language_code]
    except KeyError:
        return False
    return True


def _clean(
    words: Sequence[_T],
    language_code: str,
    drop_function_words: bool,
    drop_proper_nouns: bool,
    drop_fragments: bool,
    min_length: int,
    limit: Optional[int],
) -> List[_T]:
    """Apply the shared cleanup to a scored ranking, preserving its order."""
    kept: List[_T] = []
    function_words: Optional[Set[str]] = None
    if drop_function_words:
        tokens = [word.token for word in words]
        function_words = set(tokens) - set(filter_function_words(tokens, language_code))

    for word in words:
        token = word.token
        if len(token) < min_length:
            continue
        if drop_fragments and is_probable_fragment(token):
            continue
        if drop_proper_nouns and is_probable_proper_noun(token):
            continue
        if function_words is not None and token in function_words:
            continue
        kept.append(word)
        if limit is not None and len(kept) >= limit:
            break
    return kept


def high_skew_words(
    session: Session,
    corpus_name: str,
    language_code: str = "en",
    comparison_corpora: Optional[Sequence[str]] = None,
    min_score: Optional[float] = None,
    min_other_corpora: int = 1,
    drop_function_words: bool = True,
    drop_proper_nouns: bool = True,
    drop_fragments: bool = True,
    min_length: int = MIN_TOKEN_LENGTH,
    limit: Optional[int] = None,
) -> List[SkewedWord]:
    """The vocabulary most characteristic of ``corpus_name``, cleaned up.

    Wraps :func:`~wordfreq.frequency.corpus_skew.score_corpus_skew`: the score
    and the ordering are entirely that function's, and this adds only the
    filtering a caller would otherwise do by hand.  ``limit`` counts words
    *kept*, so asking for 200 returns 200 usable words rather than 200 rows of
    which some are "the".

    Args:
        session: Open session.
        corpus_name: The corpus to characterize.
        language_code: Token language, and the function-word inventory used.
        comparison_corpora: What to compare against; defaults to every other
            enabled corpus.
        min_score: Drop words scoring below this Zipf delta.  +1.0 means "ten
            times as common here as elsewhere"; None keeps everything scored.
        min_other_corpora: Passed through -- how many other corpora must
            attest a word before its delta is trusted.
        drop_function_words: Remove closed-class words.
        drop_proper_nouns: Remove capitalized proper-noun residue.
        drop_fragments: Remove markup and URL debris.
        min_length: Drop tokens shorter than this.
        limit: Return at most this many *kept* words.

    Returns:
        Scored words, most characteristic first.
    """
    scored = score_corpus_skew(
        session,
        corpus_name,
        language_code=language_code,
        comparison_corpora=comparison_corpora,
        min_other_corpora=min_other_corpora,
        limit=None,
    )
    if min_score is not None:
        scored = [word for word in scored if word.score >= min_score]
    return _clean(
        scored,
        language_code,
        drop_function_words,
        drop_proper_nouns,
        drop_fragments,
        min_length,
        limit,
    )


def corpus_exclusive_words(
    session: Session,
    corpus_name: str,
    language_code: str = "en",
    comparison_corpora: Optional[Sequence[str]] = None,
    max_rank: Optional[int] = None,
    drop_function_words: bool = True,
    drop_proper_nouns: bool = True,
    drop_fragments: bool = True,
    min_length: int = MIN_TOKEN_LENGTH,
    limit: Optional[int] = None,
) -> List[ExclusiveWord]:
    """Words ``corpus_name`` attests and no comparison corpus does, cleaned up.

    Wraps :func:`~wordfreq.frequency.corpus_skew.exclusive_words`.  Being
    unattested anywhere else is a stronger claim about a word's domain than
    merely being commoner in one place, so these lists are sharper than
    :func:`high_skew_words` -- "subspecies" and "habeas" rather than
    "reasonably" and "discretion".

    The same cleanup applies, and matters more here: a word exclusive to one
    corpus is disproportionately likely to be a proper noun or a fragment,
    since those are exactly the tokens no other corpus would contain.

    Args:
        session: Open session.
        corpus_name: The corpus to take exclusive vocabulary from.
        language_code: Token language, and the function-word inventory used.
        comparison_corpora: What must *not* attest the word; defaults to every
            other enabled corpus.
        max_rank: Keep only words ranking this high or better within the
            corpus.  Exclusive words run deep into the tail, where a word is
            attested a handful of times and may be a typo.
        drop_function_words: Remove closed-class words.
        drop_proper_nouns: Remove capitalized proper-noun residue.
        drop_fragments: Remove markup and URL debris.
        min_length: Drop tokens shorter than this.
        limit: Return at most this many *kept* words.

    Returns:
        Exclusive words, best-ranked within the corpus first.
    """
    found = exclusive_words(
        session,
        corpus_name,
        language_code=language_code,
        comparison_corpora=comparison_corpora,
        limit=None,
    )
    if max_rank is not None:
        found = [
            word
            for word in found
            if word.ordinal_rank is not None and word.ordinal_rank <= max_rank
        ]
    return _clean(
        found,
        language_code,
        drop_function_words,
        drop_proper_nouns,
        drop_fragments,
        min_length,
        limit,
    )
