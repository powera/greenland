"""Tests for the single-word add pipeline (words.add_word).

add_word turns a bare English word into one lemma per sense worth adding. The
LLM call is stubbed here by replacing the LinguisticClient it constructs, so no
real definitions call is made -- the tests cover the logic layered on top of the
LLM: the existence guard, frequency-driven sense sizing (including the fallback
to inflected surface forms), the closed-class single-sense cap,
translation-duplicate collapse, subtype normalization, and the diversion of
catch-all ``*_other`` subtypes to the pending-import queue.
"""

from pathlib import Path
from typing import Any, Dict, Generator, List, Tuple

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from storage.backend.config import BackendType, DataSourceConfig
from storage.models import Base, Lemma, WordToken
from storage.models.imports import PendingImport
from storage.models.variant_form import VARIANT_KIND_SPELLING, VariantForm
from words import add_word as add_word_module
from words.add_word import (
    AddWordResult,
    _apply_pos_sense_cap,
    _drop_translation_duplicates,
    _MAX_TIED_SENSES,
    _REVIEW_REASON_KEY,
    _extend_for_prominence_ties,
    _review_reason,
    divergent_english_term,
    source_word_from_note,
    _inflected_candidates,
    _normalize_subtype,
    _sense_bounds,
    add_word,
)
from wordfreq.translation.definitions import select_senses_to_add


@pytest.fixture()
def db_engine(tmp_path: Path) -> Generator[Engine, None, None]:
    import storage.models  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path / 'add_word.sqlite'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def session(db_engine: Engine) -> Generator[Session, None, None]:
    factory = sessionmaker(bind=db_engine)
    db_session = factory()
    yield db_session
    db_session.close()


@pytest.fixture()
def config() -> DataSourceConfig:
    return DataSourceConfig(
        backend_type=BackendType.SQLITE, sqlite_path=":memory:", model="test-model"
    )


class _FakeClient:
    """Stand-in for LinguisticClient that returns canned definitions."""

    def __init__(self, definitions: List[Dict[str, Any]]) -> None:
        self._definitions = definitions
        self.model = "test-model"
        self.calls = 0

    def query_definitions(self, word: str, **kwargs: Any) -> Tuple[List[Dict[str, Any]], bool]:
        self.calls += 1
        return self._definitions, bool(self._definitions)


@pytest.fixture()
def patch_client(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Return a helper that installs a _FakeClient with the given definitions."""

    def _install(definitions: List[Dict[str, Any]]) -> _FakeClient:
        fake = _FakeClient(definitions)
        monkeypatch.setattr(add_word_module, "LinguisticClient", lambda config=None: fake)
        return fake

    return _install


def _def(
    definition: str,
    pos: str = "noun",
    pos_subtype: str = "animal",
    prominence: str = "common",
    **translations: str,
) -> Dict[str, Any]:
    """Build one LLM definition dict. Translation kwargs use LLM field names."""
    entry: Dict[str, Any] = {
        "definition": definition,
        "pos": pos,
        "pos_subtype": pos_subtype,
        "sense_prominence": prominence,
        "lithuanian_translation": "vertimas",
        "spanish_translation": "traducción",
        "spanish_latam_translation": "traducción",
        "french_translation": "traduction",
        "chinese_translation": "翻译",
    }
    entry.update(translations)
    return entry


def _senses(*pairs: Tuple[str, str]) -> List[Dict[str, Any]]:
    """Build a definitions list from (definition, prominence) pairs."""
    return [{"definition": text, "sense_prominence": prominence} for text, prominence in pairs]


def _seed_word_token(session: Session, token: str, rank: int) -> None:
    session.add(WordToken(token=token, language_code="en", frequency_rank=rank))
    session.commit()


# --- Pure helpers -----------------------------------------------------------


def test_sense_bounds_by_rank() -> None:
    # min stays 1 at every rank: sense_prominence, not word frequency, decides
    # whether a second sense is added. Frequency only raises the max.
    assert _sense_bounds(500) == (1, 4)
    assert _sense_bounds(2000) == (1, 4)
    assert _sense_bounds(2001) == (1, 3)
    assert _sense_bounds(10000) == (1, 3)
    assert _sense_bounds(10001) == (1, 2)
    assert _sense_bounds(None) == (1, 2)


def _select_and_extend(defs: List[Dict[str, Any]], max_senses: int) -> List[str]:
    """Run add_word's ceiling + tie-extension over a definitions list."""
    selected = select_senses_to_add(defs, max_senses=max_senses, min_senses=1)
    extended = _extend_for_prominence_ties(selected, defs)
    return [sense["definition"] for sense in extended]


def test_tie_extension_cuts_between_prominence_tiers() -> None:
    # 2 very_common + 2 common, ceiling 2: the cut lands between tiers, so keep
    # only the two very_common and drop the commons.
    defs = _senses(
        ("a", "very_common"),
        ("b", "very_common"),
        ("c", "common"),
        ("d", "common"),
    )
    assert _select_and_extend(defs, max_senses=2) == ["a", "b"]


def test_tie_extension_keeps_whole_common_tier() -> None:
    # 1 very_common + 4 common, ceiling 3: the cut lands inside the common tier,
    # so include all five rather than dropping one common for list position.
    defs = _senses(
        ("a", "very_common"),
        ("b", "common"),
        ("c", "common"),
        ("d", "common"),
        ("e", "common"),
    )
    assert _select_and_extend(defs, max_senses=3) == ["a", "b", "c", "d", "e"]


def test_tie_extension_never_reaches_uncommon() -> None:
    # A prominent sense plus uncommon ones: the boundary tier is very_common,
    # so nothing is pulled in and the uncommons stay dropped.
    defs = _senses(
        ("a", "very_common"),
        ("b", "uncommon"),
        ("c", "uncommon"),
    )
    assert _select_and_extend(defs, max_senses=3) == ["a"]


def test_oversized_tie_is_marked_for_review() -> None:
    # 1 very_common + 7 common against a ceiling of 4 is what "further" produced:
    # too wide to be a real tie, so every sense in the tier is marked for review
    # rather than imported on list position. The very_common sense is untouched.
    defs = _senses(
        ("a", "very_common"),
        ("b", "common"),
        ("c", "common"),
        ("d", "common"),
        ("e", "common"),
        ("f", "common"),
        ("g", "common"),
        ("h", "common"),
    )
    selected = select_senses_to_add(defs, max_senses=4, min_senses=1)
    extended = _extend_for_prominence_ties(selected, defs)

    assert [sense["definition"] for sense in extended] == list("abcdefgh")
    assert _REVIEW_REASON_KEY not in extended[0]
    for sense in extended[1:]:
        assert _REVIEW_REASON_KEY in sense
    assert _review_reason(extended[0], "adjective", "quality", "word") is None
    assert _review_reason(extended[1], "adjective", "quality", "word") is not None


def test_tie_at_the_limit_still_imports() -> None:
    # Exactly _MAX_TIED_SENSES in the tier is a tie, not a failure to rank.
    defs = _senses(("a", "very_common"), *[(letter, "common") for letter in "bcdef"])
    selected = select_senses_to_add(defs, max_senses=4, min_senses=1)
    extended = _extend_for_prominence_ties(selected, defs)

    assert len([s for s in extended if s["sense_prominence"] == "common"]) == _MAX_TIED_SENSES
    assert all(_REVIEW_REASON_KEY not in sense for sense in extended)


def test_review_reason_reports_the_subtype_trigger() -> None:
    # The pre-existing *_other trigger is unchanged and still fires on its own.
    assert _review_reason({}, "noun", "noun_other", "word") is not None
    assert _review_reason({}, "noun", "human", "word") is None
    # Closed-class *_other is ordinary, not a review trigger.
    assert _review_reason({}, "preposition", "preposition_other", "word") is None


def test_divergent_english_term_detects_a_different_headword() -> None:
    # The queried token is only how we got here; english_translation names the
    # sense. "gas" for the motor-fuel sense is really "gasoline".
    assert divergent_english_term({"english_translation": "gasoline"}, "gas") == "gasoline"
    # Same word is not divergence, whatever its case or surrounding space.
    assert divergent_english_term({"english_translation": "gas"}, "gas") is None
    assert divergent_english_term({"english_translation": "Gas"}, "gas") is None
    assert divergent_english_term({"english_translation": "  gas  "}, "gas") is None
    # An absent or empty field is not a divergence claim: senses predating the
    # schema field must keep importing normally rather than all going to review.
    assert divergent_english_term({}, "gas") is None
    assert divergent_english_term({"english_translation": ""}, "gas") is None


def test_divergent_english_term_routes_to_review() -> None:
    # A divergence is a signal to have a human look, not a licence to rename:
    # the LLM returns real clippings ("gasoline") and bare synonyms ("twice"
    # for "double") in the same field, and they are not separable here.
    reason = _review_reason({"english_translation": "gasoline"}, "noun", "chemical_compound", "gas")
    assert reason is not None
    # The reason names both terms so the reviewer sees the proposed headword.
    assert "gasoline" in reason and "gas" in reason
    # PendingImport has no column for the word a row was queued from, so the
    # note is the only record of it. Attaching "gas" as a variant of the
    # approved "gasoline" is not built yet and will need to recover it.
    assert source_word_from_note(f"add_word: {reason}") == "gas"
    # A sense whose English term is the queried word imports as before.
    assert (
        _review_reason({"english_translation": "gas"}, "noun", "material_substance", "gas") is None
    )


def test_source_word_is_not_recovered_from_other_pending_rows() -> None:
    # Only a divergent row carries a source word. A row queued for a subtype or
    # a prominence tie was queued under the word itself, so there is no variant
    # to consider and the parser must not invent one.
    assert source_word_from_note("add_word: noun_other needs subtype review before import") is None
    assert source_word_from_note("Found in top frequency words") is None
    assert source_word_from_note(None) is None
    assert source_word_from_note("") is None


def test_numeral_without_a_valid_subtype_goes_to_review() -> None:
    # "numeral" is the one POS with no *_other catch-all, so the prompt's
    # "return the part-of-speech as the subtype" instruction yields an unusable
    # value. It must reach review rather than failing the word (the HTTP 400
    # "invalid pos_subtype 'numeral' for 'numeral'" that halted the 'hundred'
    # import), and rather than being guessed as cardinal or ordinal.
    assert _normalize_subtype("numeral", "numeral") == "numeral"
    assert _review_reason({}, "numeral", "numeral", "word") is not None
    # A subtype the LLM did get right imports normally.
    assert _review_reason({}, "numeral", "cardinal", "word") is None
    assert _review_reason({}, "numeral", "ordinal", "word") is None


def test_closed_class_capped_to_one_sense() -> None:
    senses = [
        {"pos": "conjunction", "definition": "except on the condition that"},
        {"pos": "conjunction", "definition": "if not"},
    ]
    kept, dropped = _apply_pos_sense_cap(senses)
    assert len(kept) == 1
    assert kept[0]["definition"] == "except on the condition that"
    assert len(dropped) == 1


def test_open_class_not_capped() -> None:
    senses = [
        {"pos": "noun", "definition": "a financial institution"},
        {"pos": "noun", "definition": "the side of a river"},
    ]
    kept, dropped = _apply_pos_sense_cap(senses)
    assert len(kept) == 2
    assert dropped == []


def test_translation_duplicates_collapsed() -> None:
    senses = [
        _def("keep happening", pos="verb", lithuanian_translation="tęsti"),
        _def("make something keep happening", pos="verb", lithuanian_translation="tęsti"),
    ]
    kept, collapsed = _drop_translation_duplicates(senses)
    assert len(kept) == 1
    assert len(collapsed) == 1


def test_accent_differences_collapse() -> None:
    """An accent apart is the same word: "proteger" vs "protéger"."""
    senses = [
        _def("to watch over", pos="verb", spanish_translation="proteger"),
        _def("to prevent harm", pos="verb", spanish_translation="protéger"),
    ]
    kept, collapsed = _drop_translation_duplicates(senses)
    assert len(kept) == 1
    assert len(collapsed) == 1


def test_prefix_differences_collapse() -> None:
    """The TODO's case: lt marks aspect with a prefix, so these are one sense."""
    senses = [
        _def("to watch over", pos="verb", lithuanian_translation="saugoti"),
        _def("to prevent harm", pos="verb", lithuanian_translation="apsaugoti"),
    ]
    kept, collapsed = _drop_translation_duplicates(senses)
    assert len(kept) == 1
    assert len(collapsed) == 1


def test_genuinely_distinct_senses_survive() -> None:
    """Regression guard from the TODO: "further" must not be over-merged.

    D08_001 (distance) and D09_010 (intensity) are a real English split. Their
    translations differ outright in every language, so unanimity keeps them.
    """
    senses = [
        _def(
            "at a greater distance",
            pos="adverb",
            lithuanian_translation="toliau",
            spanish_translation="más lejos",
            french_translation="plus loin",
        ),
        _def(
            "to a greater extent",
            pos="adverb",
            lithuanian_translation="labiau",
            spanish_translation="más",
            french_translation="davantage",
        ),
    ]
    kept, collapsed = _drop_translation_duplicates(senses)
    assert len(kept) == 2
    assert collapsed == []


def test_unrelated_words_are_not_merged_by_the_prefix_rule() -> None:
    """The tolerance must not swallow words that merely share an ending."""
    senses = [
        _def("a small animal", pos="noun", lithuanian_translation="katinas"),
        _def("a large animal", pos="noun", lithuanian_translation="arklys"),
    ]
    kept, collapsed = _drop_translation_duplicates(senses)
    assert len(kept) == 2
    assert collapsed == []


def test_partial_translation_agreement_does_not_collapse() -> None:
    """Every language must agree; one matching language is not enough."""
    senses = [
        _def(
            "sense one",
            pos="verb",
            lithuanian_translation="saugoti",
            spanish_translation="proteger",
        ),
        _def(
            "sense two",
            pos="verb",
            lithuanian_translation="apsaugoti",
            spanish_translation="vigilar",
        ),
    ]
    kept, collapsed = _drop_translation_duplicates(senses)
    assert len(kept) == 2
    assert collapsed == []


def test_normalize_subtype_closed_class() -> None:
    assert _normalize_subtype("preposition", "preposition") == "preposition_other"
    assert _normalize_subtype("conjunction", "other") == "conjunction_other"
    assert _normalize_subtype("noun", "concept_idea") == "concept_idea"


def test_normalize_subtype_replaces_cross_pos_value_with_other() -> None:
    assert _normalize_subtype("adjective", "completeness") == "adjective_other"
    assert _normalize_subtype("preposition", "location") == "preposition_other"


# --- add_word end to end ----------------------------------------------------


def test_add_word_creates_lemma(
    session: Session, config: DataSourceConfig, patch_client: Any
) -> None:
    fake = patch_client(
        [
            _def(
                "a domesticated carnivore",
                pos="noun",
                pos_subtype="animal",
                lithuanian_translation="šuo",
                spanish_translation="perro",
                spanish_latam_translation="perro",
                french_translation="chien",
                chinese_translation="狗",
            )
        ]
    )
    _seed_word_token(session, "dog", rank=300)

    result = add_word(session, "dog", config=config)

    assert isinstance(result, AddWordResult)
    assert result.status == "created"
    assert result.frequency_rank == 300
    assert len(result.senses) == 1
    assert fake.calls == 1

    lemma = session.query(Lemma).filter(Lemma.lemma_text == "dog").one()
    assert lemma.pos_type == "noun"
    assert lemma.difficulty_level == -1
    assert result.senses[0].translations.get("lt") == "šuo"
    assert result.senses[0].translations == {
        "lt": "šuo",
        "es": "perro",
        "es-419": "perro",
        "fr": "chien",
        "zh": "狗",
    }
    assert len(lemma.derivative_forms) == 1
    assert lemma.derivative_forms[0].derivative_form_text == "dog"
    assert lemma.derivative_forms[0].grammatical_form == "noun/en_singular"
    assert lemma.derivative_forms[0].is_base_form is True
    assert lemma.derivative_forms[0].word_token_id is not None


def test_add_word_skips_existing_lemma(
    session: Session, config: DataSourceConfig, patch_client: Any
) -> None:
    session.add(
        Lemma(lemma_text="cat", definition_text="a small feline", pos_type="noun", guid="N01_001")
    )
    session.commit()
    fake = patch_client([_def("a small feline", pos="noun")])

    result = add_word(session, "cat", config=config)

    assert result.status == "already_exists"
    assert result.senses == []
    # The existence guard must short-circuit before any LLM call.
    assert fake.calls == 0


def test_add_word_skips_spelling_variant(
    session: Session, config: DataSourceConfig, patch_client: Any
) -> None:
    lemma = Lemma(lemma_text="gray", definition_text="a color", pos_type="noun", guid="N01_002")
    session.add(lemma)
    session.flush()
    session.add(
        VariantForm(
            lemma_id=lemma.id,
            variant_form_text="grey",
            language_code="en",
            variant_kind=VARIANT_KIND_SPELLING,
            variant_key="grey",
            grammatical_form="noun/en_singular",
            is_base_form=True,
        )
    )
    session.commit()
    fake = patch_client([_def("a color", pos="noun")])

    result = add_word(session, "grey", config=config)

    assert result.status == "already_exists"
    assert fake.calls == 0


def test_add_word_all_very_common_senses_kept(
    session: Session, config: DataSourceConfig, patch_client: Any
) -> None:
    # Three equally very_common senses on a rare word (max 2): all three are
    # kept, because a very_common sense is never dropped for list position -- the
    # ceiling only bounds lower tiers.
    patch_client(
        [
            _def(
                "first sense",
                pos="noun",
                prominence="very_common",
                lithuanian_translation="pirmas",
            ),
            _def(
                "second sense",
                pos="noun",
                prominence="very_common",
                lithuanian_translation="antras",
            ),
            _def(
                "third sense",
                pos="noun",
                prominence="very_common",
                lithuanian_translation="trečias",
            ),
        ]
    )

    result = add_word(session, "obscureword", config=config)

    assert result.status == "created"
    assert len(result.senses) == 3


def test_add_word_frequent_word_with_one_real_sense(
    session: Session, config: DataSourceConfig, patch_client: Any
) -> None:
    # A very common word (rank < 2000) whose only prominent meaning is one
    # sense, plus a rare sense. Frequency must NOT force the rare sense in --
    # sense_prominence decides, so this yields a single lemma.
    patch_client(
        [
            _def("the animal", pos="noun", prominence="very_common"),
            _def("an obscure technical meaning", pos="noun", prominence="rare"),
        ]
    )
    _seed_word_token(session, "dog", rank=200)

    result = add_word(session, "dog", config=config)

    assert result.status == "created"
    assert result.frequency_rank == 200
    assert len(result.senses) == 1
    assert result.senses[0].definition_text == "the animal"


def test_add_word_frequent_word_keeps_multiple_prominent_senses(
    session: Session, config: DataSourceConfig, patch_client: Any
) -> None:
    # A common, genuinely polysemous word: two prominent senses both survive
    # because they are "common", and the high frequency raises the ceiling.
    patch_client(
        [
            _def(
                "hit forcibly", pos="verb", pos_subtype="physical_action", prominence="very_common"
            ),
            _def("a work stoppage", pos="noun", pos_subtype="animal", prominence="common"),
        ]
    )
    _seed_word_token(session, "strike", rank=800)

    result = add_word(session, "strike", config=config)

    assert result.status == "created"
    assert len(result.senses) == 2


def test_add_word_closed_class_single_sense(
    session: Session, config: DataSourceConfig, patch_client: Any
) -> None:
    patch_client(
        [
            _def(
                "except on the condition that", pos="conjunction", pos_subtype="conjunction_other"
            ),
            _def("if not", pos="conjunction", pos_subtype="conjunction_other"),
        ]
    )
    _seed_word_token(session, "unless", rank=400)

    result = add_word(session, "unless", config=config)

    assert result.status == "created"
    assert len(result.senses) == 1
    assert session.query(Lemma).filter(Lemma.lemma_text == "unless").count() == 1


def test_add_word_no_definitions(
    session: Session, config: DataSourceConfig, patch_client: Any
) -> None:
    patch_client([])

    result = add_word(session, "zzznotaword", config=config)

    assert result.status == "no_definitions"


def test_add_word_rejects_a_selected_sense_with_a_missing_target_translation(
    session: Session, config: DataSourceConfig, patch_client: Any
) -> None:
    incomplete = _def("a domesticated carnivore", pos="noun", pos_subtype="animal")
    incomplete["spanish_latam_translation"] = ""
    patch_client([incomplete])

    result = add_word(session, "dog", config=config)

    assert result.status == "error"
    assert result.error is not None
    assert "es-419" in result.error
    assert session.query(Lemma).filter(Lemma.lemma_text == "dog").count() == 0
    assert result.senses == []


# --- Frequency rank falls back to inflected forms ---------------------------


def test_inflected_candidates_are_pos_directed() -> None:
    """Each POS gets only its own inflections; closed-class gets none.

    This is the guard against the whole point of the POS-directed lookup: a
    blind generator would offer "exclaimer" for a verb and "guards" for both a
    noun and a verb.
    """
    assert set(_inflected_candidates("exclaim", "verb")) == {
        "exclaims",
        "exclaimed",
        "exclaiming",
    }
    assert _inflected_candidates("guard", "noun") == ["guards"]
    assert set(_inflected_candidates("merry", "adjective")) == {"merrier", "merriest"}
    assert _inflected_candidates("within", "preposition") == []


def test_rank_falls_back_to_an_inflected_form(
    session: Session, config: DataSourceConfig, patch_client: Any
) -> None:
    """The TODO's case: the corpus holds "exclaimed", not "exclaim"."""
    patch_client([_def("to cry out suddenly", pos="verb", pos_subtype="communication")])
    _seed_word_token(session, "exclaimed", rank=1500)

    result = add_word(session, "exclaim", config=config)

    assert result.frequency_rank == 1500
    assert result.frequency_rank_source == "exclaimed"


def test_exact_form_beats_an_inflected_match(
    session: Session, config: DataSourceConfig, patch_client: Any
) -> None:
    """A rank for the word itself always wins, even if an inflection ranks better."""
    patch_client([_def("to watch over", pos="verb", pos_subtype="physical_action")])
    _seed_word_token(session, "guard", rank=900)
    _seed_word_token(session, "guarded", rank=100)

    result = add_word(session, "guard", config=config)

    assert result.frequency_rank == 900
    assert result.frequency_rank_source == "guard"


def test_wrong_pos_inflection_is_not_consulted(
    session: Session, config: DataSourceConfig, patch_client: Any
) -> None:
    """A verb must not pick up the adjective comparative "exclaimer".

    Without POS-directed candidates this token would be found, and because a
    lower rank means *more* frequent, it would silently widen the sense ceiling.
    """
    patch_client([_def("to cry out suddenly", pos="verb", pos_subtype="communication")])
    _seed_word_token(session, "exclaimer", rank=50)

    result = add_word(session, "exclaim", config=config)

    assert result.frequency_rank is None
    assert result.frequency_rank_source is None


def test_inflected_rank_widens_the_sense_ceiling(
    session: Session, config: DataSourceConfig, patch_client: Any
) -> None:
    """The rank is only worth recovering because it sizes sense selection.

    Four very_common senses with no rank are capped at 2 by the fallback band;
    the same senses at rank 500 are allowed 4.
    """
    definitions = [
        _def(
            f"sense {n}",
            pos="verb",
            pos_subtype="physical_action",
            prominence="very_common",
            lithuanian_translation=f"vertimas {n}",
        )
        for n in range(4)
    ]
    patch_client(definitions)
    _seed_word_token(session, "guarded", rank=500)

    result = add_word(session, "guard", config=config)

    assert result.frequency_rank == 500
    assert result.frequency_rank_source == "guarded"
    assert len(result.senses) == 4


def test_irregular_inflections_are_not_reached(
    session: Session, config: DataSourceConfig, patch_client: Any
) -> None:
    """Known limitation: the candidates are rule-based, so "struck" is missed.

    ``generate_past_tense("strike")`` gives "striked". Recovering irregular
    forms would need the conjugation tables, which is a larger change; the
    fallback is documented as best-effort and simply finds nothing here.
    """
    patch_client([_def("to hit forcefully", pos="verb", pos_subtype="physical_action")])
    _seed_word_token(session, "struck", rank=500)

    result = add_word(session, "strike", config=config)

    assert result.frequency_rank is None
    assert result.status == "created"  # still added, just unsized


def test_no_definitions_skips_the_frequency_lookup(
    session: Session, config: DataSourceConfig, patch_client: Any
) -> None:
    """No POS means no rank: the lookup needs one to pick candidates."""
    patch_client([])
    _seed_word_token(session, "zzznotaword", rank=10)

    result = add_word(session, "zzznotaword", config=config)

    assert result.status == "no_definitions"
    assert result.frequency_rank is None


# --- *_other subtypes are diverted to the pending queue ---------------------


def test_other_subtype_on_open_class_is_queued_not_written(
    session: Session, config: DataSourceConfig, patch_client: Any
) -> None:
    patch_client(
        [
            _def(
                "to watch over and protect",
                pos="verb",
                pos_subtype="verb_other",
                lithuanian_translation="saugoti",
            )
        ]
    )

    result = add_word(session, "guard", config=config)

    assert result.status == "pending_review"
    assert result.senses == []
    assert session.query(Lemma).filter(Lemma.lemma_text == "guard").count() == 0

    pending = session.query(PendingImport).filter(PendingImport.english_word == "guard").all()
    assert len(pending) == 1
    assert pending[0].pos_subtype == "verb_other"
    assert pending[0].disambiguation_translation == "saugoti"

    assert len(result.pending_senses) == 1
    assert result.pending_senses[0].guid == ""


def test_cross_pos_subtype_on_open_class_is_queued_as_other(
    session: Session, config: DataSourceConfig, patch_client: Any
) -> None:
    patch_client(
        [
            _def(
                "forming an entire or complete thing",
                pos="adjective",
                pos_subtype="completeness",
                lithuanian_translation="visas",
            )
        ]
    )

    result = add_word(session, "whole", config=config)

    assert result.status == "pending_review"
    assert result.senses == []
    assert session.query(Lemma).filter(Lemma.lemma_text == "whole").count() == 0

    pending = session.query(PendingImport).filter(PendingImport.english_word == "whole").one()
    assert pending.pos_type == "adjective"
    assert pending.pos_subtype == "adjective_other"


def test_other_subtype_on_closed_class_is_still_written(
    session: Session, config: DataSourceConfig, patch_client: Any
) -> None:
    """The only preposition subtype is "preposition_other" -- not a review signal."""
    patch_client([_def("inside the limits of", pos="preposition", pos_subtype="preposition_other")])

    result = add_word(session, "within", config=config)

    assert result.status == "created"
    assert len(result.senses) == 1
    lemma = session.query(Lemma).filter(Lemma.lemma_text == "within").one()
    assert len(lemma.derivative_forms) == 1
    assert lemma.derivative_forms[0].grammatical_form == "preposition/base"
    assert lemma.derivative_forms[0].word_token is not None
    assert lemma.derivative_forms[0].word_token.token == "within"
    assert session.query(PendingImport).count() == 0


def test_mixed_senses_both_write_and_queue(
    session: Session, config: DataSourceConfig, patch_client: Any
) -> None:
    """A word can create some lemmas and queue others; status stays "created"."""
    patch_client(
        [
            _def(
                "a person who watches over",
                pos="noun",
                pos_subtype="human",
                lithuanian_translation="sargas",
            ),
            _def(
                "an unplaceable sense",
                pos="noun",
                pos_subtype="noun_other",
                lithuanian_translation="kita",
            ),
        ]
    )
    _seed_word_token(session, "guard", rank=500)

    result = add_word(session, "guard", config=config)

    assert result.status == "created"
    assert len(result.senses) == 1
    assert len(result.pending_senses) == 1
    assert session.query(Lemma).filter(Lemma.lemma_text == "guard").count() == 1
    assert session.query(PendingImport).filter(PendingImport.english_word == "guard").count() == 1


def test_queued_sense_falls_back_to_definition_for_disambiguation(
    session: Session, config: DataSourceConfig, patch_client: Any
) -> None:
    """disambiguation_translation is NOT NULL, so it needs a fallback."""
    patch_client(
        [
            _def(
                "an unplaceable sense",
                pos="noun",
                pos_subtype="noun_other",
                lithuanian_translation="",
            )
        ]
    )

    add_word(session, "guard", config=config)

    pending = session.query(PendingImport).filter(PendingImport.english_word == "guard").one()
    assert pending.disambiguation_translation == "an unplaceable sense"


def test_queueing_the_same_sense_twice_is_not_duplicated(
    session: Session, config: DataSourceConfig, patch_client: Any
) -> None:
    """Re-running a word must not stack duplicate rows in the review queue."""
    definitions = [_def("an unplaceable sense", pos="noun", pos_subtype="noun_other")]
    patch_client(definitions)
    add_word(session, "guard", config=config)

    patch_client(definitions)
    result = add_word(session, "guard", config=config)

    assert session.query(PendingImport).filter(PendingImport.english_word == "guard").count() == 1
    assert result.pending_senses == []
    assert any("already in the pending queue" in entry for entry in result.dropped_senses)
