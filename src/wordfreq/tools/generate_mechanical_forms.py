#!/usr/bin/env python3

"""Generate derivative forms that follow mechanically from spelling.

The rule-based builders in ``langtools`` reproduce most paradigms from a word
plus its stored grammar facts.  Forms a rule can regenerate do not need to be
stored in ``data/release``; this script puts them back after a release import,
so the release files only have to carry the ones the rules cannot derive.

Currently covers English (nouns, adjectives, adverbs, verbs), Lithuanian
(nouns, verbs), and French and Spanish (adjectives, verbs).  For English the
lemma text is the word; for the others it is the lemma's translation into that
language.

No LLM is involved.  The builders are called directly rather than through
``LinguisticClient``, whose ``query_*_forms`` entry points fall back to a model
when the rules decline.  Here a declining rule means "skip this lemma", which
is the whole point: a word the rules are unsure about is a word whose forms
belong in ``data/release``.

Run it against a database that already holds lemmas and grammar facts -- the
builders read countability, number_type, gradability, irregular forms and the
Lithuanian principal parts per lemma, and those facts are themselves loaded
from the release files.

Some builders also report what they worked out about the paradigm.  Lithuanian
``decline_noun`` infers gender from the ending it matched, and that is written
back as a ``grammatical_gender`` fact when the noun has none: gender is
recomputable, but it is also what other languages get from an LLM, and a
release file holding only the exceptions would read as "no fact" for every
regular noun rather than "regular".  A noun whose gender was already stored
keeps it -- that fact is what selected the pattern, so re-reporting it would
claim the generator derived what it was told.

Existing forms and facts are never overwritten, so re-running is safe and
additive.
"""

import argparse
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy.orm import Session

from langtools.en.conjugation import expand_verb_forms
from langtools.en.inflection import (
    build_adjective_forms,
    build_adverb_forms,
    build_noun_forms,
)
from langtools.es.conjugation import conjugate as es_conjugate
from langtools.es.inflection import build_adjective_forms as es_build_adjective_forms
from langtools.fr.conjugation import conjugate as fr_conjugate
from langtools.fr.inflection import build_adjective_forms as fr_build_adjective_forms
from langtools.lt.conjugation import conjugate as lt_conjugate
from langtools.lt.declension import decline_noun as lt_decline_noun
from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.crud.grammar_fact import add_grammar_fact, get_grammar_fact_value
from storage.crud.operation_log import log_operation
from storage.crud.word_token import add_word_token
from storage.models.enums import GrammaticalForm
from storage.models.schema import DerivativeForm, Lemma
from storage.translation_helpers import get_translation

VALID_GRAMMATICAL_FORMS = frozenset(g.value for g in GrammaticalForm)

# Builder output key -> GrammaticalForm value, per POS. Keys absent from a
# builder's result (a non-gradable adverb has no comparative) are simply not
# written; that is a correct paradigm, not a gap.
FORM_KEYS: Dict[str, Dict[str, str]] = {
    "noun": {
        "singular": "noun/en_singular",
        "plural": "noun/en_plural",
    },
    "adjective": {
        "positive": "adjective/en_positive",
        "comparative": "adjective/en_comparative",
        "superlative": "adjective/en_superlative",
    },
    "adverb": {
        "positive": "adverb/en_positive",
        "comparative": "adverb/en_comparative",
        "superlative": "adverb/en_superlative",
    },
    "verb": {
        "infinitive": "verb/en_infinitive",
        "past": "verb/en_3s_past",
        "past_participle": "verb/en_past_participle",
        "present_participle": "verb/en_present_participle",
        "3s_present": "verb/en_3s_present",
    },
}

# The form that carries is_base_form, per (language, POS).
BASE_FORM_KEY: Dict[Tuple[str, str], str] = {
    ("en", "noun"): "singular",
    ("en", "adjective"): "positive",
    ("en", "adverb"): "positive",
    ("en", "verb"): "infinitive",
    ("lt", "noun"): "nominative_singular",
    ("lt", "verb"): "infinitive",
    ("fr", "adjective"): "singular_m",
    ("fr", "verb"): "infinitive",
    ("es", "adjective"): "singular_m",
    # Spanish has no verb/es_infinitive slot, so no generated form is the base.
}

# decline_noun returns grammatical metadata alongside the case forms; these
# keys describe the paradigm rather than naming a form to store.
LT_NOUN_METADATA_KEYS = frozenset({"number_type", "declension_class", "gender"})

# Paradigm metadata worth keeping as a grammar fact, mapped from the builder's
# key to the registered fact_type.  ``declension_class`` is deliberately absent:
# it is the one fact the registry keeps out of data/release, because
# decline_noun recomputes it from the noun plus its gender.
METADATA_FACT_TYPES: Dict[str, str] = {"gender": "grammatical_gender"}

# Kept ready for the TODO on SUPPORTED below: this mapping is correct and was
# validated against sentence_words; it is the conjugator that needs fixing, so
# enabling ("es", "verb") is the only change required here.
#
# The Spanish conjugator emits a fuller paradigm than GrammaticalForm models:
# it returns preterite, imperfect, conditional, subjunctive and imperative
# forms, while the enum has only present/past/future per person. Present and
# future map by name; "past" is the preterite, which is how the existing
# sentence data uses verb/es_*_past ("compró", "encontró", "vio"). The tenses
# with no enum slot are skipped rather than forced into an approximate one.
ES_VERB_KEYS: Dict[str, str] = {
    **{
        f"{person}_present": f"verb/es_{person}_present"
        for person in ("1s", "2s", "3s", "1p", "2p", "3p")
    },
    **{
        f"{person}_future": f"verb/es_{person}_future"
        for person in ("1s", "2s", "3s", "1p", "2p", "3p")
    },
    **{
        f"{person}_preterite": f"verb/es_{person}_past"
        for person in ("1s", "2s", "3s", "1p", "2p", "3p")
    },
}

# Which (language, POS) pairs have a rule-based builder at all.
#
# TODO: enable ("es", "verb"). langtools.es.conjugation.conjugate has an
# incomplete stem-change table: it handles "querer" -> "quiere" but returns
# "tene" for "tener" (correct: "tiene"), "rie" for "reír" ("ríe") and
# "sonriió" for "sonreír" ("sonrió"), and conjugate_safe reports no warning
# for any of them, so bad output cannot be filtered out at this call site.
# Checking generated forms against the Spanish already in sentence_words gave
# 78.8% agreement (182 agree / 49 disagree) versus 99.35% for lt+fr; those 49
# disagreements are a ready-made test set for fixing the conjugator.  Spanish
# adjectives are regular and validated, so they are enabled here.
SUPPORTED: Dict[str, Tuple[str, ...]] = {
    "en": ("noun", "adjective", "adverb", "verb"),
    "lt": ("noun", "verb"),
    "fr": ("adjective", "verb"),
    "es": ("adjective",),
}


def _facts(
    session: Session, lemma_id: int, *names: str, language_code: str = "en"
) -> Tuple[Optional[str], ...]:
    """Read several grammar facts for a lemma in one call."""
    return tuple(get_grammar_fact_value(session, lemma_id, language_code, name) for name in names)


def _is_mechanically_safe_translation(word: str) -> bool:
    """Whether *word* is a single, lowercase word safe to inflect by rule.

    Multi-word translations ("teikti pirmenybę", "en colère") and proper nouns
    ("Varšuva") must not be inflected mechanically. The Lithuanian conjugator
    logs a warning for an infinitive that does not end in -ti/-tis but still
    returns a paradigm built from the truncated stem, which silently drops the
    second word -- so the caller has to refuse these rather than rely on the
    builder returning None.
    """
    word = word.strip()
    if not word or " " in word:
        return False
    return word == word.lower()


def _build_non_english(
    session: Session, lemma: Lemma, pos_type: str, language_code: str
) -> Tuple[Optional[Dict[str, str]], Dict[str, str]]:
    """Build a non-English paradigm from the lemma's translation.

    Returns the paradigm and any paradigm metadata the builder inferred
    (see ``METADATA_FACT_TYPES``); the metadata is empty for languages and
    parts of speech whose builders report none.
    """
    word = get_translation(session, lemma, language_code)
    if not word or not _is_mechanically_safe_translation(word):
        return None, {}
    word = word.strip()

    if language_code == "lt":
        if pos_type == "verb":
            # Lithuanian conjugation is not recoverable from the infinitive
            # alone; both principal parts are stored as grammar facts.
            present_3, past_3 = _facts(
                session, lemma.id, "3s_present", "3s_past", language_code="lt"
            )
            if not present_3 or not past_3:
                return None, {}
            return lt_conjugate(word, present_3, past_3), {}

        if pos_type == "noun":
            gender, number_type = _facts(
                session, lemma.id, "grammatical_gender", "number_type", language_code="lt"
            )
            declined = lt_decline_noun(word, gender, number_type)
            if not declined:
                return None, {}
            # Split the paradigm metadata decline_noun reports alongside the
            # forms: the forms are stored as derivative_forms, the metadata as
            # grammar facts.  Only report metadata the noun did not already
            # have -- a stored gender is what selected the pattern above, so
            # re-reporting it would claim the generator derived what it was told.
            metadata = {
                key: declined[key]
                for key in METADATA_FACT_TYPES
                if declined.get(key) and not gender
            }
            return (
                {k: v for k, v in declined.items() if k not in LT_NOUN_METADATA_KEYS},
                metadata,
            )

    if language_code == "fr":
        if pos_type == "verb":
            return fr_conjugate(word), {}
        if pos_type == "adjective":
            return fr_build_adjective_forms(word), {}

    if language_code == "es":
        if pos_type == "verb":
            return es_conjugate(word), {}
        if pos_type == "adjective":
            return es_build_adjective_forms(word), {}

    return None, {}


def build_for_lemma(
    session: Session, lemma: Lemma, language_code: str = "en"
) -> Optional[Dict[str, str]]:
    """Return the mechanical paradigm for *lemma* in *language_code*, or None.

    For English the lemma text is the word itself; for other languages the
    word is the lemma's translation, so a lemma with no translation in that
    language has nothing to inflect.

    Callers that also want the paradigm metadata a builder inferred (Lithuanian
    gender, say) should use :func:`build_for_lemma_with_metadata`.
    """
    return build_for_lemma_with_metadata(session, lemma, language_code)[0]


def build_for_lemma_with_metadata(
    session: Session, lemma: Lemma, language_code: str = "en"
) -> Tuple[Optional[Dict[str, str]], Dict[str, str]]:
    """Return the mechanical paradigm for *lemma* and its paradigm metadata."""
    pos_type = lemma.pos_type.lower()

    if language_code != "en":
        return _build_non_english(session, lemma, pos_type, language_code)

    text = lemma.lemma_text

    if pos_type == "noun":
        countability, number_type, irregular_plural = _facts(
            session, lemma.id, "countability", "number_type", "plural"
        )
        return build_noun_forms(text, countability, number_type, irregular_plural), {}

    if pos_type in ("adjective", "adverb"):
        gradability, comparative, superlative = _facts(
            session, lemma.id, "gradability", "comparative", "superlative"
        )
        builder: Callable[..., Optional[Dict[str, str]]] = (
            build_adjective_forms if pos_type == "adjective" else build_adverb_forms
        )
        return builder(text, gradability, comparative, superlative), {}

    if pos_type == "verb":
        past, past_participle = _facts(session, lemma.id, "past", "past_participle")
        base_forms = {"infinitive": text}
        if past:
            base_forms["past"] = past
        if past_participle:
            base_forms["past_participle"] = past_participle
        # expand_verb_forms always returns a table; an irregular verb with no
        # stored past would get a wrong regular one, so require the facts.
        if not past or not past_participle:
            return None, {}
        return expand_verb_forms(base_forms), {}

    return None, {}


def resolve_grammatical_form(language_code: str, pos_type: str, form_key: str) -> Optional[str]:
    """Map a builder's output key to a GrammaticalForm value, or None to skip.

    English uses an explicit table because its builders' key names do not all
    match the enum ("past" -> verb/en_3s_past). The other languages' builders
    already emit keys that match, so the value is composed directly and
    validated against the enum.
    """
    if language_code == "en":
        return FORM_KEYS[pos_type].get(form_key)

    if language_code == "es" and pos_type == "verb":
        return ES_VERB_KEYS.get(form_key)

    candidate = f"{pos_type}/{language_code}_{form_key}"
    return candidate if candidate in VALID_GRAMMATICAL_FORMS else None


def generate(
    config: DataSourceConfig, dry_run: bool = False, languages: Optional[List[str]] = None
) -> Dict[str, Dict[str, int]]:
    """Add missing mechanical forms for every supported language.

    Returns per-language counts of lemmas examined, forms written, and lemmas
    the rules declined to inflect.
    """
    session = create_session(config)
    selected = languages or list(SUPPORTED)
    stats: Dict[str, Dict[str, int]] = {}

    try:
        for language_code in selected:
            pos_types = SUPPORTED[language_code]
            counts = {
                "lemmas_seen": 0,
                "lemmas_written": 0,
                "forms_added": 0,
                "rules_declined": 0,
                "facts_added": 0,
            }
            stats[language_code] = counts

            lemmas: List[Lemma] = (
                session.query(Lemma).filter(Lemma.pos_type.in_(list(pos_types))).all()
            )

            for lemma in lemmas:
                counts["lemmas_seen"] += 1
                pos_type = lemma.pos_type.lower()

                paradigm, metadata = build_for_lemma_with_metadata(session, lemma, language_code)
                if not paradigm:
                    counts["rules_declined"] += 1
                    continue

                # Persist what the builder worked out about the paradigm.  The
                # gender decline_noun infers is worth storing even though it is
                # recomputable: other languages get gender from an LLM, and a
                # release file that carried only the exceptions would be read as
                # "no fact" for every regular noun rather than "regular".
                for metadata_key, fact_type in METADATA_FACT_TYPES.items():
                    fact_value = metadata.get(metadata_key)
                    if not fact_value:
                        continue
                    if get_grammar_fact_value(session, lemma.id, language_code, fact_type):
                        continue
                    if not dry_run:
                        add_grammar_fact(
                            session,
                            lemma_id=lemma.id,
                            language_code=language_code,
                            fact_type=fact_type,
                            fact_value=fact_value,
                            notes="derived mechanically by generate_mechanical_forms",
                        )
                    counts["facts_added"] += 1

                existing = {
                    row.grammatical_form
                    for row in session.query(DerivativeForm).filter(
                        DerivativeForm.lemma_id == lemma.id,
                        DerivativeForm.language_code == language_code,
                    )
                }

                added = 0
                for form_key, form_text in paradigm.items():
                    grammatical_form = resolve_grammatical_form(language_code, pos_type, form_key)
                    if grammatical_form is None or grammatical_form in existing:
                        continue
                    if not form_text or not form_text.strip():
                        continue

                    if not dry_run:
                        token = add_word_token(session, form_text, language_code)
                        session.add(
                            DerivativeForm(
                                lemma_id=lemma.id,
                                derivative_form_text=form_text,
                                word_token_id=token.id,
                                language_code=language_code,
                                grammatical_form=grammatical_form,
                                is_base_form=(
                                    form_key == BASE_FORM_KEY.get((language_code, pos_type))
                                ),
                                verified=False,
                            )
                        )
                    added += 1

                if added:
                    counts["lemmas_written"] += 1
                    counts["forms_added"] += added
                    if not dry_run:
                        log_operation(
                            session,
                            operation_type="mechanical_forms_generated",
                            source="generate_mechanical_forms",
                            entity_type="derivative_form",
                            lemma_id=lemma.id,
                            details={
                                "language_code": language_code,
                                "pos_type": pos_type,
                                "forms_added": added,
                                "generator": f"langtools.{language_code} {pos_type}",
                            },
                        )

        if not dry_run:
            session.commit()
    finally:
        session.close()

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate mechanically-derivable English forms (no LLM calls)"
    )
    parser.add_argument("--db-path", required=True, help="Path to the SQLite database")
    parser.add_argument(
        "--dry-run", action="store_true", help="Report what would be added, write nothing"
    )
    parser.add_argument(
        "--language",
        dest="languages",
        action="append",
        choices=sorted(SUPPORTED),
        help="Limit to one language (repeatable; default: every supported language)",
    )
    args = parser.parse_args()

    config = DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=args.db_path)
    stats = generate(config, dry_run=args.dry_run, languages=args.languages)

    prefix = "would add" if args.dry_run else "added"
    total = 0
    for language_code, counts in sorted(stats.items()):
        total += counts["forms_added"]
        print(
            f"  {language_code}: {counts['lemmas_seen']:5} lemmas examined, "
            f"{counts['rules_declined']:5} declined, "
            f"{prefix} {counts['forms_added']:6} forms "
            f"across {counts['lemmas_written']} lemmas"
            + (f", {counts['facts_added']} grammar facts" if counts["facts_added"] else "")
        )
    print(f"  total forms {prefix}: {total}")


if __name__ == "__main__":
    main()
