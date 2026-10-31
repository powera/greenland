"""Word-form, family, synonym, and rhyme worksheets built from an in-memory database."""

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models.grammar_fact import GrammarFact
from storage.models.lemma_relation import LemmaRelationGroup, LemmaRelationMember
from storage.models.schema import Base, DerivativeForm, Lemma, LemmaTier, WordToken
from worksheets.activities.families import build_families
from worksheets.activities.matching import build_matching
from worksheets.activities.word_forms import BLANK, build_word_forms
from worksheets.rendering.pdf import render_pdf
from worksheets.sources import (
    SelectionFilters,
    is_irregular,
    normalize_rhyme_key,
    select_families,
    select_rhyme_pairs,
    select_synonym_pairs,
    select_word_forms,
)

TABLES = [
    WordToken.__table__,
    Lemma.__table__,
    LemmaTier.__table__,
    GrammarFact.__table__,
    DerivativeForm.__table__,
    LemmaRelationGroup.__table__,
    LemmaRelationMember.__table__,
]


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=TABLES)
    with Session(engine) as db:
        yield db


def _lemma(
    session: Session,
    guid: str,
    text: str,
    pos_type: str,
    *,
    facts: dict[str, str] | None = None,
    ipa: str = "",
    tier: str = "",
    rank: int | None = None,
    disambiguation: str | None = None,
) -> Lemma:
    lemma = Lemma(
        guid=guid,
        lemma_text=text,
        definition_text=f"Definition of {guid}.",
        pos_type=pos_type,
        frequency_rank=rank,
        disambiguation=disambiguation,
    )
    session.add(lemma)
    session.flush()
    for fact_type, fact_value in (facts or {}).items():
        session.add(
            GrammarFact(
                lemma_id=lemma.id, language_code="en", fact_type=fact_type, fact_value=fact_value
            )
        )
    if ipa:
        session.add(
            DerivativeForm(
                lemma_id=lemma.id,
                derivative_form_text=text,
                language_code="en",
                grammatical_form=f"{pos_type}/en_base",
                is_base_form=True,
                ipa_pronunciation=ipa,
            )
        )
    if tier:
        session.add(LemmaTier(lemma_id=lemma.id, source="cambridge_yle", tier_name=tier))
    return lemma


def _group(session: Session, relation_type: str, *lemmas: Lemma) -> None:
    group = LemmaRelationGroup(relation_type=relation_type, concept_label=lemmas[0].lemma_text)
    session.add(group)
    session.flush()
    for lemma in lemmas:
        session.add(LemmaRelationMember(group_id=group.id, lemma_id=lemma.id))


def _verbs(session: Session) -> None:
    _lemma(session, "V1", "go", "verb", facts={"past": "went", "past_participle": "gone"})
    _lemma(session, "V2", "walk", "verb", facts={"past": "walked", "past_participle": "walked"})
    _lemma(session, "V3", "eat", "verb", facts={"past": "ate", "past_participle": "eaten"})
    _lemma(session, "V4", "think", "verb", facts={"past": "thought"})  # no participle
    _lemma(session, "V5", "look up", "verb", facts={"past": "looked up"})  # phrase


def test_principal_parts_use_stored_facts_and_skip_incomplete_verbs(session: Session) -> None:
    _verbs(session)
    entries = select_word_forms(session, 3, "principal_parts", 5)
    assert {entry.base: entry.forms for entry in entries} == {
        "go": ("went", "gone"),
        "walk": ("walked", "walked"),
        "eat": ("ate", "eaten"),
    }
    assert entries == select_word_forms(session, 3, "principal_parts", 5)
    with pytest.raises(ValueError, match="Only 3"):
        select_word_forms(session, 4, "principal_parts", 5)
    # The past alone needs only the past fact, so "think" qualifies.
    assert len(select_word_forms(session, 4, "past", 5)) == 4


def test_irregular_only_and_past_participle_sheet(session: Session) -> None:
    _verbs(session)
    entries = select_word_forms(session, 2, "past_participle", 1, irregular_only=True)
    assert {entry.base for entry in entries} == {"go", "eat"}
    sheet = build_word_forms(entries, "past_participle")
    for question, entry in zip(sheet.questions, entries):
        assert question.prompt == f"{entry.base}: have {BLANK}"
        assert question.answer == entry.forms[0]
    answers = render_pdf(sheet, answers=True)
    assert render_pdf(sheet).startswith(b"%PDF-") and answers.startswith(b"%PDF-")


def test_plurals_prefer_stored_then_fact_then_rule_and_skip_singular_only(session: Session) -> None:
    _lemma(session, "N1", "mouse", "noun", facts={"plural": "mice", "number_type": "regular"})
    _lemma(session, "N2", "cat", "noun", facts={"number_type": "regular"})
    _lemma(session, "N3", "scissors", "noun", facts={"number_type": "plurale_tantum"})
    _lemma(session, "N4", "milk", "noun", facts={"number_type": "singulare_tantum"})
    cactus = _lemma(session, "N5", "cactus", "noun")
    session.add(
        DerivativeForm(
            lemma_id=cactus.id,
            derivative_form_text="cacti",
            language_code="en",
            grammatical_form="noun/en_plural",
        )
    )
    entries = select_word_forms(session, 3, "plural", 2)
    assert {entry.base: entry.forms for entry in entries} == {
        "mouse": ("mice",),
        "cat": ("cats",),
        "cactus": ("cacti",),
    }
    irregular = select_word_forms(session, 2, "plural", 2, irregular_only=True)
    assert {entry.base for entry in irregular} == {"mouse", "cactus"}


def test_comparison_and_irregularity_rules() -> None:
    assert is_irregular("comparison", "good", ("better", "best"))
    assert not is_irregular("comparison", "big", ("bigger", "biggest"))
    assert not is_irregular("comparison", "careful", ("more careful", "most careful"))
    assert is_irregular("principal_parts", "go", ("went", "gone"))
    assert not is_irregular("past", "stop", ("stopped",))


def test_homographs_with_different_forms_need_a_disambiguation(session: Session) -> None:
    facts = {"past": "hung", "past_participle": "hung"}
    _lemma(session, "V1", "hang", "verb", facts=facts, disambiguation="suspend")
    _lemma(session, "V2", "hang", "verb", facts={"past": "hanged", "past_participle": "hanged"})
    entries = select_word_forms(session, 1, "past", 3)
    assert entries[0].forms == ("hung",)
    assert entries[0].clue == "suspend"
    with pytest.raises(ValueError, match="Only 1"):
        select_word_forms(session, 2, "past", 3)


def test_yle_tier_is_cumulative_and_rank_filter_excludes_unranked(session: Session) -> None:
    facts = {"number_type": "regular"}
    _lemma(session, "N1", "cat", "noun", facts=facts, tier="starters", rank=100)
    _lemma(session, "N2", "kite", "noun", facts=facts, tier="movers", rank=2000)
    _lemma(session, "N3", "comet", "noun", facts=facts, tier="flyers")
    _lemma(session, "N4", "dog", "noun", facts=facts, rank=50)

    def bases(filters: SelectionFilters) -> set[str]:
        with pytest.raises(ValueError, match=r"Only (\d+)") as failure:
            select_word_forms(session, 20, "plural", 1, filters)
        found = int(str(failure.value).split()[1])
        return {entry.base for entry in select_word_forms(session, found, "plural", 1, filters)}

    assert bases(SelectionFilters(yle_tier="starters")) == {"cat"}
    assert bases(SelectionFilters(yle_tier="movers")) == {"cat", "kite"}
    assert bases(SelectionFilters(max_frequency_rank=1000)) == {"cat", "dog"}
    with pytest.raises(ValueError, match="Unknown Cambridge"):
        select_word_forms(session, 1, "plural", 1, SelectionFilters(yle_tier="giants"))


def test_word_families_hide_one_member_and_require_every_member_eligible(session: Session) -> None:
    beauty = _lemma(session, "N1", "beauty", "noun")
    beautiful = _lemma(session, "A1", "beautiful", "adjective")
    danger = _lemma(session, "N2", "danger", "noun")
    dangerous = _lemma(session, "A2", "dangerous", "adjective")
    phrase = _lemma(session, "N3", "ice cream", "noun")
    _group(session, "derivational", beauty, beautiful)
    _group(session, "derivational", danger, dangerous)
    _group(session, "derivational", phrase, beautiful)
    families = select_families(session, 2, 4)
    sheet = build_families(families, 4)
    assert sheet == build_families(select_families(session, 2, 4), 4)
    for question, family in zip(sheet.questions, families):
        assert question.prompt.count(BLANK) == 1
        assert question.answer in {member.text for member in family}
        shown_words = [part.split(" (")[0] for part in question.prompt.split(" · ")]
        assert question.answer not in shown_words
    with pytest.raises(ValueError, match="Only 2"):
        select_families(session, 3, 4)


def test_synonym_pairs_use_each_group_once(session: Session) -> None:
    quickly = _lemma(session, "B1", "quickly", "adverb")
    swiftly = _lemma(session, "B2", "swiftly", "adverb")
    rapidly = _lemma(session, "B3", "rapidly", "adverb")
    big = _lemma(session, "A1", "big", "adjective")
    large = _lemma(session, "A2", "large", "adjective")
    _group(session, "synonym", quickly, swiftly, rapidly)
    _group(session, "synonym", big, large)
    _group(session, "derivational", big, quickly)  # not a synonym group
    pairs = select_synonym_pairs(session, 2, 8)
    sheet = build_matching(pairs, "synonym", 8)
    assert sheet.title == "Synonym matching"
    words = [pair.text for pair in pairs] + list(sheet.choices)
    assert len(set(words)) == 4
    for question, pair in zip(sheet.questions, pairs):
        assert sheet.choices[ord(question.answer) - 65] == pair.definition


def test_rhyme_pairs_fold_transcription_variants_and_avoid_shared_endings(session: Session) -> None:
    _lemma(session, "N1", "bird", "noun", ipa="/bɜːrd/")
    _lemma(session, "N2", "word", "noun", ipa="/wɝd/")
    _lemma(session, "N3", "cat", "noun", ipa="/kæt/")
    _lemma(session, "N4", "hat", "noun", ipa="/hæt/")
    _lemma(session, "N5", "dog", "noun", ipa="/dɒɡ/")
    pairs = select_rhyme_pairs(session, 2, 6)
    assert {frozenset((pair.text, pair.definition)) for pair in pairs} == {
        frozenset(("bird", "word")),
        frozenset(("cat", "hat")),
    }
    sheet = build_matching(pairs, "rhyme", 6)
    assert sheet.title == "Rhyme matching"
    with pytest.raises(ValueError, match="Only 2"):
        select_rhyme_pairs(session, 3, 6)


def test_rhyme_families_sharing_a_spelling_ending_are_not_combined(session: Session) -> None:
    # Two keys that a mis-transcription split apart still share "-ake".
    _lemma(session, "N1", "cake", "noun", ipa="/keɪk/")
    _lemma(session, "N2", "lake", "noun", ipa="/leɪk/")
    _lemma(session, "N3", "bake", "verb", ipa="/bek/")
    _lemma(session, "N4", "make", "verb", ipa="/mek/")
    with pytest.raises(ValueError, match="Only 1"):
        select_rhyme_pairs(session, 2, 1)


def test_normalize_rhyme_key_folds_known_variants() -> None:
    assert normalize_rhyme_key("ɜːrd") == normalize_rhyme_key("ɝd")
    assert normalize_rhyme_key("eɪbəl") == normalize_rhyme_key("eɪbl")
    assert normalize_rhyme_key("ɒɡ") == "ɑɡ"
