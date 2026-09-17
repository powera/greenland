"""Golden mode rebuilds the forms the release files withhold as derivable.

``data/release`` carries only what the langtools rules cannot derive, and
``storage.admin.bootstrap`` puts the rest back with ``generate_mechanical_forms``
after an import.  Golden/hosted serve the same files out of an in-memory SQLite
without ever bootstrapping, so the step has to happen there too -- otherwise a
regular noun like "pharmacist", whose whole paradigm is derivable, arrives with
no ``DerivativeForm`` rows at all.

That is not only a gap in the forms tab.  ``storage.lexeme.get_lexeme`` returns
None for a lemma with no forms in a language, so the frequency rollup, the
per-corpus ranks and the combined rank skip it entirely: an irregular
("child") keeps a rank while a regular one loses it, which is what made the
frequency stats look arbitrary.
"""

from __future__ import annotations

import unittest
from typing import Any, List, Optional
from unittest import mock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Import the full model registry so every table (FK targets included) is created.
import storage.models  # noqa: F401
from storage.crud.grammar_fact import add_grammar_fact
from storage.lexeme import get_lexeme
from storage.models.schema import Base, DerivativeForm, Lemma
from storage.release.mechanical_filter import clear_cache, without_derivable
from wordfreq import golden_loader
from wordfreq.tools.generate_mechanical_forms import generate_for_session


class GoldenMechanicalFormsTest(unittest.TestCase):
    """What a release-shaped database looks like before and after the pass."""

    def setUp(self) -> None:
        clear_cache()
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.session = Session(engine)

    def tearDown(self) -> None:
        self.session.close()
        clear_cache()

    def _noun(self, text: str, guid: str, plural: Optional[str] = None) -> Lemma:
        """A countable English noun, optionally carrying an irregular plural.

        This is what an imported release row looks like: the lemma, its grammar
        facts, and only the forms the rules cannot derive.  An irregular plural
        is stored as a form and not as a ``plural`` grammar fact, which is how
        ``data/release`` carries "children" -- a fact would make the rules
        predict it, and the export would then withhold the row.
        """
        lemma = Lemma(lemma_text=text, definition_text=text, pos_type="noun", guid=guid)
        self.session.add(lemma)
        self.session.commit()
        add_grammar_fact(
            self.session,
            lemma_id=lemma.id,
            language_code="en",
            fact_type="countability",
            fact_value="countable",
        )
        if plural is not None:
            self.session.add(
                DerivativeForm(
                    lemma_id=lemma.id,
                    language_code="en",
                    grammatical_form="noun/en_plural",
                    derivative_form_text=plural,
                    is_base_form=False,
                )
            )
            self.session.commit()
        return lemma

    def _en_forms(self, lemma: Lemma) -> dict[str, str]:
        rows = (
            self.session.query(DerivativeForm)
            .filter(
                DerivativeForm.lemma_id == lemma.id,
                DerivativeForm.language_code == "en",
            )
            .all()
        )
        return {row.grammatical_form: row.derivative_form_text for row in rows}

    def test_a_fully_regular_noun_arrives_with_nothing(self) -> None:
        """The premise: the release withholds even "pharmacist"'s own spelling.

        Both slots follow from the rules, so the export writes neither and the
        lemma reaches golden mode with no forms and therefore no lexeme.
        """
        lemma = self._noun("pharmacist", "N36_900")
        self.assertEqual(self._en_forms(lemma), {})
        self.assertIsNone(get_lexeme(self.session, lemma.id, "en"))

    def test_generation_restores_the_base_form(self) -> None:
        """After the pass the lemma has its singular, flagged as the base form."""
        lemma = self._noun("pharmacist", "N36_901")
        generate_for_session(self.session, languages=["en"])

        self.assertEqual(
            self._en_forms(lemma),
            {"noun/en_singular": "pharmacist", "noun/en_plural": "pharmacists"},
        )
        lexeme = get_lexeme(self.session, lemma.id, "en")
        assert lexeme is not None
        base_form = lexeme.base_form
        assert base_form is not None
        self.assertEqual(base_form.derivative_form_text, "pharmacist")

    def test_an_irregular_keeps_its_stored_plural_and_gains_a_base_form(self) -> None:
        """ "child" ships its "children" and is missing only the derivable half."""
        lemma = self._noun("child", "N36_902", plural="children")
        self.assertEqual(self._en_forms(lemma), {"noun/en_plural": "children"})

        generate_for_session(self.session, languages=["en"])

        self.assertEqual(
            self._en_forms(lemma),
            {"noun/en_singular": "child", "noun/en_plural": "children"},
        )

    def test_the_pass_is_the_inverse_of_the_export_filter(self) -> None:
        """Whatever the export withholds is exactly what the pass puts back.

        The two are meant to compose into a fixed point, so a generated
        paradigm run back through the filter must leave the release row the
        lemma started with -- nothing for a regular noun, the irregular plural
        for "child".
        """
        regular = self._noun("librarian", "N36_903")
        irregular = self._noun("child", "N36_904", plural="children")
        generate_for_session(self.session, languages=["en"])
        clear_cache()

        for lemma, expected in ((regular, []), (irregular, ["children"])):
            forms = (
                self.session.query(DerivativeForm).filter(DerivativeForm.lemma_id == lemma.id).all()
            )
            kept = without_derivable(self.session, lemma, forms)
            self.assertEqual([row.derivative_form_text for row in kept], expected)

    def test_generation_is_idempotent(self) -> None:
        """A second pass adds nothing: golden mode may reload into a warm DB."""
        self._noun("pharmacist", "N36_905")
        first = generate_for_session(self.session, languages=["en"])
        second = generate_for_session(self.session, languages=["en"])

        self.assertEqual(first["en"]["forms_added"], 2)
        self.assertEqual(second["en"]["forms_added"], 0)


class GoldenLoaderOrderTest(unittest.TestCase):
    """Where the pass sits in the golden load, and on what kind of session."""

    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.storage = mock.Mock(_cached_sqlite_engine=engine)

    def test_forms_are_generated_before_the_corpus_load(self) -> None:
        """``link_forms_to_word_tokens`` has nothing to link to otherwise.

        The corpus load is what creates the ``WordToken`` rows a form points
        at, so a form generated afterwards would sit unlinked and roll up
        nothing -- the same ordering ``storage.admin.bootstrap`` documents.
        """
        calls: List[str] = []

        def record(name: str, result: Any) -> Any:
            def _recorded(*_args: Any, **_kwargs: Any) -> Any:
                calls.append(name)
                return result

            return _recorded

        with (
            mock.patch.object(golden_loader, "generate_for_session", record("generate", {})),
            mock.patch.object(golden_loader.corpus, "load_all_corpora", record("corpora", {})),
            mock.patch.object(
                golden_loader,
                "link_forms_to_word_tokens",
                record("link", {"derivative_forms": 0, "variant_forms": 0}),
            ),
            mock.patch.object(golden_loader, "run_tier_import", record("tiers", mock.Mock())),
            mock.patch.object(
                golden_loader.combined_rank,
                "calculate_lemma_combined_ranks",
                record("ranks", {}),
            ),
        ):
            golden_loader.load_wordfreq_into_storage(self.storage)

        self.assertEqual(calls[:3], ["generate", "corpora", "link"])

    def test_the_generation_session_does_not_expire_on_commit(self) -> None:
        """Expiry on commit is what made this pass take minutes, not seconds.

        ``add_word_token`` commits once per new token, and a committing session
        expires every object it holds.  Against the in-memory database, whose
        identity map is the whole dictionary, that is quadratic.
        """
        with mock.patch.object(golden_loader, "generate_for_session") as generate:
            golden_loader._generate_mechanical_forms(self.storage)

        session = generate.call_args.args[0]
        self.assertFalse(session.expire_on_commit)


if __name__ == "__main__":
    unittest.main()
