"""Read existing English lemma data without modifying the linguistic database.

Every selector shuffles a stably ordered candidate list with the worksheet's
version number, so the same settings reproduce a sheet while the database is
unchanged.
"""

import json
import random
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Query, Session

from langtools.en.inflection import build_adjective_forms, build_noun_forms
from langtools.en.utils import (
    generate_comparative,
    generate_past_tense,
    generate_regular_plural,
    generate_superlative,
)
from storage.config.lemma_fact_registry import CONTENT_FLAG_ALL_AGES, CONTENT_FLAG_VALUES
from storage.models.grammar_fact import GrammarFact
from storage.models.lemma_fact import LemmaFact
from storage.models.lemma_relation import (
    RELATION_TYPE_DERIVATIONAL,
    RELATION_TYPE_SYNONYM,
    LemmaRelationGroup,
    LemmaRelationMember,
)
from storage.models.schema import DerivativeForm, Lemma, LemmaTier
from worksheets.models import FamilyMember, FormEntry, Word

# Cambridge Young Learners English tiers, easiest first.  A chosen tier
# includes every easier one: "movers" means Starters or Movers words.
YLE_SOURCE = "cambridge_yle"
YLE_TIERS: tuple[str, ...] = ("starters", "movers", "flyers")

# kind -> (part of speech, grammar slots the question asks for).
FORM_KINDS: dict[str, tuple[str, tuple[str, ...]]] = {
    "plural": ("noun", ("plural",)),
    "past": ("verb", ("past",)),
    "past_participle": ("verb", ("past_participle",)),
    "principal_parts": ("verb", ("past", "past_participle")),
    "comparison": ("adjective", ("comparative", "superlative")),
}

_HEADWORD = re.compile(r"[a-z]{2,16}")
# Answers may be periphrastic ("more careful") or hyphenated ("co-wrote").
_FORM_TEXT = re.compile(r"[a-z][a-z'-]*( [a-z][a-z'-]*)?")


# How the content_flag lemma fact restricts selection:
#   exclude_flagged  unrated senses allowed; flagged ones only if their flag is allowed
#   reviewed_only    only senses rated "all_ages" or with an allowed flag
#   any              no restriction
CONTENT_POLICIES: tuple[str, ...] = ("exclude_flagged", "reviewed_only", "any")
CONTENT_FLAGS: tuple[str, ...] = tuple(
    flag for flag in CONTENT_FLAG_VALUES if flag != CONTENT_FLAG_ALL_AGES
)


@dataclass(frozen=True)
class SelectionFilters:
    """Restrictions shared by every activity's word selection."""

    category: str = ""
    yle_tier: str = ""
    max_frequency_rank: Optional[int] = None
    content_policy: str = "exclude_flagged"
    # Flags the user has chosen to permit, such as death_illness for older students.
    allowed_flags: frozenset[str] = frozenset()


def _filtered_query(
    session: Session, filters: SelectionFilters, pos_type: str = ""
) -> "Query[Lemma]":
    query = session.query(Lemma).filter(Lemma.guid.isnot(None))
    if pos_type:
        query = query.filter(Lemma.pos_type == pos_type)
    if filters.category:
        query = query.filter(Lemma.pos_subtype == filters.category)
    if filters.yle_tier:
        if filters.yle_tier not in YLE_TIERS:
            raise ValueError("Unknown Cambridge YLE tier.")
        allowed_tiers = YLE_TIERS[: YLE_TIERS.index(filters.yle_tier) + 1]
        tier_lemmas = session.query(LemmaTier.lemma_id).filter(
            LemmaTier.source == YLE_SOURCE, LemmaTier.tier_name.in_(allowed_tiers)
        )
        query = query.filter(Lemma.id.in_(tier_lemmas))
    if filters.content_policy not in CONTENT_POLICIES:
        raise ValueError("Unknown content policy.")
    if not filters.allowed_flags <= set(CONTENT_FLAGS):
        raise ValueError("Unknown content flag.")
    if filters.content_policy != "any":
        acceptable = {CONTENT_FLAG_ALL_AGES} | filters.allowed_flags
        rated = session.query(LemmaFact.lemma_id).filter(LemmaFact.fact_type == "content_flag")
        if filters.content_policy == "reviewed_only":
            query = query.filter(Lemma.id.in_(rated.filter(LemmaFact.fact_value.in_(acceptable))))
        else:
            query = query.filter(
                Lemma.id.notin_(rated.filter(LemmaFact.fact_value.notin_(acceptable)))
            )
    if filters.max_frequency_rank is not None:
        query = query.filter(
            Lemma.frequency_rank.isnot(None),
            Lemma.frequency_rank <= filters.max_frequency_rank,
        )
    return query


def _candidates(session: Session, filters: SelectionFilters, pos_type: str = "") -> list[Lemma]:
    """Filtered lemmas in a stable order, so a seeded shuffle is reproducible."""
    return list(_filtered_query(session, filters, pos_type).order_by(Lemma.guid).all())


def _headword(lemma: Lemma) -> Optional[str]:
    """The lowercase single-word headword, or None for phrases and proper nouns."""
    text = lemma.lemma_text.strip()
    return text if _HEADWORD.fullmatch(text) else None


def _shortfall(found: int) -> ValueError:
    return ValueError(
        f"Only {found} eligible items found; request fewer questions or change filters."
    )


def select_words(
    session: Session,
    count: int,
    clue_type: str,
    seed: int,
    filters: Optional[SelectionFilters] = None,
) -> list[Word]:
    """Select unique words and clues; exclude clues that reveal the spelling."""
    lemmas = _candidates(session, filters or SelectionFilters())
    random.Random(seed).shuffle(lemmas)
    selected: list[Word] = []
    seen_words: set[str] = set()
    seen_clues: set[str] = set()
    for lemma in lemmas:
        text = lemma.lemma_text.strip().lower()
        if not _HEADWORD.fullmatch(text) or len(set(text)) < 2:
            continue
        definition = lemma.definition_text.strip()
        try:
            emojis = json.loads(lemma.emoji or "[]")
        except (ValueError, TypeError):
            emojis = []
        emoji = (
            next((item for item in emojis if isinstance(item, str) and item.strip()), "")
            if isinstance(emojis, list)
            else ""
        )
        clue = emoji if clue_type == "emoji" else definition
        normalized_clue = clue.casefold()
        if not clue or text in seen_words or normalized_clue in seen_clues:
            continue
        if clue_type == "definition" and re.search(rf"\b{re.escape(text)}\b", clue, re.I):
            continue
        selected.append(Word(str(lemma.guid), text, definition, emoji))
        seen_words.add(text)
        seen_clues.add(normalized_clue)
        if len(selected) == count:
            break
    if len(selected) < count:
        raise _shortfall(len(selected))
    return selected


# ---------------------------------------------------------------------------
# Word forms: plurals, past tense, past participles, comparison
# ---------------------------------------------------------------------------


def _english_facts(session: Session, fact_types: tuple[str, ...]) -> dict[int, dict[str, str]]:
    """English grammar facts of the given types, keyed by lemma id."""
    facts: dict[int, dict[str, str]] = defaultdict(dict)
    rows = session.query(GrammarFact.lemma_id, GrammarFact.fact_type, GrammarFact.fact_value)
    for lemma_id, fact_type, fact_value in rows.filter(
        GrammarFact.language_code == "en", GrammarFact.fact_type.in_(fact_types)
    ):
        if fact_value:
            facts[lemma_id][fact_type] = fact_value.strip()
    return facts


def _stored_plurals(session: Session) -> dict[int, str]:
    """Plural forms the database already holds; these outrank the rules, as in production."""
    rows = session.query(DerivativeForm.lemma_id, DerivativeForm.derivative_form_text).filter(
        DerivativeForm.language_code == "en",
        DerivativeForm.grammatical_form == "noun/en_plural",
    )
    return {lemma_id: text.strip() for lemma_id, text in rows}


def _lemma_forms(
    kind: str,
    word: str,
    facts: dict[str, str],
    stored_plural: Optional[str],
) -> Optional[tuple[str, ...]]:
    """The requested forms of *word*, or None when they are unknown or absent."""
    pos_type, slots = FORM_KINDS[kind]
    if pos_type == "noun":
        if facts.get("number_type") == "plurale_tantum":
            return None
        noun_forms = build_noun_forms(
            word, facts.get("countability"), facts.get("number_type"), facts.get("plural")
        )
        if noun_forms is not None and "plural" not in noun_forms:
            return None  # Singular-only noun: there is no plural to ask for.
        plural = stored_plural or (noun_forms or {}).get("plural")
        return (plural,) if plural else None
    if pos_type == "verb":
        # Principal parts are stored facts: a rule would give "goed".
        verb_forms = tuple(facts.get(slot, "") for slot in slots)
        return verb_forms if all(verb_forms) else None
    degree_forms = build_adjective_forms(
        word, facts.get("gradability"), facts.get("comparative"), facts.get("superlative")
    )
    if not degree_forms or not all(slot in degree_forms for slot in slots):
        return None
    return tuple(degree_forms[slot] for slot in slots)


def is_irregular(kind: str, base: str, forms: tuple[str, ...]) -> bool:
    """Whether any requested form departs from the ordinary spelling rule."""
    pos_type, slots = FORM_KINDS[kind]
    for slot, form in zip(slots, forms):
        if slot == "plural":
            regular = {generate_regular_plural(base)}
        elif slot in ("past", "past_participle"):
            regular = {generate_past_tense(base)}
        elif slot == "comparative":
            regular = {generate_comparative(base), f"more {base}"}
        else:
            regular = {generate_superlative(base), f"most {base}"}
        if form not in regular:
            return True
    return False


def select_word_forms(
    session: Session,
    count: int,
    kind: str,
    seed: int,
    filters: Optional[SelectionFilters] = None,
    irregular_only: bool = False,
) -> list[FormEntry]:
    """Select base words with their stored or rule-built inflected forms."""
    if kind not in FORM_KINDS:
        raise ValueError("Unknown word-form activity.")
    pos_type = FORM_KINDS[kind][0]
    facts = _english_facts(
        session,
        (
            "plural",
            "countability",
            "number_type",
            "past",
            "past_participle",
            "gradability",
            "comparative",
            "superlative",
        ),
    )
    stored_plurals = _stored_plurals(session) if pos_type == "noun" else {}
    candidates: list[tuple[Lemma, str, tuple[str, ...]]] = []
    forms_by_word: dict[str, set[tuple[str, ...]]] = defaultdict(set)
    for lemma in _candidates(session, filters or SelectionFilters(), pos_type):
        word = _headword(lemma)
        if word is None:
            continue
        forms = _lemma_forms(kind, word, facts.get(lemma.id, {}), stored_plurals.get(lemma.id))
        if forms is None or not all(_FORM_TEXT.fullmatch(form) for form in forms):
            continue
        candidates.append((lemma, word, forms))
        forms_by_word[word].add(forms)
    random.Random(seed).shuffle(candidates)
    selected: list[FormEntry] = []
    seen_words: set[str] = set()
    for lemma, word, forms in candidates:
        if word in seen_words or (irregular_only and not is_irregular(kind, word, forms)):
            continue
        clue = ""
        if len(forms_by_word[word]) > 1:
            # Senses of this spelling inflect differently; only a labelled sense is fair.
            if not lemma.disambiguation:
                continue
            clue = lemma.disambiguation
        selected.append(FormEntry(str(lemma.guid), word, forms, clue))
        seen_words.add(word)
        if len(selected) == count:
            break
    if len(selected) < count:
        raise _shortfall(len(selected))
    return selected


# ---------------------------------------------------------------------------
# Relation groups: word families and synonyms
# ---------------------------------------------------------------------------


def _relation_groups(
    session: Session, relation_type: str, filters: SelectionFilters
) -> list[list[Lemma]]:
    """Groups whose every member is an eligible single-word lemma, in stable order."""
    allowed = {lemma.id: lemma for lemma in _candidates(session, filters)}
    members: dict[int, list[Lemma]] = defaultdict(list)
    complete: dict[int, bool] = defaultdict(lambda: True)
    rows = (
        session.query(LemmaRelationMember.group_id, LemmaRelationMember.lemma_id)
        .join(LemmaRelationGroup, LemmaRelationGroup.id == LemmaRelationMember.group_id)
        .filter(LemmaRelationGroup.relation_type == relation_type)
        .order_by(LemmaRelationMember.group_id, LemmaRelationMember.lemma_id)
    )
    for group_id, lemma_id in rows:
        member = allowed.get(lemma_id)
        if member is None or _headword(member) is None:
            complete[group_id] = False
        else:
            members[group_id].append(member)
    groups = []
    for group_id in sorted(members):
        texts = {_headword(member) for member in members[group_id]}
        if complete[group_id] and len(texts) == len(members[group_id]) >= 2:
            groups.append(members[group_id])
    return groups


def select_families(
    session: Session, count: int, seed: int, filters: Optional[SelectionFilters] = None
) -> list[tuple[FamilyMember, ...]]:
    """Select derivational word families (beauty/beautiful) with no repeated word."""
    groups = _relation_groups(session, RELATION_TYPE_DERIVATIONAL, filters or SelectionFilters())
    random.Random(seed).shuffle(groups)
    selected: list[tuple[FamilyMember, ...]] = []
    seen_words: set[str] = set()
    for group in groups:
        family = tuple(
            FamilyMember(
                str(lemma.guid),
                str(_headword(lemma)),
                lemma.pos_type,
                lemma.definition_text.strip(),
            )
            for lemma in group
        )
        texts = {member.text for member in family}
        if texts & seen_words:
            continue
        selected.append(family)
        seen_words |= texts
        if len(selected) == count:
            break
    if len(selected) < count:
        raise _shortfall(len(selected))
    return selected


def select_synonym_pairs(
    session: Session, count: int, seed: int, filters: Optional[SelectionFilters] = None
) -> list[Word]:
    """Select synonym pairs as words whose clue (``definition``) is the partner word."""
    groups = _relation_groups(session, RELATION_TYPE_SYNONYM, filters or SelectionFilters())
    rng = random.Random(seed)
    rng.shuffle(groups)
    selected: list[Word] = []
    seen_words: set[str] = set()
    for group in groups:
        texts = [str(_headword(lemma)) for lemma in group]
        # Any word of the group would be a correct match, so the whole group is used up.
        if set(texts) & seen_words:
            continue
        first, second = rng.sample(range(len(group)), 2)
        selected.append(Word(str(group[first].guid), texts[first], texts[second]))
        seen_words |= set(texts)
        if len(selected) == count:
            break
    if len(selected) < count:
        raise _shortfall(len(selected))
    return selected


# ---------------------------------------------------------------------------
# Rhymes
# ---------------------------------------------------------------------------

# Stored English IPA mixes transcription conventions (length marks, ɝ beside
# ɜːr, a few British vowels), which would split one rhyme family into several
# keys.  Folding them is a stopgap until the IPA is normalized at the source.
_RHYME_FOLDS: tuple[tuple[str, str], ...] = (
    ("ː", ""),
    (".", ""),
    ("ˌ", ""),
    ("ˈ", ""),
    ("ɝ", "ɜr"),
    ("ɚ", "ər"),
    ("ɹ", "r"),
    ("əʊ", "oʊ"),
    ("ɒ", "ɑ"),
    ("g", "ɡ"),
    ("ʧ", "tʃ"),
    ("ʤ", "dʒ"),
    # Syllabic consonants written with or without schwa: /ˈteɪbəl/, /ˈkeɪbl/.
    ("əl", "l"),
    ("ən", "n"),
)


def normalize_rhyme_key(key: str) -> str:
    """Fold transcription variants so words that rhyme share one key."""
    for old, new in _RHYME_FOLDS:
        key = key.replace(old, new)
    return key


def _base_form_rhyme_keys(session: Session) -> dict[int, str]:
    """Normalized rhyme key of each lemma's English base form, keyed by lemma id."""
    from langtools.rhyme_keys import compute_rhyme_key

    rows = session.query(
        DerivativeForm.lemma_id, DerivativeForm.rhyme_key, DerivativeForm.ipa_pronunciation
    ).filter(DerivativeForm.language_code == "en", DerivativeForm.is_base_form.is_(True))
    keys: dict[int, str] = {}
    for lemma_id, rhyme_key, ipa in rows:
        key = rhyme_key or (compute_rhyme_key(ipa, "en") if ipa else None)
        if key and lemma_id not in keys:
            keys[lemma_id] = normalize_rhyme_key(key)
    return keys


def select_rhyme_pairs(
    session: Session, count: int, seed: int, filters: Optional[SelectionFilters] = None
) -> list[Word]:
    """Select rhyming pairs from distinct rhyme families, the partner word as the clue.

    No two pairs on a sheet share a rhyme key, and no two share a three-letter
    spelling ending either: that catches families still split by inconsistent
    transcriptions, which would otherwise let a clue match two words.
    """
    rhyme_keys = _base_form_rhyme_keys(session)
    families: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for lemma in _candidates(session, filters or SelectionFilters()):
        word = _headword(lemma)
        key = rhyme_keys.get(lemma.id)
        if word and key and word not in {text for _, text in families[key]}:
            families[key].append((str(lemma.guid), word))
    rng = random.Random(seed)
    keys = sorted(key for key, members in families.items() if len(members) >= 2)
    rng.shuffle(keys)
    selected: list[Word] = []
    used_endings: set[str] = set()
    for key in keys:
        family_endings = {text[-3:] for _, text in families[key]}
        if family_endings & used_endings:
            continue
        first, second = rng.sample(families[key], 2)
        selected.append(Word(first[0], first[1], second[1]))
        used_endings |= family_endings
        if len(selected) == count:
            break
    if len(selected) < count:
        raise _shortfall(len(selected))
    return selected
