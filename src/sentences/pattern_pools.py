"""Load the slot words for pattern sentences (langtools.sentence_patterns)
from the database.

Read-only: nouns in the object and colorable subtypes, color adjectives and
the feeling adjectives the patterns name, each with its translation, forms
and grammar facts in one language.  A word with no translation is left out;
a word missing a form is kept, so the pattern reports it as a Skip.
"""

from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from langtools.es import sentence_patterns as es
from langtools.fr import sentence_patterns as fr
from langtools.lt import sentence_patterns as lt
from langtools.sentence_patterns.common import COLORABLE_GROUPS, OBJECT_GROUPS, strip_disambiguation
from langtools.zh import sentence_patterns as zh
from langtools.sentence_patterns.types import Gender, SlotAdjective, SlotNoun, WordPools
from storage.models.grammar_fact import GrammarFact
from storage.models.schema import DerivativeForm, Lemma, LemmaTranslation

NOUN_GROUPS = OBJECT_GROUPS | COLORABLE_GROUPS
FEELINGS = lt.FEELINGS | es.FEELINGS | fr.FEELINGS | zh.FEELINGS


def _forms(session: Session, lemma_ids: List[int], language_code: str) -> Dict[int, Dict[str, str]]:
    """{lemma_id: {'accusative_singular': ...}} for one language.

    'noun/es-419_plural' -> 'plural'; the language code is the prefix, so a
    query for es never picks up es-419 rows.
    """
    result: Dict[int, Dict[str, str]] = defaultdict(dict)
    if not lemma_ids:
        return result
    rows = (
        session.query(DerivativeForm)
        .filter(
            DerivativeForm.lemma_id.in_(lemma_ids),
            DerivativeForm.language_code == language_code,
        )
        .order_by(DerivativeForm.is_base_form.desc(), DerivativeForm.id)
        .all()
    )
    prefix = f"{language_code}_"
    for row in rows:
        slot = row.grammatical_form.split("/", 1)[-1]
        if not slot.startswith(prefix):
            continue
        key = slot[len(prefix) :]
        text = row.derivative_form_text.strip()
        if text:
            result[row.lemma_id].setdefault(key, text)
    return result


def _facts(
    session: Session, lemma_ids: List[int], language_code: str, fact_type: str
) -> Dict[int, str]:
    if not lemma_ids:
        return {}
    rows = (
        session.query(GrammarFact)
        .filter(
            GrammarFact.lemma_id.in_(lemma_ids),
            GrammarFact.language_code == language_code,
            GrammarFact.fact_type == fact_type,
        )
        .all()
    )
    return {r.lemma_id: r.fact_value.strip() for r in rows if r.fact_value and r.fact_value.strip()}


def _translated(
    session: Session, lemmas: List[Lemma], language_code: str
) -> List[Tuple[Lemma, str]]:
    ids = [lemma.id for lemma in lemmas]
    if not ids:
        return []
    translations = {
        t.lemma_id: strip_disambiguation(t.translation)
        for t in session.query(LemmaTranslation).filter(
            LemmaTranslation.lemma_id.in_(ids),
            LemmaTranslation.language_code == language_code,
        )
    }
    return [(lemma, translations[lemma.id]) for lemma in lemmas if translations.get(lemma.id)]


def _level_ok(lemma: Lemma, max_level: Optional[int]) -> bool:
    if max_level is None:
        return True
    return lemma.difficulty_level is not None and 0 < lemma.difficulty_level <= max_level


def load_pools(session: Session, language_code: str, max_level: Optional[int] = None) -> WordPools:
    noun_lemmas = [
        lemma
        for lemma in session.query(Lemma).filter(
            Lemma.guid.isnot(None),
            Lemma.pos_type == "noun",
            Lemma.pos_subtype.in_(sorted(NOUN_GROUPS)),
        )
        if _level_ok(lemma, max_level)
    ]
    nouns_translated = _translated(session, noun_lemmas, language_code)
    noun_ids = [lemma.id for lemma, _ in nouns_translated]
    noun_forms = _forms(session, noun_ids, language_code)
    english_forms = _forms(session, noun_ids, "en")
    countabilities = _facts(session, noun_ids, language_code, "countability")
    english_countabilities = _facts(session, noun_ids, "en", "countability")
    number_types = _facts(session, noun_ids, language_code, "number_type")
    english_number_types = _facts(session, noun_ids, "en", "number_type")
    genders = _facts(session, noun_ids, language_code, "grammatical_gender")
    measure_words = (
        _facts(session, noun_ids, language_code, "measure_words") if language_code == "zh" else {}
    )

    nouns: List[SlotNoun] = []
    for lemma, target in nouns_translated:
        gender_fact = genders.get(lemma.id)
        gender: Optional[Gender] = None
        if gender_fact == "masculine":
            gender = "masculine"
        elif gender_fact == "feminine":
            gender = "feminine"
        nouns.append(
            SlotNoun(
                guid=str(lemma.guid),
                english=strip_disambiguation(lemma.lemma_text),
                target=target,
                group=str(lemma.pos_subtype),
                countability=countabilities.get(lemma.id),
                english_countability=english_countabilities.get(lemma.id),
                number_type=number_types.get(lemma.id),
                english_number_type=english_number_types.get(lemma.id),
                english_plural=english_forms.get(lemma.id, {}).get("plural"),
                gender=gender,
                gender_fact=gender_fact,
                measure_word=measure_words.get(lemma.id),
                level=lemma.difficulty_level,
                forms=noun_forms.get(lemma.id, {}),
            )
        )

    adjective_lemmas: List[Lemma] = []
    seen_feelings: Set[str] = set()
    for lemma in (
        session.query(Lemma)
        .filter(Lemma.guid.isnot(None), Lemma.pos_type == "adjective")
        .order_by(Lemma.difficulty_level, Lemma.id)
    ):
        if not _level_ok(lemma, max_level):
            continue
        english = strip_disambiguation(lemma.lemma_text)
        if lemma.pos_subtype == "color":
            adjective_lemmas.append(lemma)
        elif english in FEELINGS and english not in seen_feelings:
            # One sense per feeling: the earliest-level one is the everyday sense.
            seen_feelings.add(english)
            adjective_lemmas.append(lemma)
    adjectives_translated = _translated(session, adjective_lemmas, language_code)
    adjective_forms = _forms(
        session, [lemma.id for lemma, _ in adjectives_translated], language_code
    )
    adjectives = [
        SlotAdjective(
            guid=str(lemma.guid),
            english=strip_disambiguation(lemma.lemma_text),
            target=target,
            kind="color" if lemma.pos_subtype == "color" else "feeling",
            level=lemma.difficulty_level,
            forms=adjective_forms.get(lemma.id, {}),
        )
        for lemma, target in adjectives_translated
    ]
    return WordPools(nouns=nouns, adjectives=adjectives)
