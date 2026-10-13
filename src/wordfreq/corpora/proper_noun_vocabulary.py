"""Capitalized words the corpus build should keep as ordinary vocabulary.

The corpus builder classifies a word as a proper noun, per book, when its
mid-sentence occurrences are almost always capitalized, and drops it (see
:mod:`wordfreq.corpora.frequency_build`).  That is right for Heathcliff and
wrong for Saturday: a learner needs the days of the week and the months, and
they are exactly the words the capitalization test eats.

``BookList.always_vocabulary`` is the existing escape hatch -- a per-corpus
tuple fed to ``detect_names`` as ``extra_never_names``.  It was maintained by
hand, which is why only ``religious_translated`` had one.  This module derives
the list from the database instead, so a name that is already a dictionary
headword is kept automatically and the two cannot drift apart.

It reads the database rather than the ``data/release`` export, because a corpus
rebuild usually follows new lemmas and the release lags the database until
someone exports it.  The session comes from the caller, so a build pointed at
a release tree (``--backend jsonl --data-dir data/release``) still reads that.

Read-only: this never writes to the database.

**Which categories are safe.**  Not every proper noun in the database can
be whitelisted, because a whitelist is keyed on a *lowercased surface string*
and the corpora cannot tell senses apart:

* Days, months and holidays are wanted, and most are unambiguous.
* Cities and countries are wanted and are nearly all unambiguous.
* "March", "May" and "August" are the exception in both groups: as ordinary
  English they are a verb, a modal and an adjective, and they are far more
  common in that reading than as the month.  Whitelisting them does not
  recover the month's frequency, it hands the month the *common word's*
  frequency -- "may" ranks 40-67 across these corpora on the strength of the
  modal alone.  They are held back by :data:`AMBIGUOUS_WITH_COMMON_WORDS`.

See :func:`load_always_vocabulary` for what a caller gets.
"""

from __future__ import annotations

from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from storage.models.schema import DerivativeForm, Lemma

# Noun subtypes holding capitalized entries that are legitimate vocabulary. ``place_name`` is deliberately absent: despite the
# name it holds common nouns (area, city, north), which are never capitalized
# and so are never filtered in the first place.
VOCABULARY_NAME_SUBTYPES: Tuple[str, ...] = (
    "temporal_name",
    "city",
    "region",
    "geographic_place",
)

# Surface strings that are a common English word as often as (or more often
# than) they are the name, and so must not be whitelisted. The corpus counts a
# lowercased string, so whitelisting "may" would credit the month with every
# use of the modal verb.
AMBIGUOUS_WITH_COMMON_WORDS: FrozenSet[str] = frozenset(
    {
        "march",  # to march; the Marches
        "may",  # the modal verb
        "august",  # august = venerable
        "turkey",  # the bird
        "china",  # porcelain
        "frank",  # candid
        "reading",  # the town vs. the gerund
        "nice",  # the city vs. the adjective
        "mobile",  # the city vs. the adjective
    }
)


def _read_subtype_forms(session: Session, subtype: str) -> List[str]:
    """Return every English surface form for one noun subtype.

    Both the headword and its English ``DerivativeForm`` rows are read, because
    the filter matches surface strings and a name may inflect ("Alps" alongside
    "Alp"), while a lemma need not have any forms at all.
    """
    headwords = [
        lemma_text
        for (lemma_text,) in session.query(Lemma.lemma_text).filter(
            Lemma.pos_type == "noun", Lemma.pos_subtype == subtype
        )
    ]
    forms = [
        form_text
        for (form_text,) in session.query(DerivativeForm.derivative_form_text)
        .join(Lemma, DerivativeForm.lemma_id == Lemma.id)
        .filter(
            Lemma.pos_type == "noun",
            Lemma.pos_subtype == subtype,
            DerivativeForm.language_code == "en",
        )
    ]
    return [text for text in headwords + forms if text]


def _normalize_entry(text: str) -> Optional[str]:
    """Lowercase one database name, or None if it must not be whitelisted.

    A multi-word name is kept **whole** ("new york", not "new" + "york"). It
    must therefore be matched by a tokenizer that emits multi-word tokens; see
    :mod:`wordfreq.corpora.gutenberg_text`. Splitting it into words instead
    would whitelist "new", "year", "day", "states" and "sea" as never-names,
    which is far worse than leaving the name filtered: those are ordinary
    English words, and the entry is supposed to protect a name, not blanket
    every word it happens to contain.

    A single-word name must be capitalized to be worth protecting; an entry
    that is already lowercase is never filtered as a name in the first place.
    """
    stripped = text.strip()
    if not stripped:
        return None
    if " " in stripped:
        # Multi-word: keep whole, provided at least one word is capitalized.
        if not any(part[:1].isupper() for part in stripped.split()):
            return None
        return stripped.lower()
    if not stripped[:1].isupper():
        return None
    return stripped.lower()


def load_always_vocabulary(
    session: Session,
    subtypes: Sequence[str] = VOCABULARY_NAME_SUBTYPES,
    exclude: FrozenSet[str] = AMBIGUOUS_WITH_COMMON_WORDS,
) -> Tuple[str, ...]:
    """Capitalized words from the database to keep as ordinary vocabulary.

    Suitable for ``BookList.always_vocabulary`` / ``detect_names``'s
    ``extra_never_names``, both of which lowercase what they receive.

    Args:
        session: Open session on the database (or release tree) to read.
        subtypes: Noun subtypes to read. Defaults to the capitalized-vocabulary
            ones; ``place_name`` is excluded by default as it holds common nouns.
        exclude: Lowercased surface strings to hold back, whatever the database
            says. Defaults to the words that collide with common English.

    Returns:
        Lowercased words, sorted and deduplicated.
    """
    words: set[str] = set()
    for subtype in subtypes:
        for text in _read_subtype_forms(session, subtype):
            lowered = _normalize_entry(text)
            if lowered is None or lowered in exclude:
                continue
            words.add(lowered)

    return tuple(sorted(words))


def load_always_vocabulary_by_subtype(
    session: Session,
    subtypes: Sequence[str] = VOCABULARY_NAME_SUBTYPES,
    exclude: FrozenSet[str] = AMBIGUOUS_WITH_COMMON_WORDS,
) -> Dict[str, Tuple[str, ...]]:
    """Same as :func:`load_always_vocabulary`, kept per subtype.

    Useful for reporting which categories a corpus rebuild would newly protect,
    and for whitelisting only some categories in a given corpus.
    """
    out: Dict[str, Tuple[str, ...]] = {}
    for subtype in subtypes:
        words: set[str] = set()
        for text in _read_subtype_forms(session, subtype):
            lowered = _normalize_entry(text)
            if lowered is None or lowered in exclude:
                continue
            words.add(lowered)
        out[subtype] = tuple(sorted(words))
    return out


def excluded_words(
    session: Session,
    subtypes: Sequence[str] = VOCABULARY_NAME_SUBTYPES,
    exclude: FrozenSet[str] = AMBIGUOUS_WITH_COMMON_WORDS,
) -> Tuple[str, ...]:
    """Database words held back by ``exclude``, for reporting.

    Lets a caller show *which* names were withheld as too ambiguous, rather
    than leaving their absence unexplained.
    """
    held: set[str] = set()
    for subtype in subtypes:
        for text in _read_subtype_forms(session, subtype):
            lowered = _normalize_entry(text)
            if lowered is not None and lowered in exclude:
                held.add(lowered)
    return tuple(sorted(held))


__all__ = [
    "AMBIGUOUS_WITH_COMMON_WORDS",
    "VOCABULARY_NAME_SUBTYPES",
    "excluded_words",
    "load_always_vocabulary",
    "load_always_vocabulary_by_subtype",
]
