#!/usr/bin/python3

"""Aggregation for the term-age report."""

from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import storage.models  # noqa: F401 -- register every model before create_all
from reports.term_age import collect_results, parse_level_range, summarize
from storage.models.schema import Base, Lemma, LemmaTranslation
from words.term_age import LexicalStratum


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _add_lemma(
    session: Session,
    *,
    guid: str,
    lemma_text: str,
    pos_subtype: str,
    difficulty_level: int,
    japanese: str | None = None,
    ancient_status: str | None = None,
) -> Lemma:
    lemma = Lemma(
        guid=guid,
        lemma_text=lemma_text,
        definition_text=lemma_text,
        pos_type="noun",
        pos_subtype=pos_subtype,
        difficulty_level=difficulty_level,
    )
    session.add(lemma)
    session.flush()
    if japanese:
        session.add(LemmaTranslation(lemma_id=lemma.id, language_code="ja", translation=japanese))
    if ancient_status:
        for language_code in ("la", "sa", "grc", "ar-classical", "non"):
            session.add(
                LemmaTranslation(
                    lemma_id=lemma.id,
                    language_code=language_code,
                    translation=f"{lemma_text}-{language_code}",
                    translation_status=ancient_status,
                )
            )
    session.flush()
    return lemma


class TestParseLevelRange(unittest.TestCase):
    def test_single_level(self) -> None:
        self.assertEqual(parse_level_range("5"), (5, 5))

    def test_range(self) -> None:
        self.assertEqual(parse_level_range("3-8"), (3, 8))

    def test_inverted_range_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_level_range("8-3")


class TestReportAggregation(unittest.TestCase):
    def setUp(self) -> None:
        self.session = _make_session()
        _add_lemma(
            self.session,
            guid="N01_001",
            lemma_text="horse",
            pos_subtype="animal",
            difficulty_level=2,
            japanese="馬",
            ancient_status="conventional",
        )
        _add_lemma(
            self.session,
            guid="N01_002",
            lemma_text="computer",
            pos_subtype="technology_digital",
            difficulty_level=9,
            japanese="コンピューター",
            ancient_status="modern_loan",
        )
        _add_lemma(
            self.session,
            guid="N01_003",
            lemma_text="Berlin",
            pos_subtype="city",
            difficulty_level=15,
            japanese="ベルリン",
        )
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()

    def test_scores_every_lemma(self) -> None:
        summary = summarize(collect_results(self.session))
        self.assertEqual(summary["total_lemmas"], 3)

    def test_strata_split_ancient_from_modern(self) -> None:
        summary = summarize(collect_results(self.session))
        self.assertEqual(summary["strata"][LexicalStratum.ANCIENT_CORE.value], 1)
        self.assertEqual(summary["strata"][LexicalStratum.MODERN.value], 1)

    def test_coverage_counts_evidence_and_suppressions(self) -> None:
        summary = summarize(collect_results(self.session))
        coverage = summary["coverage"]
        self.assertEqual(coverage["with_ancient_evidence"], 2)
        self.assertEqual(coverage["with_japanese_translation"], 3)
        self.assertEqual(coverage["named_entity_suppressions"], 1)

    def test_cross_tab_keys_difficulty_levels(self) -> None:
        summary = summarize(collect_results(self.session))
        ancient = summary["stratum_by_difficulty_level"][LexicalStratum.ANCIENT_CORE.value]
        self.assertEqual(ancient, {2: 1})

    def test_level_filter_restricts_the_query(self) -> None:
        scored = collect_results(self.session, level_range=(1, 5))
        self.assertEqual([lemma.lemma_text for lemma, _result in scored], ["horse"])

    def test_extremes_only_include_corroborated_lemmas(self) -> None:
        """Berlin has no classical evidence, so it must not head either list."""
        summary = summarize(collect_results(self.session))
        listed = {entry["lemma_text"] for entry in summary["most_ancient"]}
        listed |= {entry["lemma_text"] for entry in summary["most_modern"]}
        self.assertNotIn("Berlin", listed)


if __name__ == "__main__":
    unittest.main()
