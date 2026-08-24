"""Tests for mechanical Lithuanian verb conjugation."""

import pytest

from langtools.lt.conjugation import (
    conjugate_verb,
    _conjugate_conditional,
    _conjugate_future,
    _conjugate_habitual_past,
    _conjugate_imperative,
    _conjugate_past,
    _conjugate_present,
    _get_infinitive_stem,
    _make_future_stem,
    _palatalize_final,
)


class TestPalatalizeFinal:
    """Test consonant palatalization rules."""

    def test_d_becomes_dz(self) -> None:
        assert _palatalize_final("gird") == "girdž"

    def test_t_becomes_c(self) -> None:
        assert _palatalize_final("kent") == "kenč"

    def test_other_consonants_unchanged(self) -> None:
        assert _palatalize_final("myl") == "myl"
        assert _palatalize_final("nor") == "nor"
        assert _palatalize_final("tur") == "tur"
        assert _palatalize_final("tik") == "tik"
        assert _palatalize_final("valg") == "valg"


class TestMakeFutureStem:
    """Test future stem derivation from infinitive."""

    def test_regular_consonant_stem(self) -> None:
        assert _make_future_stem("dirbti") == "dirbs"

    def test_regular_vowel_stem(self) -> None:
        assert _make_future_stem("rašyti") == "rašys"

    def test_sibilant_assimilation_zh(self) -> None:
        # ž + s → š
        assert _make_future_stem("vežti") == "veš"

    def test_sibilant_assimilation_s(self) -> None:
        # s + s → s (absorbed)
        assert _make_future_stem("kąsti") == "kąs"

    def test_sibilant_assimilation_sh(self) -> None:
        # š + s → š (absorbed)
        assert _make_future_stem("mešti") == "meš"

    def test_short_stem(self) -> None:
        assert _make_future_stem("eiti") == "eis"

    def test_long_vowel_stem(self) -> None:
        assert _make_future_stem("būti") == "būs"


class TestConjugatePresent:
    """Test present tense derivation from 3rd person present."""

    def test_conjugation_i_simple(self) -> None:
        """Conjugation I (-a): dirbti → dirba."""
        forms = _conjugate_present("dirba")
        assert forms is not None
        assert forms["1s_present"] == "dirbu"
        assert forms["2s_present"] == "dirbi"
        assert forms["3s_present"] == "dirba"
        assert forms["1p_present"] == "dirbame"
        assert forms["2p_present"] == "dirbate"
        assert forms["3p_present"] == "dirba"

    def test_conjugation_i_ia_ending(self) -> None:
        """Conjugation I with -ia ending: kenčia (kęsti)."""
        forms = _conjugate_present("kenčia")
        assert forms is not None
        assert forms["1s_present"] == "kenčiu"
        assert forms["2s_present"] == "kenči"
        assert forms["1p_present"] == "kenčiame"
        assert forms["2p_present"] == "kenčiate"

    def test_conjugation_ii_with_palatalization(self) -> None:
        """Conjugation II (-i) with d→dž: girdėti → girdi."""
        forms = _conjugate_present("girdi")
        assert forms is not None
        assert forms["1s_present"] == "girdžiu"
        assert forms["2s_present"] == "girdi"
        assert forms["3s_present"] == "girdi"
        assert forms["1p_present"] == "girdime"
        assert forms["2p_present"] == "girdite"

    def test_conjugation_ii_no_palatalization(self) -> None:
        """Conjugation II (-i) without palatalization: mylėti → myli."""
        forms = _conjugate_present("myli")
        assert forms is not None
        assert forms["1s_present"] == "myliu"
        assert forms["2s_present"] == "myli"
        assert forms["1p_present"] == "mylime"
        assert forms["2p_present"] == "mylite"

    def test_conjugation_iii(self) -> None:
        """Conjugation III (-o): rašyti → rašo."""
        forms = _conjugate_present("rašo")
        assert forms is not None
        assert forms["1s_present"] == "rašau"
        assert forms["2s_present"] == "rašai"
        assert forms["3s_present"] == "rašo"
        assert forms["1p_present"] == "rašome"
        assert forms["2p_present"] == "rašote"

    def test_unrecognized_ending(self) -> None:
        forms = _conjugate_present("xyz")
        assert forms is None


class TestConjugatePast:
    """Test past tense derivation from 3rd person past."""

    def test_o_preterite(self) -> None:
        """o-preterite: dirbti → dirbo."""
        forms = _conjugate_past("dirbo")
        assert forms is not None
        assert forms["1s_past"] == "dirbau"
        assert forms["2s_past"] == "dirbai"
        assert forms["3s_past"] == "dirbo"
        assert forms["1p_past"] == "dirbome"
        assert forms["2p_past"] == "dirbote"
        assert forms["3p_past"] == "dirbo"

    def test_e_preterite_with_palatalization_t(self) -> None:
        """ė-preterite with t→č: kęsti → kentė."""
        forms = _conjugate_past("kentė")
        assert forms is not None
        assert forms["1s_past"] == "kenčiau"
        assert forms["2s_past"] == "kentei"
        assert forms["3s_past"] == "kentė"
        assert forms["1p_past"] == "kentėme"
        assert forms["2p_past"] == "kentėte"

    def test_e_preterite_with_palatalization_d(self) -> None:
        """ė-preterite with d→dž: melsti → meldė."""
        forms = _conjugate_past("meldė")
        assert forms is not None
        assert forms["1s_past"] == "meldžiau"
        assert forms["2s_past"] == "meldei"

    def test_e_preterite_no_palatalization(self) -> None:
        """ė-preterite without palatalization: rašyti → rašė."""
        forms = _conjugate_past("rašė")
        assert forms is not None
        assert forms["1s_past"] == "rašiau"
        assert forms["2s_past"] == "rašei"
        assert forms["1p_past"] == "rašėme"
        assert forms["2p_past"] == "rašėte"

    def test_o_preterite_long_stem(self) -> None:
        """o-preterite with longer stem: mylėti → mylėjo."""
        forms = _conjugate_past("mylėjo")
        assert forms is not None
        assert forms["1s_past"] == "mylėjau"
        assert forms["2s_past"] == "mylėjai"
        assert forms["1p_past"] == "mylėjome"
        assert forms["2p_past"] == "mylėjote"

    def test_unrecognized_ending(self) -> None:
        forms = _conjugate_past("xyz")
        assert forms is None


class TestConjugateFuture:
    """Test future tense derivation from infinitive."""

    def test_regular(self) -> None:
        forms = _conjugate_future("dirbti")
        assert forms["1s_future"] == "dirbsiu"
        assert forms["2s_future"] == "dirbsi"
        assert forms["3s_future"] == "dirbs"
        assert forms["1p_future"] == "dirbsime"
        assert forms["2p_future"] == "dirbsite"
        assert forms["3p_future"] == "dirbs"

    def test_with_sibilant(self) -> None:
        forms = _conjugate_future("vežti")
        assert forms["1s_future"] == "vešiu"
        assert forms["2s_future"] == "veši"
        assert forms["3s_future"] == "veš"
        assert forms["1p_future"] == "vešime"
        assert forms["2p_future"] == "vešite"


class TestGetInfinitiveStem:
    """Test infinitive stem extraction."""

    def test_regular(self) -> None:
        assert _get_infinitive_stem("dirbti") == "dirb"

    def test_vowel_stem(self) -> None:
        assert _get_infinitive_stem("rašyti") == "rašy"

    def test_long_vowel_stem(self) -> None:
        assert _get_infinitive_stem("mylėti") == "mylė"

    def test_reflexive_returns_none(self) -> None:
        assert _get_infinitive_stem("mokytis") is None

    def test_unrecognized_returns_none(self) -> None:
        assert _get_infinitive_stem("xyz") is None


class TestConjugateConditional:
    """Test conditional (tariamoji nuosaka) derivation from infinitive."""

    def test_consonant_stem(self) -> None:
        """dirbti → dirb + conditional endings.

        The plural endings are deliberately asymmetric: 1pl drops the -mė-
        (dirbtume, not dirbtumėme) because me+me is too repetitive, while 2pl
        keeps it (dirbtumėte) since mė+te is not. Do not "fix" this to match.
        """
        forms = _conjugate_conditional("dirbti")
        assert forms is not None
        assert forms["1s_conditional"] == "dirbčiau"
        assert forms["2s_conditional"] == "dirbtum"
        assert forms["3s_conditional"] == "dirbtų"
        assert forms["1p_conditional"] == "dirbtume"
        assert forms["2p_conditional"] == "dirbtumėte"
        assert forms["3p_conditional"] == "dirbtų"

    def test_vowel_stem(self) -> None:
        """rašyti → rašy + conditional endings."""
        forms = _conjugate_conditional("rašyti")
        assert forms is not None
        assert forms["1s_conditional"] == "rašyčiau"
        assert forms["3s_conditional"] == "rašytų"

    def test_long_vowel_stem(self) -> None:
        """mylėti → mylė + conditional endings."""
        forms = _conjugate_conditional("mylėti")
        assert forms is not None
        assert forms["1s_conditional"] == "mylėčiau"
        assert forms["3s_conditional"] == "mylėtų"

    def test_short_stem(self) -> None:
        """eiti → ei + conditional endings."""
        forms = _conjugate_conditional("eiti")
        assert forms is not None
        assert forms["1s_conditional"] == "eičiau"
        assert forms["3s_conditional"] == "eitų"

    def test_3s_equals_3p(self) -> None:
        forms = _conjugate_conditional("dirbti")
        assert forms is not None
        assert forms["3s_conditional"] == forms["3p_conditional"]

    def test_reflexive_returns_none(self) -> None:
        assert _conjugate_conditional("mokytis") is None


class TestConjugateImperative:
    """Test imperative (liepiamoji nuosaka) derivation from infinitive."""

    def test_consonant_stem(self) -> None:
        """dirbti → dirbk / dirbkite."""
        forms = _conjugate_imperative("dirbti")
        assert forms is not None
        assert forms["2s_imperative"] == "dirbk"
        assert forms["2p_imperative"] == "dirbkite"

    def test_vowel_stem(self) -> None:
        """rašyti → rašyk / rašykite."""
        forms = _conjugate_imperative("rašyti")
        assert forms is not None
        assert forms["2s_imperative"] == "rašyk"
        assert forms["2p_imperative"] == "rašykite"

    def test_long_vowel_stem(self) -> None:
        """mylėti → mylėk / mylėkite."""
        forms = _conjugate_imperative("mylėti")
        assert forms is not None
        assert forms["2s_imperative"] == "mylėk"
        assert forms["2p_imperative"] == "mylėkite"

    def test_short_stem(self) -> None:
        """eiti → eik / eikite."""
        forms = _conjugate_imperative("eiti")
        assert forms is not None
        assert forms["2s_imperative"] == "eik"
        assert forms["2p_imperative"] == "eikite"

    def test_sibilant_stem(self) -> None:
        """kęsti → kęsk / kęskite."""
        forms = _conjugate_imperative("kęsti")
        assert forms is not None
        assert forms["2s_imperative"] == "kęsk"
        assert forms["2p_imperative"] == "kęskite"

    def test_reflexive_returns_none(self) -> None:
        assert _conjugate_imperative("mokytis") is None


class TestConjugateHabitualPast:
    """Test habitual past (būtasis kartinis) derivation from infinitive."""

    def test_consonant_stem(self) -> None:
        """dirbti → dirbdavo."""
        forms = _conjugate_habitual_past("dirbti")
        assert forms is not None
        assert forms["habitual_past"] == "dirbdavo"

    def test_vowel_stem(self) -> None:
        """rašyti → rašydavo."""
        forms = _conjugate_habitual_past("rašyti")
        assert forms is not None
        assert forms["habitual_past"] == "rašydavo"

    def test_long_vowel_stem(self) -> None:
        """mylėti → mylėdavo."""
        forms = _conjugate_habitual_past("mylėti")
        assert forms is not None
        assert forms["habitual_past"] == "mylėdavo"

    def test_short_stem(self) -> None:
        """eiti → eidavo."""
        forms = _conjugate_habitual_past("eiti")
        assert forms is not None
        assert forms["habitual_past"] == "eidavo"

    def test_reflexive_returns_none(self) -> None:
        assert _conjugate_habitual_past("mokytis") is None


class TestConjugateVerb:
    """Integration tests for full verb conjugation."""

    def test_dirbti_conj_i_o_preterite(self) -> None:
        """dirbti (to work): Conj I, o-preterite."""
        forms = conjugate_verb("dirbti", "dirba", "dirbo")
        assert forms is not None
        # Present
        assert forms["1s_present"] == "dirbu"
        assert forms["2s_present"] == "dirbi"
        assert forms["3s_present"] == "dirba"
        assert forms["1p_present"] == "dirbame"
        assert forms["2p_present"] == "dirbate"
        # Past
        assert forms["1s_past"] == "dirbau"
        assert forms["2s_past"] == "dirbai"
        assert forms["3s_past"] == "dirbo"
        assert forms["1p_past"] == "dirbome"
        assert forms["2p_past"] == "dirbote"
        # Future
        assert forms["1s_future"] == "dirbsiu"
        assert forms["2s_future"] == "dirbsi"
        assert forms["3s_future"] == "dirbs"
        assert forms["1p_future"] == "dirbsime"
        assert forms["2p_future"] == "dirbsite"
        # Conditional
        assert forms["1s_conditional"] == "dirbčiau"
        assert forms["3s_conditional"] == "dirbtų"
        # Imperative
        assert forms["2s_imperative"] == "dirbk"
        assert forms["2p_imperative"] == "dirbkite"
        # Habitual past
        assert forms["habitual_past"] == "dirbdavo"

    def test_myleti_conj_ii_o_preterite(self) -> None:
        """mylėti (to love): Conj II, o-preterite."""
        forms = conjugate_verb("mylėti", "myli", "mylėjo")
        assert forms is not None
        assert forms["1s_present"] == "myliu"
        assert forms["2s_present"] == "myli"
        assert forms["1p_present"] == "mylime"
        assert forms["1s_past"] == "mylėjau"
        assert forms["2s_past"] == "mylėjai"
        assert forms["1s_future"] == "mylėsiu"
        assert forms["3s_future"] == "mylės"

    def test_rasyti_conj_iii_e_preterite(self) -> None:
        """rašyti (to write): Conj III, ė-preterite."""
        forms = conjugate_verb("rašyti", "rašo", "rašė")
        assert forms is not None
        assert forms["1s_present"] == "rašau"
        assert forms["2s_present"] == "rašai"
        assert forms["1p_present"] == "rašome"
        assert forms["1s_past"] == "rašiau"
        assert forms["2s_past"] == "rašei"
        assert forms["1s_future"] == "rašysiu"
        assert forms["3s_future"] == "rašys"

    def test_girdeti_conj_ii_palatalization(self) -> None:
        """girdėti (to hear): Conj II with d→dž palatalization."""
        forms = conjugate_verb("girdėti", "girdi", "girdėjo")
        assert forms is not None
        assert forms["1s_present"] == "girdžiu"
        assert forms["2s_present"] == "girdi"
        assert forms["1p_present"] == "girdime"
        assert forms["1s_past"] == "girdėjau"

    def test_eiti_conj_i_o_preterite(self) -> None:
        """eiti (to go): Conj I, o-preterite."""
        forms = conjugate_verb("eiti", "eina", "ėjo")
        assert forms is not None
        assert forms["1s_present"] == "einu"
        assert forms["2s_present"] == "eini"
        assert forms["1p_present"] == "einame"
        assert forms["1s_past"] == "ėjau"
        assert forms["2s_past"] == "ėjai"
        assert forms["1s_future"] == "eisiu"
        assert forms["3s_future"] == "eis"

    def test_valgyti_conj_iii_e_preterite(self) -> None:
        """valgyti (to eat): Conj III, ė-preterite (no palatalization)."""
        forms = conjugate_verb("valgyti", "valgo", "valgė")
        assert forms is not None
        assert forms["1s_present"] == "valgau"
        assert forms["2s_present"] == "valgai"
        assert forms["1s_past"] == "valgiau"
        assert forms["2s_past"] == "valgei"
        assert forms["1s_future"] == "valgysiu"

    def test_kesti_conj_i_e_preterite_palatalization(self) -> None:
        """kęsti (to suffer): Conj I (-ia), ė-preterite (t→č)."""
        forms = conjugate_verb("kęsti", "kenčia", "kentė")
        assert forms is not None
        assert forms["1s_present"] == "kenčiu"
        assert forms["2s_present"] == "kenči"
        assert forms["1p_present"] == "kenčiame"
        assert forms["1s_past"] == "kenčiau"
        assert forms["2s_past"] == "kentei"
        assert forms["1s_future"] == "kęsiu"
        assert forms["3s_future"] == "kęs"

    def test_vezti_future_sibilant_assimilation(self) -> None:
        """vežti (to transport): ž+s → š in future."""
        forms = conjugate_verb("vežti", "veža", "vežė")
        assert forms is not None
        assert forms["1s_future"] == "vešiu"
        assert forms["2s_future"] == "veši"
        assert forms["3s_future"] == "veš"
        assert forms["1p_future"] == "vešime"

    def test_buti_irregular(self) -> None:
        """būti (to be): hard-coded irregular forms."""
        forms = conjugate_verb("būti", "yra", "buvo")
        assert forms is not None
        assert forms["1s_present"] == "esu"
        assert forms["2s_present"] == "esi"
        assert forms["3s_present"] == "yra"
        assert forms["1p_present"] == "esame"
        assert forms["2p_present"] == "esate"
        assert forms["1s_past"] == "buvau"
        assert forms["2s_past"] == "buvai"
        assert forms["3s_past"] == "buvo"
        assert forms["1s_future"] == "būsiu"
        assert forms["3s_future"] == "būs"
        assert forms["1s_conditional"] == "būčiau"
        assert forms["3s_conditional"] == "būtų"
        assert forms["2s_imperative"] == "būk"
        assert forms["2p_imperative"] == "būkite"
        assert forms["habitual_past"] == "būdavo"

    def test_reflexive_returns_none(self) -> None:
        """Reflexive verbs are not supported yet."""
        forms = conjugate_verb("mokytis", "mokosi", "mokėsi")
        assert forms is None

    def test_returns_27_forms(self) -> None:
        """All results should have exactly 27 form keys."""
        forms = conjugate_verb("dirbti", "dirba", "dirbo")
        assert forms is not None
        assert len(forms) == 27
        expected_keys = {
            "1s_present",
            "2s_present",
            "3s_present",
            "1p_present",
            "2p_present",
            "3p_present",
            "1s_past",
            "2s_past",
            "3s_past",
            "1p_past",
            "2p_past",
            "3p_past",
            "1s_future",
            "2s_future",
            "3s_future",
            "1p_future",
            "2p_future",
            "3p_future",
            "1s_conditional",
            "2s_conditional",
            "3s_conditional",
            "1p_conditional",
            "2p_conditional",
            "3p_conditional",
            "2s_imperative",
            "2p_imperative",
            "habitual_past",
        }
        assert set(forms.keys()) == expected_keys

    def test_3s_equals_3p(self) -> None:
        """3rd person singular and plural are always identical."""
        forms = conjugate_verb("dirbti", "dirba", "dirbo")
        assert forms is not None
        assert forms["3s_present"] == forms["3p_present"]
        assert forms["3s_past"] == forms["3p_past"]
        assert forms["3s_future"] == forms["3p_future"]
