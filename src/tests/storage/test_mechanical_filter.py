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
from storage.release.mechanical_filter import (
    clear_cache,
    derivable_form_keys,
    is_derivable,
    without_derivable,
)


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


if __name__ == "__main__":
    unittest.main()
