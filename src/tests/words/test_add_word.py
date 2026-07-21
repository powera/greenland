"""Tests for the single-word add pipeline (words.add_word).

add_word turns a bare English word into one lemma per sense worth adding. The
LLM call is stubbed here by replacing the LinguisticClient it constructs, so no
real definitions call is made -- the tests cover the logic layered on top of the
LLM: the existence guard, frequency-driven sense sizing, the closed-class
single-sense cap, translation-duplicate collapse, and subtype normalization.
"""

from pathlib import Path
from typing import Any, Dict, Generator, List, Tuple

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from storage.backend.config import BackendType, DataSourceConfig
from storage.models import Base, Lemma, WordToken
from storage.models.variant_form import VARIANT_KIND_SPELLING, VariantForm
from words import add_word as add_word_module
from words.add_word import (
    AddWordResult,
    _apply_pos_sense_cap,
    _drop_translation_duplicates,
    _extend_for_prominence_ties,
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


def test_normalize_subtype_closed_class() -> None:
    assert _normalize_subtype("preposition", "preposition") == "preposition_other"
    assert _normalize_subtype("conjunction", "other") == "conjunction_other"
    assert _normalize_subtype("noun", "abstract") == "abstract"


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
            _def("first sense", pos="noun", prominence="very_common"),
            _def("second sense", pos="noun", prominence="very_common"),
            _def("third sense", pos="noun", prominence="very_common"),
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


def test_add_word_dry_run_writes_nothing(
    session: Session, config: DataSourceConfig, patch_client: Any
) -> None:
    patch_client([_def("a domesticated carnivore", pos="noun", pos_subtype="animal")])
    _seed_word_token(session, "dog", rank=300)

    result = add_word(session, "dog", config=config, dry_run=True)

    assert result.status == "created"
    assert len(result.senses) == 1
    assert session.query(Lemma).filter(Lemma.lemma_text == "dog").count() == 0


def test_add_word_no_definitions(
    session: Session, config: DataSourceConfig, patch_client: Any
) -> None:
    patch_client([])

    result = add_word(session, "zzznotaword", config=config)

    assert result.status == "no_definitions"
    assert result.senses == []
