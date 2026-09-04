"""Multi-word lemma forms the corpus tokenizer should count as single tokens.

"ice cream" is one word for frequency purposes.  Counting it as "ice" plus
"cream" both loses the compound and inflates its parts, which is why the
tokenizer takes a phrase index (see
:func:`wordfreq.corpora.gutenberg_text.build_phrase_index`).  This module
decides *which* multi-word forms belong in that index, reading them from the
database's own ``DerivativeForm`` rows.

**Periphrastic inflection is the second, larger category.**  Of the ~2400
multi-word English forms in this database, all but ~90 are grammatical rather
than lexical:

* every verb's future is stored as ``will <verb>`` -- 1986 rows, all six
  person/number slots of 331 verbs;
* every long adjective's and adverb's comparative and superlative is stored as
  ``more <word>`` / ``most <word>`` -- another 344.

``include_periphrastic`` controls whether those are joined, and defaults to
**True**: "will want" is a form of "want" and counting it as such is what the
database already asserts by storing it.  The tradeoff is real either way:

*For joining* (the default).  It is the only way the corpus measures a
periphrastic tense at all, and the auxiliary reading of "will" is not the same
word as the noun ("last will and testament") -- leaving every future tense
merged into that one token is its own distortion, and a large one.

*Against joining.*  A phrase index matches only *adjacent* words, so "will
never walk", "will you walk" and "more than usually careful" all miss; the
joined counts are therefore a subset of real periphrastic use rather than a
measurement of it.  Joining also moves those occurrences out of "will", "more"
and "most" themselves.

Note that joining does **not** fully separate auxiliary from noun: it splits
the auxiliary into hundreds of per-verb phrases rather than into one countable
auxiliary sense.  Doing that properly needs POS-aware counting, which this
tokenizer does not do either way.

**Joining periphrasis makes the word lists longer**, because each ``will
<verb>`` is a token competing for a slot: ~660 extra entries against this
database.  The corpus ``max_words`` caps were raised accordingly (see
``wordfreq.corpora.book_lists``); without that the new phrase tokens would push
ordinary vocabulary off the bottom of the list.

A lexical compound has neither problem: "ice cream" is contiguous by
definition, and "cream" genuinely should not be credited for it.

The test is the stored ``grammatical_form``, not a guess about the words.
Periphrastic slots are tagged (``verb/en_1s_future``,
``adjective/en_comparative``); lexical entries carry an ordinary base or plural
tag.

Both the forms table and the lemma headwords are read.  Inflections of a
compound come along for free where they exist ("ice cream" and "ice creams" are
separate ``DerivativeForm`` rows), but a lemma need not have any forms at all --
"ice cream" is stored as a headword with none -- so the lemma text is indexed
too.  Missing an inflection is acceptable; missing the compound itself is not.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, FrozenSet, List, Optional, Sequence, Set, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from storage.models.schema import SYNONYM_GRAMMATICAL_FORMS, DerivativeForm, Lemma
from storage.models.variant_form import (
    VARIANT_KIND_SCRIPT,
    VARIANT_KIND_SPELLING,
    VariantForm,
)

logger = logging.getLogger(__name__)

# Grammatical-form suffixes that mark a periphrastic (multi-word) inflection
# rather than a lexical compound. Matched against the part after the "/", so
# they hold across parts of speech.
PERIPHRASTIC_FORM_SUFFIXES: FrozenSet[str] = frozenset(
    {
        "en_1s_future",
        "en_2s_future",
        "en_3s_future",
        "en_1p_future",
        "en_2p_future",
        "en_3p_future",
        "en_comparative",
        "en_superlative",
    }
)

# Leading words that make a form periphrastic whatever its tag. A backstop for
# rows tagged loosely (a bare "lemma" or a synonym class), so a stray
# "will become" cannot reach the index through an untagged path.
PERIPHRASTIC_LEADING_WORDS: FrozenSet[str] = frozenset(
    {
        "will",
        "shall",
        "would",
        "should",
        "could",
        "more",
        "most",
        "has",
        "have",
        "had",
        "is",
        "are",
        "was",
        "were",
        "am",
        "been",
        "being",
        "do",
        "does",
        "did",
    }
)

# A form carrying a parenthetical gloss, a bracketed counter, or a slash-
# separated list of alternatives ("flock / herd / swarm") is a dictionary
# annotation, not a surface string a corpus will ever contain.
ANNOTATION_RE = re.compile(r"[()\[\]/]")


# The variant kinds that mean "the same lexeme, written differently", and so
# whose occurrences belong to the lemma.  A spelling variant ("north-east") and
# a script variant are the same word; an "expanded" row ("table wine" against
# "wine") is a narrower term and an "abbreviation" a short form, and folding
# either into the lemma would hand one word another's count.
SAME_LEXEME_VARIANT_KINDS = frozenset({VARIANT_KIND_SPELLING, VARIANT_KIND_SCRIPT})


# A form the tokenizer will see as more than one token: it contains a space or
# a hyphen.  RAW_TOKEN_RE splits on both, so "north-east" and "north east" are
# equally in need of joining and equally indexable.
_MULTI_WORD_RE = re.compile(r"[\s-]")


def is_periphrastic(form_text: str, grammatical_form: Optional[str]) -> bool:
    """Whether a multi-word form is grammatical inflection rather than a compound.

    Checked two ways, because the tag is authoritative when present but not
    every row is tagged tightly:

    * the ``grammatical_form`` names a periphrastic slot, or
    * the form begins with an auxiliary or degree word.
    """
    if grammatical_form:
        suffix = grammatical_form.split("/", 1)[-1]
        if suffix in PERIPHRASTIC_FORM_SUFFIXES:
            return True

    first_word = form_text.strip().lower().split(" ", 1)[0]
    return first_word in PERIPHRASTIC_LEADING_WORDS


def is_indexable_phrase(form_text: str, grammatical_form: Optional[str]) -> bool:
    """Whether a form should be counted as one token by the corpus tokenizer.

    Requires a genuine multi-word surface string that a corpus could contain:
    at least two words, no dictionary annotation, and not periphrastic.  A
    hyphen counts as a word separator, because the tokenizer treats it as one:
    "north-east" reaches the corpus as two tokens and needs joining exactly as
    "north east" does.
    """
    text = form_text.strip()
    if not _MULTI_WORD_RE.search(text):
        return False
    if ANNOTATION_RE.search(text):
        return False
    return not is_periphrastic(text, grammatical_form)


def load_lemma_phrases(
    session: Session,
    language_code: str = "en",
    include_synonyms: bool = True,
    include_periphrastic: bool = True,
) -> List[str]:
    """Multi-word lemma forms to index, lowercased and deduplicated.

    Args:
        session: Open session.
        language_code: Language of the forms to read. The phrase index is
            per-language because the tokenizer runs over one language's corpus.
        include_synonyms: Whether to index synonym-class forms ("cell phone"
            as a synonym of "mobile phone"). They are ordinary surface strings
            a corpus can contain, so they are included by default.
        include_periphrastic: Whether to index periphrastic inflections ("will
            walk", "more quickly"). On by default: "will want" is a form of
            "want". See the module docstring for the tradeoff, and note this
            makes the resulting word lists longer.

    Returns:
        Sorted lowercased phrases, each of two or more words.
    """
    candidates: List[Tuple[str, Optional[str]]] = [
        (form_text, grammatical_form)
        for form_text, grammatical_form in session.query(
            DerivativeForm.derivative_form_text, DerivativeForm.grammatical_form
        )
        .join(Lemma, DerivativeForm.lemma_id == Lemma.id)
        .filter(
            DerivativeForm.language_code == language_code,
            or_(
                DerivativeForm.derivative_form_text.like("% %"),
                DerivativeForm.derivative_form_text.like("%-%"),
            ),
        )
        .all()
    ]

    # English lemmas are headwords in their own right, and not all of them have
    # DerivativeForm rows -- "ice cream" is a lemma with no forms at all, so
    # reading only the forms table would miss the very compound this feature
    # exists for. Lemma text carries no grammatical_form, so it is treated as
    # an ordinary lexical entry and still screened for periphrasis by its
    # leading word.
    if language_code == "en":
        candidates.extend(
            (lemma_text, None)
            for (lemma_text,) in session.query(Lemma.lemma_text)
            .filter(or_(Lemma.lemma_text.like("% %"), Lemma.lemma_text.like("%-%")))
            .all()
        )

    # Variant spellings are the same lexeme as their lemma, so a corpus writing
    # "north-east" is writing the "northeast" lemma and the occurrence belongs
    # to it.  The variant has to be in the index before it can be joined at all
    # -- the tokenizer splits it into "north" and "east" otherwise --  and
    # load_canonical_phrases then says which spelling to credit.  Hyphenated
    # and spaced variants both qualify; a solid one needs no joining.
    candidates.extend(
        (variant_text, None)
        for (variant_text,) in session.query(VariantForm.variant_form_text)
        .filter(
            VariantForm.language_code == language_code,
            or_(
                VariantForm.variant_form_text.like("% %"),
                VariantForm.variant_form_text.like("%-%"),
            ),
        )
        .all()
    )

    phrases: Set[str] = set()
    for form_text, grammatical_form in candidates:
        if not include_synonyms and grammatical_form in SYNONYM_GRAMMATICAL_FORMS:
            continue
        text = form_text.strip()
        if not _MULTI_WORD_RE.search(text) or ANNOTATION_RE.search(text):
            continue
        if not include_periphrastic and is_periphrastic(text, grammatical_form):
            continue
        phrases.add(text.lower())

    return sorted(phrases)


def load_phrase_index(
    session: Session,
    language_code: str = "en",
    include_synonyms: bool = True,
    include_periphrastic: bool = True,
    extra_phrases: Sequence[str] = (),
) -> Dict[str, int]:
    """Build the ``{phrase: word count}`` index the tokenizer consumes.

    ``extra_phrases`` lets a caller add phrases that are not lemma forms --
    notably the multi-word entries from
    :mod:`wordfreq.corpora.proper_noun_vocabulary` ("New York", "Atlantic
    Ocean"), which must be matched whole so the proper-noun whitelist can
    protect them as units.
    """
    from wordfreq.corpora.gutenberg_text import build_phrase_index

    phrases = load_lemma_phrases(
        session,
        language_code=language_code,
        include_synonyms=include_synonyms,
        include_periphrastic=include_periphrastic,
    )
    phrases.extend(phrase.strip().lower() for phrase in extra_phrases if phrase.strip())
    return build_phrase_index(phrases)


def load_canonical_phrases(
    session: Session,
    language_code: str = "en",
) -> Dict[str, str]:
    """Map each multi-word variant spelling to the lemma spelling it counts as.

    A variant is the same lexeme as its lemma written differently, so its
    occurrences are the lemma's: a corpus writing "north-east" is writing
    "northeast", and counting them apart splits one word's frequency between
    two entries, which is the whole problem this exists to fix.

    Only variants the tokenizer would otherwise fragment are mapped -- ones
    containing a space or a hyphen.  A solid variant is a single token already
    and is not a phrase, so the phrase index has no say over it.

    **Only same-lexeme kinds are folded.**  ``variant_kind`` is free-form and
    not every kind means "the same word, written differently": this database
    also holds ``expanded`` rows ("table wine" against "wine") and an
    ``abbreviation`` ("vino"), which are a narrower term and a short form
    rather than spellings.  Crediting "table wine" to "wine" would give one
    word another's occurrences, so those kinds are left to count as themselves.

    Args:
        session: Open session.
        language_code: Language of the variants to read.

    Returns:
        ``{joined phrase: lemma spelling}``, ready for
        :func:`wordfreq.corpora.gutenberg_text.build_canonical_phrase_index`.
    """
    from wordfreq.corpora.gutenberg_text import build_canonical_phrase_index

    rows = (
        session.query(VariantForm.variant_form_text, Lemma.lemma_text)
        .join(Lemma, VariantForm.lemma_id == Lemma.id)
        .filter(
            VariantForm.language_code == language_code,
            VariantForm.variant_kind.in_(SAME_LEXEME_VARIANT_KINDS),
            or_(
                VariantForm.variant_form_text.like("% %"),
                VariantForm.variant_form_text.like("%-%"),
            ),
        )
        .all()
    )
    return build_canonical_phrase_index(
        (variant_text, lemma_text)
        for variant_text, lemma_text in rows
        if variant_text and lemma_text and not ANNOTATION_RE.search(variant_text)
    )


__all__ = [
    "ANNOTATION_RE",
    "PERIPHRASTIC_FORM_SUFFIXES",
    "PERIPHRASTIC_LEADING_WORDS",
    "is_indexable_phrase",
    "is_periphrastic",
    "load_canonical_phrases",
    "load_lemma_phrases",
    "load_phrase_index",
]
