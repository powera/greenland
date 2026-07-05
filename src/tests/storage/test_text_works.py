"""Tests for the text-works system (the story library).

Covers the type vocabulary partition, TextWork/TextVersion CRUD and its three
invariants (single canonical version, slot uniqueness, canonical license),
Q-id handling (unique work Q-id, non-unique attribution Q-id), the query
layer, and the create-from-Q-id service (idempotency, deferred quote intake).
"""

from __future__ import annotations

from typing import Iterator, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import storage.text_work_service as text_work_service
from storage.crud.text_work import (
    create_text_version,
    create_text_work,
    delete_text_version,
    delete_text_work,
    get_text_version_for_slot,
    get_text_work_by_qid,
    get_text_work_by_slug,
    update_text_version,
    update_text_work,
)
from storage.models.schema import Base
from storage.models.text_work import (
    ALL_TEXT_TYPES,
    AUTHORED_TEXT_TYPES,
    CANONICAL_TEXT_TYPES,
    INTAKE_DEFERRED_TEXT_TYPES,
    TEXT_TYPE_GROUPS,
    TextVersion,
    TextWork,
    is_authored_text_type,
    is_canonical_text_type,
    is_intake_deferred_text_type,
)
from storage.queries.text_work import (
    count_text_works,
    list_text_works,
    list_text_works_attributed_to,
)
from storage.text_work_service import create_text_work_from_qid
from storage.wikidata import WikidataConceptSeed


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


def _make_work(
    session: Session, title: str = "The Three Billy Goats Gruff", text_type: str = "folk_tale"
) -> TextWork:
    work = create_text_work(session, title, text_type)
    assert work is not None
    return work


# --- Vocabulary ------------------------------------------------------------------


def test_text_type_vocabulary_partition() -> None:
    assert set(AUTHORED_TEXT_TYPES).isdisjoint(CANONICAL_TEXT_TYPES)
    assert ALL_TEXT_TYPES == AUTHORED_TEXT_TYPES + CANONICAL_TEXT_TYPES
    assert set(INTAKE_DEFERRED_TEXT_TYPES) <= set(ALL_TEXT_TYPES)
    assert "quote" in CANONICAL_TEXT_TYPES
    assert "conversation" in AUTHORED_TEXT_TYPES
    grouped = tuple(t for _label, types in TEXT_TYPE_GROUPS for t in types)
    assert grouped == ALL_TEXT_TYPES

    assert is_authored_text_type("fable")
    assert not is_authored_text_type("poem")
    assert is_canonical_text_type("song")
    assert is_intake_deferred_text_type("quote")
    assert not is_intake_deferred_text_type("poem")


# --- Work CRUD -------------------------------------------------------------------


def test_create_text_work_validates_type(session: Session) -> None:
    assert create_text_work(session, "Some Story", "not_a_type") is None
    # Reserved-but-deferred types are refused at intake.
    assert create_text_work(session, "Veni vidi vici", "quote") is None

    work = _make_work(session)
    assert work.slug == "The_Three_Billy_Goats_Gruff"
    assert work.title == "The Three Billy Goats Gruff"
    assert work.is_authored

    # Duplicate slug (space/underscore-equivalent) is refused.
    assert create_text_work(session, "The Three Billy  Goats Gruff", "fable") is None
    assert create_text_work(session, "", "fable") is None


def test_create_text_work_normalizes_and_uniques_qid(session: Session) -> None:
    work = create_text_work(session, "The Gingerbread Man", "folk_tale", qid="q1210136")
    assert work is not None
    assert work.qid == "Q1210136"
    assert get_text_work_by_qid(session, "q1210136") == work

    # The work Q-id is unique across the library.
    assert create_text_work(session, "Another Tale", "folk_tale", qid="Q1210136") is None
    # Invalid Q-ids are refused rather than stored raw.
    assert create_text_work(session, "Bad Qid Tale", "folk_tale", qid="Quebec") is None


def test_attribution_qid_is_not_unique(session: Session) -> None:
    first = create_text_work(session, "The Road Not Taken", "poem", attribution_qid="Q168728")
    second = create_text_work(session, "Fire and Ice", "poem", attribution_qid="q168728")
    assert first is not None and second is not None
    assert first.attribution_qid == second.attribution_qid == "Q168728"

    attributed = list_text_works_attributed_to(session, "Q168728")
    assert attributed == [second, first]  # ordered by slug
    assert list_text_works_attributed_to(session, "bogus") == []


def test_update_text_work_guards(session: Session) -> None:
    work = create_text_work(session, "The Raven", "poem", attribution="Edgar Allan Poe")
    assert work is not None
    version = create_text_version(
        session,
        work,
        body="Once upon a midnight dreary...",
        is_canonical=True,
        license="public-domain",
    )
    assert version is not None

    # A canonical version pins the work to canonical types.
    assert update_text_work(session, work, text_type="folk_tale") is None
    assert update_text_work(session, work, text_type="song") is not None
    assert update_text_work(session, work, text_type="quote") is None  # deferred

    # Q-id set/clear semantics.
    updated = update_text_work(session, work, qid="q170494")
    assert updated is not None and updated.qid == "Q170494"
    assert update_text_work(session, work, qid="not-a-qid") is None
    cleared = update_text_work(session, work, qid=None)
    assert cleared is not None and cleared.qid is None

    # Renaming onto an existing slug is refused.
    other = _make_work(session)
    assert update_text_work(session, other, title="The Raven") is None


def test_delete_text_work_cascades_versions(session: Session) -> None:
    work = _make_work(session)
    assert create_text_version(session, work, body="Once upon a time...") is not None
    assert create_text_version(session, work, body="Simpler.", difficulty_level=2) is not None
    assert session.query(TextVersion).count() == 2

    assert delete_text_work(session, work)
    assert get_text_work_by_slug(session, "The_Three_Billy_Goats_Gruff") is None
    assert session.query(TextVersion).count() == 0


# --- Version invariants ------------------------------------------------------------


def test_version_lang_is_english_only_for_now(session: Session) -> None:
    work = _make_work(session)
    assert create_text_version(session, work, lang="lt", body="Kartą...") is None
    assert create_text_version(session, work, lang="en", body="Once...") is not None


def test_canonical_version_invariants(session: Session) -> None:
    fable = _make_work(session)
    poem = create_text_work(session, "Ozymandias", "poem")
    assert poem is not None

    # Invariant 1a: authored-type works never hold a canonical version.
    assert create_text_version(session, fable, body="x", is_canonical=True, license="pd") is None

    # Invariant 3: canonical versions require a license.
    assert (
        create_text_version(session, poem, body="I met a traveller...", is_canonical=True) is None
    )
    canonical = create_text_version(
        session,
        poem,
        body="I met a traveller...",
        is_canonical=True,
        license="public-domain",
        difficulty_level=None,
    )
    assert canonical is not None
    assert poem.canonical_version == canonical

    # Invariant 1b: at most one canonical version per work (different slot too).
    assert (
        create_text_version(
            session, poem, body="alt", is_canonical=True, license="pd", difficulty_level=3
        )
        is None
    )

    # The license cannot be blanked on a canonical version.
    assert update_text_version(session, canonical, license="  ") is None
    assert update_text_version(session, canonical, license="CC0") is not None


def test_version_slot_uniqueness(session: Session) -> None:
    work = _make_work(session)
    reference = create_text_version(session, work, body="Once upon a time...")
    assert reference is not None

    # Same (lang, NULL-difficulty) slot is occupied.
    assert create_text_version(session, work, body="again") is None
    assert get_text_version_for_slot(session, work, "en", None) == reference

    # A difficulty-targeted telling is its own slot...
    easy = create_text_version(session, work, body="Simple words.", difficulty_level=2)
    assert easy is not None
    # ...but only one per level.
    assert create_text_version(session, work, body="again", difficulty_level=2) is None

    # Moving a version onto an occupied slot is refused; a free slot works.
    assert update_text_version(session, easy, difficulty_level=None) is None
    moved = update_text_version(session, easy, difficulty_level=3)
    assert moved is not None and moved.difficulty_level == 3

    assert delete_text_version(session, reference)
    assert get_text_version_for_slot(session, work, "en", None) is None


# --- Queries ---------------------------------------------------------------------


def test_list_and_count_text_works(session: Session) -> None:
    _make_work(session)
    create_text_work(session, "The Gingerbread Man", "folk_tale")
    create_text_work(session, "Ozymandias", "poem", attribution="Percy Bysshe Shelley")

    assert count_text_works(session) == 3
    assert count_text_works(session, text_type="poem") == 1
    assert [w.slug for w in list_text_works(session, search="billy goats")] == [
        "The_Three_Billy_Goats_Gruff"
    ]
    # Attribution is searchable too.
    assert [w.slug for w in list_text_works(session, search="Shelley")] == ["Ozymandias"]
    assert list_text_works(session, limit=1, offset=1)[0].slug == "The_Gingerbread_Man"


# --- Service ---------------------------------------------------------------------


def _fake_seed_fetcher(title: str, summary: str = "a summary"):
    def fetch(qid: str, **_kwargs: object) -> Optional[WikidataConceptSeed]:
        return WikidataConceptSeed(qid=qid, title=title, summary=summary, sources=[])

    return fetch


def test_create_text_work_from_qid(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        text_work_service,
        "fetch_wikidata_concept_seed",
        _fake_seed_fetcher(
            "The Three Billy Goats Gruff", "A troll under a bridge meets three goats."
        ),
    )

    result = create_text_work_from_qid(session, "q727946", "folk_tale")
    assert result.ok
    assert result.work is not None
    assert result.work.qid == "Q727946"
    assert result.work.summary == "A troll under a bridge meets three goats."

    # Idempotent on Q-id.
    again = create_text_work_from_qid(session, "Q727946", "folk_tale")
    assert again.status == "exists"
    assert again.work == result.work

    # Idempotent on seeded title (different Q-id, same title).
    same_title = create_text_work_from_qid(session, "Q999999", "folk_tale")
    assert same_title.status == "exists"
    assert same_title.work is None


def test_create_text_work_from_qid_rejects_bad_input(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        text_work_service, "fetch_wikidata_concept_seed", _fake_seed_fetcher("Anything")
    )
    assert create_text_work_from_qid(session, "bogus", "folk_tale").status == "failed"
    assert create_text_work_from_qid(session, "Q1", "not_a_type").status == "failed"
    assert create_text_work_from_qid(session, "Q1", "quote").status == "failed"

    monkeypatch.setattr(text_work_service, "fetch_wikidata_concept_seed", lambda qid, **kw: None)
    assert create_text_work_from_qid(session, "Q1", "folk_tale").status == "unresolved"
