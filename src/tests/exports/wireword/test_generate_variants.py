import json
from pathlib import Path
from typing import Any

from exports.wireword.generate_variants import (
    VARIANTS_FILENAME,
    build_variants_registry,
    generate_variants,
    get_variant_directory,
)
from langtools.dialect_overrides import get_translation_target_dialects


def _load(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_spanish_registry_lists_base_and_latin_america() -> None:
    registry = build_variants_registry("es")

    assert registry is not None
    assert registry["language"] == "spanish"
    assert registry["default_variant"] == "es"
    assert [v["id"] for v in registry["variants"]] == ["es", "es-419"]


def test_default_variant_is_present_among_the_variants() -> None:
    """The client falls back to default_variant, so it must resolve."""
    for lang in ("es", "zh", "pt"):
        registry = build_variants_registry(lang)
        assert registry is not None, lang
        ids = [v["id"] for v in registry["variants"]]
        assert registry["default_variant"] in ids, lang


def test_every_storage_dialect_is_offered_as_a_variant() -> None:
    """A dialect with its own bundle is reachable, or learners cannot pick it."""
    offered = set()
    for lang in ("es", "zh", "pt"):
        registry = build_variants_registry(lang)
        assert registry is not None, lang
        offered.update(v["id"] for v in registry["variants"])

    assert set(get_translation_target_dialects()) <= offered


def test_presentation_dialects_are_not_offered() -> None:
    """es-mx stores no wirewords, so there is no directory to send a client to."""
    registry = build_variants_registry("es")

    assert registry is not None
    assert "es-mx" not in [v["id"] for v in registry["variants"]]


def test_regions_do_not_overlap_between_variants() -> None:
    """A region picks at most one variant, or selection is order-dependent."""
    for lang in ("es", "zh", "pt"):
        registry = build_variants_registry(lang)
        assert registry is not None, lang
        seen: set[str] = set()
        for variant in registry["variants"]:
            regions = set(variant["default_regions"])
            assert not (regions & seen), f"{lang}: {regions & seen}"
            seen |= regions


def test_variant_directory_matches_the_served_directory_name() -> None:
    assert get_variant_directory("es") == "spanish"
    assert get_variant_directory("es-419") == "spanish_419"
    assert get_variant_directory("zh-tw") == "chinese_tw"


def test_language_without_variants_emits_nothing(tmp_path: Path) -> None:
    """A missing file is how a single-variant language is spelled."""
    success, path = generate_variants(str(tmp_path), "lt")

    assert success
    assert path is None
    assert not (tmp_path / VARIANTS_FILENAME).exists()


def test_variant_directory_gets_no_registry_of_its_own(tmp_path: Path) -> None:
    """Only the base language ships one; it decides which variant to load."""
    success, path = generate_variants(str(tmp_path), "es-419")

    assert success
    assert path is None
    assert not (tmp_path / VARIANTS_FILENAME).exists()


def test_generate_variants_writes_the_registry(tmp_path: Path) -> None:
    success, path = generate_variants(str(tmp_path), "es")

    assert success
    assert path is not None
    registry = _load(path)
    assert registry["version"] == 1
    latam = next(v for v in registry["variants"] if v["id"] == "es-419")
    assert latam["directory"] == "spanish_419"
    assert latam["speech_locale"] == "es-MX"
    assert "US" in latam["default_regions"]


def test_registry_entries_carry_every_required_field(tmp_path: Path) -> None:
    """Field set per docs/language-variants.md; a missing one breaks the picker."""
    required = {
        "id",
        "directory",
        "language_code",
        "display_name",
        "native_name",
        "description",
        "default_regions",
        "source_languages",
    }
    for lang in ("es", "zh", "pt"):
        registry = build_variants_registry(lang)
        assert registry is not None, lang
        for variant in registry["variants"]:
            assert required <= set(variant), f"{lang}/{variant['id']}"
            assert all(variant[key] for key in required - {"default_regions"})
