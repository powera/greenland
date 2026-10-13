"""Tests for LLM level placement: prompt building and answer checking."""

from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from reports.level_candidates import PlacementQuery
from storage.models.curriculum_level import CurriculumLevel
from storage.models.schema import Base, Lemma
from wordfreq.data.cohorts import COHORT_LEVELS, US_STATES
from wordfreq.data.family_relations_sections import ALL_SECTIONS
from words.difficulty.geography_catalog import GEOGRAPHY_SENSES
from wordfreq.frequency.level_profile import LevelCandidate as CorpusMatch
from wordfreq.frequency.level_profile import LevelProfile
from words.level_placement import (
    PLACEMENT_JSON_SCHEMA,
    LevelPlacer,
    MenuLevel,
    OtherSense,
    ShortlistEntry,
    build_context,
    build_prompt,
    describe_lean,
    format_menu,
    menu_from_rows,
    merge_shortlist,
    offered,
    parse_placement,
)

MENU = [
    MenuLevel(8, "Everyday Things", "A1"),
    MenuLevel(120, "Animals", "A2"),
    MenuLevel(121, "Animals 2", "B1"),
    MenuLevel(1070, "Law", "B2"),
]
MENU_LEVELS = [item.level for item in MENU]


def _query(**overrides: Any) -> PlacementQuery:
    fields: Dict[str, Any] = {
        "lemma_text": "badger",
        "pos_type": "noun",
        "pos_subtype": "animal",
        "definition": "a burrowing mammal with a striped face",
        "rank": 8000,
    }
    fields.update(overrides)
    return PlacementQuery(**fields)


def test_offered_skips_preserved_cohort_and_parking_levels() -> None:
    assert offered(6) and offered(150) and offered(1070)
    assert not offered(3)  # hand-curated core
    assert not offered(US_STATES.level)  # a fixed set
    assert not offered(1399)  # parking, outside every band
    assert not offered(-1)


def test_curated_catalog_levels_are_fixed_sets() -> None:
    """A word joins these by being added to its catalog, never by placement."""
    catalog_levels = {sense.base_level for sense in GEOGRAPHY_SENSES} | {
        variant.curriculum_level
        for section in ALL_SECTIONS
        for variant in section.variants
        if variant.curriculum_level is not None and variant.curriculum_level > 30
    }
    assert catalog_levels <= COHORT_LEVELS
    assert not any(offered(level) for level in catalog_levels)


def test_menu_drops_untitled_and_unoffered_rows() -> None:
    rows = [
        CurriculumLevel(level=2, name="Basics", cefr="A1"),
        CurriculumLevel(level=120, name="Animals", cefr="A2"),
        CurriculumLevel(level=130, name="", cefr=None),
    ]
    assert menu_from_rows(rows) == [MenuLevel(120, "Animals", "A2")]


def test_menu_is_grouped_by_band() -> None:
    text = format_menu(MENU)
    assert text.index("Core") < text.index("8 | Everyday Things | A1")
    assert text.index("Named units") < text.index("120 | Animals | A2")
    assert text.index("Topic units") < text.index("1070 | Law | B2")


def test_context_holds_every_title_and_no_placeholders() -> None:
    context = build_context(MENU)
    assert "121 | Animals 2 | B1" in context
    assert "{{" not in context


def test_prompt_shows_word_shortlist_and_closed_core() -> None:
    shortlist = [
        ShortlistEntry(
            121,
            ("named unit with 9 animal", "corpus match: 40% ..."),
            level_size=40,
            capacity=40,
            sample_words=("otter", "weasel"),
        )
    ]
    prompt = build_prompt(
        _query(tiers=(("cefr", "B2"),)),
        shortlist,
        MENU,
        {"wiki_biology": 0.75, "wiki_geography": 0.25},
        "rank 8000 not under 5000",
    )
    assert "Word: badger" in prompt
    assert "noun / animal" in prompt
    assert "Learner lists: cefr B2" in prompt
    assert "wiki_biology 75%, wiki_geography 25%" in prompt
    assert "closed (rank 8000 not under 5000)" in prompt
    assert "121 | Animals 2 | B1 | 40/40 words (full)" in prompt
    assert "words: otter, weasel" in prompt
    assert "{{" not in prompt


def test_prompt_without_shortlist_points_at_the_full_list() -> None:
    prompt = build_prompt(_query(), [], MENU, None, None)
    assert "Core levels: open" in prompt
    assert "choose from the full list" in prompt
    assert "no corpus data" in prompt


def test_lean_of_a_general_word() -> None:
    assert "general vocabulary" in describe_lean({"general": 1.0})


CHEMISTRY_SENSE = OtherSense(
    level=1050,
    word="catalyst",
    pos_subtype="chemical_compound",
    disambiguation=None,
    definition="a substance that speeds up a reaction",
    title="Chemistry",
)


def test_lean_owned_by_another_sense_is_named_but_not_offered() -> None:
    line = describe_lean({"wiki_physical_science": 1.0}, CHEMISTRY_SENSE)
    assert line.startswith("Corpus lean: none for this sense")
    assert "catalyst (chemical_compound) sense at level 1050" in line


def test_prompt_lists_other_senses_and_an_unranked_word() -> None:
    prompt = build_prompt(_query(rank=None), [], MENU, None, None, [CHEMISTRY_SENSE])
    assert "Frequency rank: unranked" in prompt
    assert "- catalyst (chemical_compound) at 1050 Chemistry: a substance" in prompt
    assert "{{" not in prompt
    assert "Other senses of this spelling already in the course:\n(none)" in build_prompt(
        _query(), [], MENU, None, None
    )


def test_merge_interleaves_rankers_and_joins_shared_reasons() -> None:
    merged = merge_shortlist(
        [(120, "subtype"), (121, "subtype"), (999, "not offered")],
        [(1070, "corpus"), (120, "corpus")],
        MENU_LEVELS,
    )
    assert merged == [(120, ("subtype", "corpus")), (1070, ("corpus",)), (121, ("subtype",))]
    assert len(merge_shortlist([(120, "a"), (121, "b")], [(1070, "c")], MENU_LEVELS, 2)) == 2


def test_parse_accepts_a_menu_level_off_the_shortlist() -> None:
    suggestion = parse_placement(
        {"reasoning": "r", "fit": "good", "level": 121, "alternatives": [120, 121, 120]},
        MENU_LEVELS,
        [120],
        None,
    )
    assert suggestion.level == 121 and suggestion.fit == "good"
    assert suggestion.alternatives == (120,)
    assert not suggestion.from_shortlist
    assert suggestion.problems == ()


def test_parse_none_fit_parks_the_word() -> None:
    suggestion = parse_placement(
        {"reasoning": "r", "fit": "none", "level": 0, "alternatives": []}, MENU_LEVELS, [], None
    )
    assert suggestion.level is None and suggestion.problems == ()


def test_parse_discards_off_menu_and_closed_core_levels() -> None:
    off_menu = parse_placement(
        {"fit": "good", "level": 1399, "alternatives": ["x"]}, MENU_LEVELS, [], None
    )
    assert off_menu.level is None and off_menu.fit == "none"
    assert len(off_menu.problems) == 2

    closed = parse_placement(
        {"fit": "good", "level": 8, "alternatives": [120]}, MENU_LEVELS, [], "rank too low"
    )
    assert closed.level is None and closed.alternatives == (120,)
    assert "closed core" in closed.problems[0]


class _FakeResponse:
    def __init__(self, data: Dict[str, Any]) -> None:
        self.structured_data = data


class _FakeClient:
    def __init__(self, data: Dict[str, Any]) -> None:
        self.data = data
        self.calls: List[Dict[str, Any]] = []

    def generate_chat(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        return _FakeResponse(self.data)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _lemma(session: Session, text: str, level: Optional[int], subtype: str = "animal") -> Lemma:
    lemma = Lemma(
        lemma_text=text,
        definition_text=text,
        pos_type="noun",
        pos_subtype=subtype,
        difficulty_level=level,
        guid=f"N_{text}_{session.query(Lemma).count()}",
        frequency_rank=3000,
    )
    session.add(lemma)
    session.flush()
    return lemma


def test_placer_sends_titles_as_context_and_shortlists_subtype_levels() -> None:
    session = _session()
    for level, name in ((120, "Animals"), (1070, "Law")):
        session.add(CurriculumLevel(level=level, name=name, cefr="B1"))
    # Two senses of one spelling are sampled once.
    for text in ("otter", "otter", "weasel"):
        _lemma(session, text, 120)
    _lemma(session, "statute", 1070, "legal_concept")
    session.commit()

    client = _FakeClient(
        {"reasoning": "a wild mammal", "fit": "good", "level": 120, "alternatives": []}
    )
    placer = LevelPlacer(session, {120: LevelProfile(level=120)}, client)  # type: ignore[arg-type]
    suggestion = placer.place(_query())

    assert suggestion.level == 120 and suggestion.from_shortlist
    call = client.calls[0]
    assert call["json_schema"] is PLACEMENT_JSON_SCHEMA
    assert "1070 | Law | B1" in call["context"]
    assert "words: otter, weasel" in call["prompt"]
    assert "1070 | Law" not in call["prompt"]


def _catalyst_placer(match_level: int) -> tuple[LevelPlacer, PlacementQuery]:
    """A placer for the figurative catalyst whose spelling leans to ``match_level``."""
    session = _session()
    for level, name in ((290, "Events and Processes"), (1050, "Chemistry")):
        session.add(CurriculumLevel(level=level, name=name, cefr="B2"))
    _lemma(session, "catalyst", 1050, "chemical_compound")
    _lemma(session, "process", 290, "process_event")
    session.commit()

    placer = LevelPlacer(session, {}, None)
    lean = {"wiki_physical_science": 1.0}
    match = CorpusMatch(level=match_level, share=0.7, weight=90.0, lemma_count=128, lift=10.0)
    placer.word_weights = lambda query: lean  # type: ignore[method-assign]
    placer.corpus_matches = (  # type: ignore[method-assign]
        lambda weights: [match] if weights else []
    )
    query = _query(
        lemma_text="catalyst",
        pos_subtype="process_event",
        definition="something that prompts change",
        rank=None,
    )
    return placer, query


def test_lean_explained_by_another_sense_is_dropped() -> None:
    placer, query = _catalyst_placer(match_level=1050)
    prompt, shortlist, _ = placer.prepare(query)

    assert "Corpus lean: none for this sense" in prompt
    assert "- catalyst (chemical_compound) at 1050 Chemistry:" in prompt
    assert [entry.level for entry in shortlist] == [290]
    assert not any("corpus match" in reason for entry in shortlist for reason in entry.reasons)


def test_lean_pointing_elsewhere_is_kept() -> None:
    placer, query = _catalyst_placer(match_level=290)
    prompt, shortlist, _ = placer.prepare(query)

    assert "Corpus lean (of this spelling): wiki_physical_science 100%" in prompt
    assert any("corpus match" in reason for reason in shortlist[0].reasons)
