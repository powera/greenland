"""Tests for the sub-concepts (sub-encyclopedia) system.

Covers the SubConcept CRUD layer, the shared Wikidata index (mutually exclusive
concept / sub-concept targets), the filing service, promote/demote, wanted-slug
filtering, and wiki-link target resolution (slug order + Q-id targets).
"""

from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.concept_service import (
    create_concept_from_qid,
    demote_concept_to_sub,
    file_sub_concept_from_qid,
    promote_sub_concept,
)
from storage.crud.concept import (
    create_concept,
    create_sub_concept,
    delete_sub_concept,
    get_sub_concept_by_slug,
    get_wikidata_index,
    link_wikidata_concept,
    link_wikidata_sub_concept,
    update_sub_concept,
)
from storage.models.concept import (
    ALL_SUB_CONCEPT_CATEGORIES,
    Base,
    EXCLUDED_SUB_CONCEPT_CATEGORIES,
    SUB_CONCEPT_CATEGORIES,
    is_excluded_sub_concept_category,
    wiki_target_qid,
)
from storage.queries.concept import (
    count_sub_concepts,
    get_all_known_slugs,
    get_backlinks,
    get_wanted_slugs,
    list_sub_concepts,
    resolve_wiki_link_targets,
)
from storage.wikidata import WikidataConceptSeed


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


def _seed(qid: str, title: str, summary: str = "a summary") -> WikidataConceptSeed:
    return WikidataConceptSeed(qid=qid, title=title, summary=summary, sources=[])


def test_wiki_target_qid_detects_qid_targets() -> None:
    assert wiki_target_qid("Q42") == "Q42"
    assert wiki_target_qid("q103632") == "Q103632"
    assert wiki_target_qid("Q0") is None
    assert wiki_target_qid("Quebec") is None
    assert wiki_target_qid("Q42_extra") is None


def test_create_sub_concept_validates_category(session: Session) -> None:
    assert create_sub_concept(session, "Sicilian Defense", "not_a_category") is None

    sub = create_sub_concept(session, "Sicilian Defense", "chess_concept")
    assert sub is not None
    assert sub.slug == "Sicilian_Defense"
    assert sub.category == "chess_concept"

    # Duplicate slug within sub_concepts is refused.
    assert create_sub_concept(session, "Sicilian_Defense", "chess_concept") is None


def test_update_sub_concept_validates_category(session: Session) -> None:
    sub = create_sub_concept(session, "Ruy Lopez", "chess_concept")
    assert sub is not None

    assert update_sub_concept(session, sub, category="bogus") is None
    updated = update_sub_concept(session, sub, category="sports_team_season", verified=True)
    assert updated is not None
    assert updated.category == "sports_team_season"
    assert updated.verified is True


def test_sub_concept_slug_may_shadow_main_concept(session: Session) -> None:
    assert create_concept(session, title="Mercury") is not None
    sub = create_sub_concept(session, "Mercury", "bird_species")
    assert sub is not None
    assert get_sub_concept_by_slug(session, "Mercury") == sub


def test_wikidata_index_targets_are_mutually_exclusive(session: Session) -> None:
    concept = create_concept(session, title="Chess")
    assert concept is not None
    sub = create_sub_concept(session, "Sicilian Defense", "chess_concept")
    assert sub is not None

    assert link_wikidata_concept(session, "Q718", concept) is not None
    # A Q-id linked to a concept cannot be relinked to a sub-concept...
    assert link_wikidata_sub_concept(session, "Q718", sub) is None

    row = link_wikidata_sub_concept(session, "Q103632", sub)
    assert row is not None
    assert row.sub_concept_id == sub.id
    assert row.rejected is False
    # ...and vice versa.
    assert link_wikidata_concept(session, "Q103632", concept) is None


def test_delete_sub_concept_detaches_index_rows(session: Session) -> None:
    sub = create_sub_concept(session, "Sicilian Defense", "chess_concept")
    assert sub is not None
    assert link_wikidata_sub_concept(session, "Q103632", sub) is not None

    assert delete_sub_concept(session, sub) is True
    row = get_wikidata_index(session, "Q103632")
    assert row is not None
    assert row.sub_concept_id is None


def test_file_sub_concept_from_qid_files_and_is_idempotent(monkeypatch, session: Session) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        "storage.concept_service.fetch_wikidata_concept_seed",
        lambda qid, include_regional_wikis=False: _seed(qid, "Sicilian Defence", "chess opening"),
    )

    result = file_sub_concept_from_qid(session, "q103632", "chess_concept", notes="intake")
    assert result.status == "filed"
    assert result.sub_concept is not None
    assert result.sub_concept.slug == "Sicilian_Defence"
    assert result.sub_concept.summary == "chess opening"
    assert result.sub_concept.notes == "intake"
    row = get_wikidata_index(session, "Q103632")
    assert row is not None and row.sub_concept_id == result.sub_concept.id

    again = file_sub_concept_from_qid(session, "Q103632", "chess_concept")
    assert again.status == "exists"


def test_file_sub_concept_from_qid_rejects_bad_inputs(monkeypatch, session: Session) -> None:  # type: ignore[no-untyped-def]
    assert file_sub_concept_from_qid(session, "nope", "chess_concept").status == "failed"

    monkeypatch.setattr(
        "storage.concept_service.fetch_wikidata_concept_seed",
        lambda qid, include_regional_wikis=False: None,
    )
    assert file_sub_concept_from_qid(session, "Q1", "chess_concept").status == "unresolved"

    monkeypatch.setattr(
        "storage.concept_service.fetch_wikidata_concept_seed",
        lambda qid, include_regional_wikis=False: _seed(qid, "Some Topic"),
    )
    assert file_sub_concept_from_qid(session, "Q1", "not_a_category").status == "failed"


def test_file_sub_concept_reports_main_concept_qid_as_exists(session: Session) -> None:
    concept = create_concept(session, title="Chess")
    assert concept is not None
    assert link_wikidata_concept(session, "Q718", concept) is not None

    result = file_sub_concept_from_qid(session, "Q718", "chess_concept")
    assert result.status == "exists"
    assert "main concept" in result.detail


def test_create_concept_from_qid_skips_sub_filed_qids(session: Session) -> None:
    sub = create_sub_concept(session, "Sicilian Defence", "chess_concept")
    assert sub is not None
    assert link_wikidata_sub_concept(session, "Q103632", sub) is not None

    # The exists-check fires before any Wikidata fetch, so no mocking needed.
    result = create_concept_from_qid(session, "Q103632")
    assert result.status == "exists"
    assert "sub-concept" in result.detail
    assert result.concept is None


def test_promote_sub_concept_moves_qids_and_removes_row(session: Session) -> None:
    sub = create_sub_concept(session, "Sicilian Defence", "chess_concept", summary="chess opening")
    assert sub is not None
    assert link_wikidata_sub_concept(session, "Q103632", sub) is not None

    concept = promote_sub_concept(session, sub)
    assert concept is not None
    assert concept.slug == "Sicilian_Defence"
    assert concept.summary == "chess opening"
    assert get_sub_concept_by_slug(session, "Sicilian_Defence") is None
    row = get_wikidata_index(session, "Q103632")
    assert row is not None
    assert row.concept_id == concept.id
    assert row.sub_concept_id is None


def test_promote_refuses_when_main_slug_exists(session: Session) -> None:
    assert create_concept(session, title="Mercury") is not None
    sub = create_sub_concept(session, "Mercury", "bird_species")
    assert sub is not None

    assert promote_sub_concept(session, sub) is None
    assert get_sub_concept_by_slug(session, "Mercury") is not None


def test_demote_concept_moves_qids_and_removes_row(session: Session) -> None:
    concept = create_concept(session, title="Anhinga", summary="a bird", body="Body text.")
    assert concept is not None
    assert link_wikidata_concept(session, "Q26308", concept) is not None

    sub = demote_concept_to_sub(session, concept, "bird_species")
    assert sub is not None
    assert sub.slug == "Anhinga"
    assert sub.summary == "a bird"
    row = get_wikidata_index(session, "Q26308")
    assert row is not None
    assert row.sub_concept_id == sub.id
    assert row.concept_id is None


def test_wanted_slugs_exclude_sub_concepts_and_qid_targets(session: Session) -> None:
    create_concept(
        session,
        title="Chess",
        body="See [[Sicilian Defence]], [[Ruy Lopez]], and [[Q9]] for more.",
    )
    create_sub_concept(session, "Sicilian Defence", "chess_concept")

    assert get_all_known_slugs(session) == {"Chess", "Sicilian_Defence"}
    assert get_wanted_slugs(session) == ["Ruy_Lopez"]


def test_list_and_count_sub_concepts_filter_by_category_and_search(session: Session) -> None:
    create_sub_concept(session, "Sicilian Defence", "chess_concept")
    create_sub_concept(session, "Anhinga", "bird_species", summary="darter bird")
    create_sub_concept(session, "2004 Boston Red Sox season", "sports_team_season")

    assert count_sub_concepts(session) == 3
    assert count_sub_concepts(session, category="bird_species") == 1
    assert [sub.slug for sub in list_sub_concepts(session, category="chess_concept")] == [
        "Sicilian_Defence"
    ]
    # Search matches slug (space/underscore equivalent) and summary.
    assert [sub.slug for sub in list_sub_concepts(session, search="red sox")] == [
        "2004_Boston_Red_Sox_season"
    ]
    assert [sub.slug for sub in list_sub_concepts(session, search="darter")] == ["Anhinga"]


def test_resolve_wiki_link_targets_prefers_main_concept_for_slugs(session: Session) -> None:
    create_concept(session, title="Mercury")
    create_sub_concept(session, "Mercury", "bird_species")
    create_sub_concept(session, "Anhinga", "bird_species")

    resolved = resolve_wiki_link_targets(session, "About [[Mercury]], [[Anhinga]], [[Missing]].")

    assert resolved["Mercury"].kind == "concept"
    assert resolved["Anhinga"].kind == "sub_concept"
    assert "Missing" not in resolved


def test_resolve_wiki_link_targets_resolves_qids_through_index(session: Session) -> None:
    concept = create_concept(session, title="Chess")
    assert concept is not None
    link_wikidata_concept(session, "Q718", concept)
    sub = create_sub_concept(session, "Sicilian Defence", "chess_concept")
    assert sub is not None
    link_wikidata_sub_concept(session, "Q103632", sub)

    resolved = resolve_wiki_link_targets(
        session, "See [[Q718]], [[Q103632|the Sicilian]], and [[Q99999]]."
    )

    assert resolved["Q718"] == ("concept", "Chess", "Chess")
    assert resolved["Q103632"] == ("sub_concept", "Sicilian_Defence", "Sicilian Defence")
    assert "Q99999" not in resolved


def test_backlinks_match_slug_and_qid_links(session: Session) -> None:
    create_concept(session, title="Chess openings", body="Try the [[Sicilian Defence]].")
    create_concept(session, title="Chess history", body="The [[Q103632|Sicilian]] is old.")
    create_concept(session, title="Unrelated", body="Nothing relevant.")

    backlinks = get_backlinks(session, "Sicilian_Defence", qids=["Q103632"])
    assert sorted(concept.slug for concept in backlinks) == ["Chess_history", "Chess_openings"]


def test_sub_concept_categories_initial_vocabulary() -> None:
    assert SUB_CONCEPT_CATEGORIES == ("bird_species", "chess_concept", "sports_team_season")
    assert EXCLUDED_SUB_CONCEPT_CATEGORIES == ("micronation",)
    assert set(ALL_SUB_CONCEPT_CATEGORIES) == set(SUB_CONCEPT_CATEGORIES) | set(
        EXCLUDED_SUB_CONCEPT_CATEGORIES
    )
    assert is_excluded_sub_concept_category("micronation") is True
    assert is_excluded_sub_concept_category("bird_species") is False


def test_excluded_category_creates_and_marks_sub_concept(session: Session) -> None:
    sub = create_sub_concept(session, "Sealand", "micronation")
    assert sub is not None
    assert sub.is_excluded is True

    tracked = create_sub_concept(session, "Anhinga", "bird_species")
    assert tracked is not None
    assert tracked.is_excluded is False


def test_excluded_sub_concept_cannot_be_promoted(session: Session) -> None:
    sub = create_sub_concept(session, "Sealand", "micronation")
    assert sub is not None
    assert link_wikidata_sub_concept(session, "Q35754", sub) is not None

    assert promote_sub_concept(session, sub) is None
    # Row and index link are untouched.
    assert get_sub_concept_by_slug(session, "Sealand") is not None
    row = get_wikidata_index(session, "Q35754")
    assert row is not None and row.sub_concept_id == sub.id

    # Moving to a tracked category unblocks promotion.
    assert update_sub_concept(session, sub, category="chess_concept") is not None
    assert promote_sub_concept(session, sub) is not None


def test_create_concept_from_qid_reports_excluded_qids(session: Session) -> None:
    sub = create_sub_concept(session, "Sealand", "micronation")
    assert sub is not None
    assert link_wikidata_sub_concept(session, "Q35754", sub) is not None

    result = create_concept_from_qid(session, "Q35754")
    assert result.status == "exists"
    assert "strictly excluded" in result.detail
    assert result.concept is None


def test_file_sub_concept_from_qid_accepts_excluded_category(monkeypatch, session: Session) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        "storage.concept_service.fetch_wikidata_concept_seed",
        lambda qid, include_regional_wikis=False: _seed(qid, "Principality of Sealand"),
    )

    result = file_sub_concept_from_qid(session, "Q35754", "micronation")
    assert result.status == "filed"
    assert result.sub_concept is not None
    assert result.sub_concept.is_excluded is True
