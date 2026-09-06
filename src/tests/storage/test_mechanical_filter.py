"""Tests for withholding mechanically-derivable forms from the release files.

``data/release`` carries only what the langtools rules cannot derive, and
``generate_mechanical_forms`` puts the rest back on import.  The filter under
test is the export-side half of that invariant: without it, a round trip
(import a release, export it again) writes every generated paradigm back out
and roughly doubles the tree.

The behaviour that matters is that the test is on *value*, not on slot.  A
form is withheld only when the rules would produce that same spelling for that
same slot; an irregular whose stored text differs from the rule's prediction is
the very thing the release exists to carry, so it stays.  These use English
nouns, whose builder needs only a ``countability`` fact, so the assertions read
without a language-specific setup.
"""

from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Import the full model registry so every table (FK targets included) is created.
import storage.models  # noqa: F401
from storage.crud.grammar_fact import add_grammar_fact
from storage.models.schema import Base, DerivativeForm, Lemma
from storage.models.variant_form import VariantForm
from storage.release.mechanical_filter import (
    clear_cache,
    derivable_form_keys,
    is_derivable,
    without_derivable,
)
from storage.release.variant import release_variants_by_language
from wordfreq.tools.generate_mechanical_forms import derivable_variant_slots


def _form(
    grammatical_form: str,
    text: str,
    ipa: str | None = None,
    phonetic: str | None = None,
) -> DerivativeForm:
    return DerivativeForm(
        language_code="en",
        grammatical_form=grammatical_form,
        derivative_form_text=text,
        is_base_form=False,
        ipa_pronunciation=ipa,
        phonetic_pronunciation=phonetic,
    )


class MechanicalFilterTest(unittest.TestCase):
    """Which forms the export withholds, and which it must keep."""

    def setUp(self) -> None:
        clear_cache()
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.session = Session(engine)

    def tearDown(self) -> None:
        self.session.close()
        clear_cache()

    def _noun(self, text: str, guid: str) -> Lemma:
        """A countable English noun, the simplest case with a rule-based plural."""
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
        return lemma

    def test_regular_plural_is_derivable(self) -> None:
        """ "dogs" follows from "dog" by rule, so it never reaches the files."""
        lemma = self._noun("dog", "N01_001")
        self.assertTrue(is_derivable(self.session, lemma, _form("noun/en_plural", "dogs")))

    def test_irregular_plural_is_kept(self) -> None:
        """The rules predict "childs"; the stored "children" must survive."""
        lemma = self._noun("child", "N01_002")
        self.assertFalse(is_derivable(self.session, lemma, _form("noun/en_plural", "children")))

    def test_a_pronunciation_keeps_an_otherwise_derivable_form(self) -> None:
        """The rules spell "dogs" but cannot voice it, so the row must survive.

        Withholding it would drop the IPA with it, and the next import -- which
        regenerates text only -- could not put the pronunciation back.
        """
        lemma = self._noun("dog", "N01_007")
        self.assertFalse(
            is_derivable(self.session, lemma, _form("noun/en_plural", "dogs", ipa="/dɔːɡz/"))
        )
        self.assertFalse(
            is_derivable(self.session, lemma, _form("noun/en_plural", "dogs", phonetic="DAWGZ"))
        )

    def test_unknown_slot_is_kept(self) -> None:
        """A slot the builder never emits has nothing to compare against."""
        lemma = self._noun("dog", "N01_003")
        self.assertFalse(is_derivable(self.session, lemma, _form("noun/en_possessive", "dog's")))

    def test_unsupported_pos_keeps_everything(self) -> None:
        """No builder for the (language, POS) pair means nothing is withheld."""
        lemma = Lemma(
            lemma_text="under",
            definition_text="under",
            pos_type="preposition",
            guid="P01_001",
        )
        self.session.add(lemma)
        self.session.commit()
        self.assertEqual(derivable_form_keys(self.session, lemma, "en"), set())
        self.assertFalse(is_derivable(self.session, lemma, _form("preposition/en_base", "under")))

    def test_without_derivable_keeps_only_the_irregulars(self) -> None:
        """The whole point: a mixed paradigm exports only what rules can't reach."""
        lemma = self._noun("child", "N01_004")
        kept = without_derivable(
            self.session,
            lemma,
            [
                _form("noun/en_singular", "child"),
                _form("noun/en_plural", "children"),
            ],
        )
        self.assertEqual(
            [form.derivative_form_text for form in kept],
            ["children"],
        )

    def test_cache_is_scoped_to_the_lemma(self) -> None:
        """Two lemmas must not share a memoized paradigm."""
        dog = self._noun("dog", "N01_005")
        child = self._noun("child", "N01_006")
        self.assertTrue(is_derivable(self.session, dog, _form("noun/en_plural", "dogs")))
        self.assertFalse(is_derivable(self.session, child, _form("noun/en_plural", "children")))


class VariantReleaseFilterTest(unittest.TestCase):
    """Which variant forms reach data/release, and which are regenerated.

    A variant's base form is irreducible -- no rule takes "gray" to "grey" --
    so it is always written.  Its inflections follow by the same rule that
    builds the lemma's own, so they are withheld and rebuilt on import; the
    alternative ships "greyer" beside a "grayer" the export withheld, which
    reads as a claim that the two spellings inflect differently.
    """

    def setUp(self) -> None:
        clear_cache()
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.session = Session(engine)
        self.lemma = Lemma(
            lemma_text="gray", definition_text="gray", pos_type="adjective", guid="A02_008"
        )
        self.session.add(self.lemma)
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()
        clear_cache()

    def _variant(
        self, grammatical_form: str, text: str, is_base_form: bool, ipa: str | None = None
    ) -> VariantForm:
        row = VariantForm(
            lemma_id=self.lemma.id,
            language_code="en",
            variant_kind="spelling",
            variant_key="grey",
            grammatical_form=grammatical_form,
            variant_form_text=text,
            is_base_form=is_base_form,
            ipa_pronunciation=ipa,
        )
        self.session.add(row)
        self.session.commit()
        return row

    def _exported_texts(self) -> list[str]:
        grouped = release_variants_by_language(self.lemma.variant_forms)
        return [form["text"] for form in grouped["en"][0]["forms"]]

    def test_derivable_inflections_are_withheld(self) -> None:
        """ "grey" ships; "greyer"/"greyest" are rebuilt by the generator."""
        self._variant("adjective/en_positive", "grey", True)
        self._variant("adjective/en_comparative", "greyer", False)
        self._variant("adjective/en_superlative", "greyest", False)
        self.assertEqual(self._exported_texts(), ["grey"])

    def test_base_form_is_always_written(self) -> None:
        """No rule derives the variant's spelling, so it can never be dropped."""
        self._variant("adjective/en_positive", "grey", True)
        self.assertEqual(self._exported_texts(), ["grey"])

    def test_an_unmodelled_base_slot_keeps_its_paradigm(self) -> None:
        """The compass words sit in adjective/en_base, which builds nothing.

        Withholding an inflection there would lose it for good, since the
        generator produces no paradigm to put it back.
        """
        self._variant("adjective/en_base", "north-east", True)
        unmodelled = self._variant("adjective/en_comparative", "north-easter", False)
        self.assertNotIn(unmodelled.grammatical_form, derivable_variant_slots(unmodelled))
        self.assertIn("north-easter", self._exported_texts())

    def test_a_pronunciation_keeps_an_inflection(self) -> None:
        """The builders emit text only, so an IPA-bearing row must survive."""
        self._variant("adjective/en_positive", "grey", True)
        self._variant("adjective/en_comparative", "greyer", False, ipa="/ˈɡreɪ.ər/")
        self.assertEqual(sorted(self._exported_texts()), ["grey", "greyer"])


if __name__ == "__main__":
    unittest.main()
