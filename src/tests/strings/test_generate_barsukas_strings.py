"""Tests for Barsukas template replacement generation."""

from pathlib import Path

import pytest

from strings.generate_barsukas_strings import (
    CatalogState,
    CatalogUpdateStats,
    Span,
    build_text_replacement,
    classify_extracted_segment,
    plan_template_replacements,
)


def _create_catalog_states(tmp_path: Path) -> tuple[CatalogState, CatalogState]:
    standard_root = tmp_path / "strings" / "barsukas"
    cstr_root = standard_root / "cstr"
    return (CatalogState(standard_root), CatalogState(cstr_root, allow_common_reuse=False))


def test_classify_extracted_segment_distinguishes_short_sentence_and_multi() -> None:
    assert classify_extracted_segment("Search") == "short"
    assert classify_extracted_segment("This is a sentence.") == "sentence"
    assert classify_extracted_segment("One sentence. Another sentence!") == "multi_sentence"


def test_build_text_replacement_emits_expected_accessor_by_classification(tmp_path: Path) -> None:
    standard_state, cstr_state = _create_catalog_states(tmp_path)
    standard_stats = CatalogUpdateStats()
    cstr_stats = CatalogUpdateStats()

    short_replacement = build_text_replacement(
        content="<div>Search</div>",
        span=Span(start=5, end=11),
        namespace="lemmas",
        standard_catalog_state=standard_state,
        cstr_catalog_state=cstr_state,
        standard_stats=standard_stats,
        cstr_stats=cstr_stats,
    )
    assert short_replacement is not None
    assert short_replacement.replacement_text == "{{ LSTR.search }}"

    sentence_replacement = build_text_replacement(
        content="<div>This is a complete sentence.</div>",
        span=Span(start=5, end=33),
        namespace="lemmas",
        standard_catalog_state=standard_state,
        cstr_catalog_state=cstr_state,
        standard_stats=standard_stats,
        cstr_stats=cstr_stats,
    )
    assert sentence_replacement is not None
    assert sentence_replacement.replacement_text == "{{ SSTR.lemmas.this_is_a_complete_sentence }}"

    multi_sentence_content = "<div>One sentence. Another sentence!</div>"
    multi_sentence_replacement = build_text_replacement(
        content=multi_sentence_content,
        span=Span(start=5, end=multi_sentence_content.index("</div>")),
        namespace="lemmas",
        standard_catalog_state=standard_state,
        cstr_catalog_state=cstr_state,
        standard_stats=standard_stats,
        cstr_stats=cstr_stats,
    )
    assert multi_sentence_replacement is not None
    assert (
        multi_sentence_replacement.replacement_text
        == "{{ CSTR.lemmas.one_sentence_another_sentence }}"
    )


def test_plan_template_replacements_honors_directives_and_escape_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from strings import generate_barsukas_strings as generator

    template_root = tmp_path / "src" / "barsukas" / "templates"
    template_path = template_root / "lemmas" / "sample.html"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(
        """
<div><!-- strings:sentence -->Token</div>
<div><!-- strings:do-not-transform -->Literal text</div>
<input placeholder="Fill out this field.">
<p>One sentence. Another sentence!</p>
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(generator, "TEMPLATES_ROOT", template_root)

    standard_state, cstr_state = _create_catalog_states(tmp_path)
    standard_stats = CatalogUpdateStats()
    cstr_stats = CatalogUpdateStats()

    replacements = plan_template_replacements(
        template_path=template_path,
        standard_catalog_state=standard_state,
        cstr_catalog_state=cstr_state,
        standard_stats=standard_stats,
        cstr_stats=cstr_stats,
    )

    replacement_texts = [item.replacement_text for item in replacements]
    assert "{{ SSTR.lemmas.token }}" in replacement_texts
    assert "{{ SSTR.lemmas.fill_out_this_field }}" in replacement_texts
    assert "{{ CSTR.lemmas.one_sentence_another_sentence }}" in replacement_texts
    assert all("Literal text" not in item.original_text for item in replacements)
