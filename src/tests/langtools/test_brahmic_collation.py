"""Tests for Brahmic-script collation, including Gurmukhi (Punjabi)."""

from langtools.collation import SORT_KEY_LANGUAGES, generate_sort_key
from langtools.family.brahmic.collation import PA_LETTERS_LOWER, REMAP_LANGUAGES


def test_punjabi_registered() -> None:
    """Punjabi must be wired into both the Brahmic table and the public set."""
    assert "pa" in REMAP_LANGUAGES
    assert "pa" in SORT_KEY_LANGUAGES


def test_punjabi_sort_keys_are_ascii() -> None:
    """Every Gurmukhi sort key must be plain ASCII for binary collation."""
    for word in ["ਪਾਣੀ", "ਕੁੱਤਾ", "ਅੱਗ", "ਗਾਂ", "ਸੇਬ", "ਮਾਂ"]:
        key = generate_sort_key("pa", word)
        assert key is not None
        assert key.isascii(), f"non-ASCII sort key for {word!r}: {key!r}"


def test_punjabi_alphabet_order() -> None:
    """Words sort in Gurmukhi alphabet order (vowel-bearer, then painti)."""
    # ਅ (vowel) < ਸ < ਕ < ਗ < ਪ < ਮ in standard Gurmukhi order.
    words = ["ਮਾਂ", "ਪਾਣੀ", "ਗਾਂ", "ਕੁੱਤਾ", "ਸੇਬ", "ਅੱਗ"]
    ordered = sorted(words, key=lambda w: generate_sort_key("pa", w) or "")
    assert ordered == ["ਅੱਗ", "ਸੇਬ", "ਕੁੱਤਾ", "ਗਾਂ", "ਪਾਣੀ", "ਮਾਂ"]


def test_punjabi_matras_stripped() -> None:
    """Combining vowel signs (matras) must not perturb word-initial ordering."""
    # ਕ and ਕੀ share the same initial consonant; the matra is stripped, so the
    # first letter alone drives the leading sort position.
    bare = generate_sort_key("pa", "ਕ")
    with_matra = generate_sort_key("pa", "ਕੀ")
    assert bare is not None and with_matra is not None
    assert with_matra.startswith(bare)


def test_painti_has_no_duplicate_letters() -> None:
    """The Gurmukhi letter list must be unique so position codes are 1:1."""
    assert len(PA_LETTERS_LOWER) == len(set(PA_LETTERS_LOWER))
