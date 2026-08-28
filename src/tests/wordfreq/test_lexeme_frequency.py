"""Tests for wordfreq.lexeme_frequency rollups and sense-prominence splitting."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.lexeme import get_lexeme
from storage.models.schema import (
    SENSE_PROMINENCE_COMMON,
    SENSE_PROMINENCE_UNCOMMON,
    SENSE_PROMINENCE_VERY_COMMON,
    Base,
    DerivativeForm,
    ExternalLexemeAnnotation,
    Lemma,
    WordToken,
)
from storage.models.variant_form import VARIANT_KIND_SPELLING, VariantForm
from wordfreq.lexeme_frequency import (
    get_lexeme_form_ranks,
    get_lexeme_frequency,
    get_token_share,
    link_forms_to_word_tokens,
)


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _add_lemma(
    session: Session,
    text: str,
    guid: str,
    *,
    pos_type: str = "noun",
    sense_prominence: str = SENSE_PROMINENCE_COMMON,
) -> Lemma:
    lemma = Lemma(
        lemma_text=text,
        definition_text=text,
        pos_type=pos_type,
        guid=guid,
        sense_prominence=sense_prominence,
    )
    session.add(lemma)
    session.flush()
    return lemma


def _add_token_with_freq(
    session: Session,
    token_text: str,
    corpus_name: str,
    frequency: float,
    language_code: str = "en",
) -> WordToken:
    """Insert a WordToken (if missing) and an ExternalLexemeAnnotation for ``wordfreq_<corpus_name>``."""
    token = (
        session.query(WordToken)
        .filter(WordToken.token == token_text, WordToken.language_code == language_code)
        .first()
    )
    if token is None:
        token = WordToken(token=token_text, language_code=language_code)
        session.add(token)
        session.flush()
    session.add(
        ExternalLexemeAnnotation(
            word_token_id=token.id,
            source=f"wordfreq_{corpus_name}",
            tier_name="r1-50",
            frequency=frequency,
        )
    )
    session.flush()
    return token


def _add_form(
    session: Session,
    lemma: Lemma,
    text: str,
    grammatical_form: str,
    *,
    word_token: WordToken | None = None,
    language_code: str = "en",
    is_base_form: bool = False,
) -> DerivativeForm:
    form = DerivativeForm(
        lemma_id=lemma.id,
        derivative_form_text=text,
        word_token_id=word_token.id if word_token is not None else None,
        language_code=language_code,
        grammatical_form=grammatical_form,
        is_base_form=is_base_form,
    )
    session.add(form)
    session.flush()
    return form


def test_single_sense_lemma_gets_full_token_frequency() -> None:
    """An unambiguous lemma owns 100% of its token frequency regardless of prominence."""
    session = _make_session()
    try:
        elephant = _add_lemma(
            session, "elephant", "N01_001", sense_prominence=SENSE_PROMINENCE_COMMON
        )
        token = _add_token_with_freq(session, "elephant", "testcorpus", 42.0)
        _add_form(session, elephant, "elephant", "singular", word_token=token, is_base_form=True)
        session.commit()

        lexeme = get_lexeme(session, elephant.id, "en")
        assert lexeme is not None
        rollup = get_lexeme_frequency(session, lexeme, "testcorpus")
        assert rollup.total_frequency == pytest.approx(42.0)
        assert len(rollup.form_breakdown) == 1
        assert rollup.form_breakdown[0].share == pytest.approx(1.0)
    finally:
        session.close()


def test_homograph_split_by_sense_prominence_weights() -> None:
    """bank-finance (very_common=20) vs bank-river (common=5) split 20/25 vs 5/25."""
    session = _make_session()
    try:
        bank_fin = _add_lemma(
            session, "bank", "N02_001", sense_prominence=SENSE_PROMINENCE_VERY_COMMON
        )
        bank_riv = _add_lemma(session, "bank", "N02_002", sense_prominence=SENSE_PROMINENCE_COMMON)
        token = _add_token_with_freq(session, "bank", "testcorpus", 100.0)
        _add_form(session, bank_fin, "bank", "singular", word_token=token, is_base_form=True)
        _add_form(session, bank_riv, "bank", "singular", word_token=token, is_base_form=True)
        session.commit()

        share_fin = get_token_share(session, token.id, bank_fin.id)
        share_riv = get_token_share(session, token.id, bank_riv.id)
        assert share_fin == pytest.approx(20 / 25)
        assert share_riv == pytest.approx(5 / 25)
        assert share_fin + share_riv == pytest.approx(1.0)

        lex_fin = get_lexeme(session, bank_fin.id, "en")
        lex_riv = get_lexeme(session, bank_riv.id, "en")
        assert lex_fin is not None and lex_riv is not None
        rollup_fin = get_lexeme_frequency(session, lex_fin, "testcorpus")
        rollup_riv = get_lexeme_frequency(session, lex_riv, "testcorpus")
        assert rollup_fin.total_frequency == pytest.approx(80.0)
        assert rollup_riv.total_frequency == pytest.approx(20.0)
    finally:
        session.close()


def test_three_way_split_with_uncommon() -> None:
    """very_common(20) + common(5) + uncommon(1) splits a token 20/26, 5/26, 1/26."""
    session = _make_session()
    try:
        a = _add_lemma(session, "bank", "X01", sense_prominence=SENSE_PROMINENCE_VERY_COMMON)
        b = _add_lemma(session, "bank", "X02", sense_prominence=SENSE_PROMINENCE_COMMON)
        c = _add_lemma(session, "bank", "X03", sense_prominence=SENSE_PROMINENCE_UNCOMMON)
        token = _add_token_with_freq(session, "bank", "c", 260.0)
        for lemma in (a, b, c):
            _add_form(session, lemma, "bank", "singular", word_token=token, is_base_form=True)
        session.commit()

        lex_a = get_lexeme(session, a.id, "en")
        lex_b = get_lexeme(session, b.id, "en")
        lex_c = get_lexeme(session, c.id, "en")
        assert lex_a is not None and lex_b is not None and lex_c is not None
        ra = get_lexeme_frequency(session, lex_a, "c")
        rb = get_lexeme_frequency(session, lex_b, "c")
        rc = get_lexeme_frequency(session, lex_c, "c")
        assert ra.total_frequency == pytest.approx(200.0)
        assert rb.total_frequency == pytest.approx(50.0)
        assert rc.total_frequency == pytest.approx(10.0)
    finally:
        session.close()


def test_inflections_sum_into_lexeme_total() -> None:
    """All DerivativeForms tied to one lemma roll up additively."""
    session = _make_session()
    try:
        read_v = _add_lemma(
            session, "read", "V01", pos_type="verb", sense_prominence=SENSE_PROMINENCE_VERY_COMMON
        )
        t_present = _add_token_with_freq(session, "read", "c", 100.0)
        t_reads = _add_token_with_freq(session, "reads", "c", 30.0)
        t_reading = _add_token_with_freq(session, "reading", "c", 50.0)
        _add_form(session, read_v, "read", "infinitive", word_token=t_present, is_base_form=True)
        _add_form(session, read_v, "reads", "3rd_person_singular_present", word_token=t_reads)
        _add_form(session, read_v, "reading", "gerund", word_token=t_reading)
        session.commit()

        lex = get_lexeme(session, read_v.id, "en")
        assert lex is not None
        rollup = get_lexeme_frequency(session, lex, "c")
        assert rollup.total_frequency == pytest.approx(180.0)
        assert len(rollup.form_breakdown) == 3
    finally:
        session.close()


def test_unknown_corpus_returns_zero_rollup() -> None:
    """Querying an unknown corpus name yields an empty zero-frequency rollup."""
    session = _make_session()
    try:
        elephant = _add_lemma(session, "elephant", "N01_001")
        _add_form(session, elephant, "elephant", "singular", is_base_form=True)
        session.commit()
        lexeme = get_lexeme(session, elephant.id, "en")
        assert lexeme is not None
        rollup = get_lexeme_frequency(session, lexeme, "no-such-corpus")
        assert rollup.total_frequency == 0.0
        assert rollup.form_breakdown == ()
    finally:
        session.close()


def test_form_without_token_is_skipped() -> None:
    """Multi-word forms (no word_token_id) contribute zero, no error."""
    session = _make_session()
    try:
        lemma = _add_lemma(session, "give up", "V99", pos_type="verb")
        _add_form(session, lemma, "give up", "infinitive", word_token=None, is_base_form=True)
        session.commit()

        lex = get_lexeme(session, lemma.id, "en")
        assert lex is not None
        rollup = get_lexeme_frequency(session, lex, "c")
        assert rollup.total_frequency == 0.0
        assert rollup.form_breakdown == ()
    finally:
        session.close()


def test_token_share_zero_for_unattached_token() -> None:
    session = _make_session()
    try:
        token = WordToken(token="orphan", language_code="en")
        session.add(token)
        session.flush()
        assert get_token_share(session, token.id, lemma_id=999) == 0.0
    finally:
        session.close()


def _add_variant(
    session: Session,
    lemma: Lemma,
    text: str,
    variant_key: str,
    grammatical_form: str,
    *,
    word_token: WordToken | None = None,
    language_code: str = "en",
) -> VariantForm:
    variant = VariantForm(
        lemma_id=lemma.id,
        language_code=language_code,
        variant_kind=VARIANT_KIND_SPELLING,
        variant_key=variant_key,
        grammatical_form=grammatical_form,
        variant_form_text=text,
        word_token_id=word_token.id if word_token is not None else None,
        is_base_form=True,
    )
    session.add(variant)
    session.flush()
    return variant


def test_variant_spelling_contributes_frequency_to_its_lemma() -> None:
    """A corpus using the British spelling still measures the same lexeme.

    "aluminium" is not a derivative form of "aluminum" -- it is the same word
    spelled another way -- so without variants counted, a corpus that prefers
    the British spelling charges that usage to nobody.
    """
    session = _make_session()
    try:
        aluminum = _add_lemma(session, "aluminum", "N14_005")
        own = _add_token_with_freq(session, "aluminum", "testcorpus", 83.0)
        _add_form(session, aluminum, "aluminum", "singular", word_token=own, is_base_form=True)

        british = _add_token_with_freq(session, "aluminium", "testcorpus", 350.0)
        _add_variant(session, aluminum, "aluminium", "aluminium", "singular", word_token=british)
        session.commit()

        lexeme = get_lexeme(session, aluminum.id, "en")
        assert lexeme is not None
        rollup = get_lexeme_frequency(session, lexeme, "testcorpus")

        assert rollup.total_frequency == pytest.approx(433.0)
        assert {f.derivative_form_text for f in rollup.form_breakdown} == {
            "aluminum",
            "aluminium",
        }
    finally:
        session.close()


def test_variant_only_token_is_still_owned_by_its_lemma() -> None:
    """A token reached only through a variant must not have share 0.0.

    The lemma's own spelling may have no token at all (no corpus used it), and
    the variant's frequency would then be discarded rather than credited.
    """
    session = _make_session()
    try:
        aluminum = _add_lemma(session, "aluminum", "N14_005")
        _add_form(session, aluminum, "aluminum", "singular", word_token=None, is_base_form=True)
        british = _add_token_with_freq(session, "aluminium", "testcorpus", 350.0)
        _add_variant(session, aluminum, "aluminium", "aluminium", "singular", word_token=british)
        session.commit()

        assert get_token_share(session, british.id, aluminum.id) == pytest.approx(1.0)

        lexeme = get_lexeme(session, aluminum.id, "en")
        assert lexeme is not None
        rollup = get_lexeme_frequency(session, lexeme, "testcorpus")
        assert rollup.total_frequency == pytest.approx(350.0)
    finally:
        session.close()


def test_variant_ranks_are_collected_for_scoring() -> None:
    """get_lexeme_form_ranks sees variants, so rank scoring agrees with frequency."""
    session = _make_session()
    try:
        aluminum = _add_lemma(session, "aluminum", "N14_005")
        _add_form(session, aluminum, "aluminum", "singular", word_token=None, is_base_form=True)
        british = WordToken(token="aluminium", language_code="en")
        session.add(british)
        session.flush()
        session.add(
            ExternalLexemeAnnotation(
                word_token_id=british.id,
                source="wordfreq_testcorpus",
                tier_name="r2001-3000",
                frequency=56.7,
                ordinal_rank=2302,
            )
        )
        _add_variant(session, aluminum, "aluminium", "aluminium", "singular", word_token=british)
        session.commit()

        lexeme = get_lexeme(session, aluminum.id, "en")
        assert lexeme is not None
        assert get_lexeme_form_ranks(session, lexeme, "testcorpus") == [2302]
    finally:
        session.close()


def test_a_form_counted_once_even_when_slots_share_a_spelling() -> None:
    """English past tense fills many slots with one word; frequency counts it once.

    "refined" occupies 1s/2s/3s/1p/2p/3p past plus the participle, all pointing
    at the same token. Summing per row would multiply that word's frequency by
    the size of the paradigm table.
    """
    session = _make_session()
    try:
        refine = _add_lemma(session, "refine", "V80", pos_type="verb")
        token = _add_token_with_freq(session, "refined", "c", 100.0)
        for slot in (
            "verb/en_1s_past",
            "verb/en_2s_past",
            "verb/en_3s_past",
            "verb/en_1p_past",
            "verb/en_2p_past",
            "verb/en_3p_past",
            "verb/en_past_participle",
        ):
            _add_form(session, refine, "refined", slot, word_token=token)
        session.commit()

        lex = get_lexeme(session, refine.id, "en")
        assert lex is not None
        rollup = get_lexeme_frequency(session, lex, "c")
        assert rollup.total_frequency == pytest.approx(100.0)
        assert get_lexeme_form_ranks(session, lex, "c") == []
    finally:
        session.close()


@pytest.mark.parametrize("capitalized_first", [True, False])
def test_link_forms_prefers_the_exact_spelling_over_a_case_twin(
    capitalized_first: bool,
) -> None:
    """A form spelled "May" links to the "May" token, not to "may".

    Both spellings are legal rows -- ``uq_word_token_language`` is
    case-sensitive -- and the linker used to pick between them with
    ``setdefault`` over an unordered query, so the winner was whichever row came
    back first. Insertion order is parametrized here because that arbitrariness
    is the actual defect: the month must win both ways round.
    """
    session = _make_session()
    try:
        spellings = ["May", "may"] if capitalized_first else ["may", "May"]
        for spelling in spellings:
            session.add(WordToken(token=spelling, language_code="en"))
        session.flush()

        month = _add_lemma(session, "May", "N01_001")
        modal = _add_lemma(session, "may", "V01_001", pos_type="verb")
        _add_form(session, month, "May", "singular", is_base_form=True)
        _add_form(session, modal, "may", "infinitive", is_base_form=True)
        session.commit()

        counts = link_forms_to_word_tokens(session)
        assert counts["derivative_forms"] == 2

        linked = {
            form.derivative_form_text: form.word_token.token
            for form in session.query(DerivativeForm).all()
        }
        assert linked == {"May": "May", "may": "may"}
    finally:
        session.close()
