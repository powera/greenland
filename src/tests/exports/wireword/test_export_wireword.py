from storage.backend.config import BackendType, DataSourceConfig
from exports.wireword.export_wireword import WirewordExporter


def test_format_missing_verb_translation_warning_preview_and_count() -> None:
    exporter = WirewordExporter(
        config=DataSourceConfig(backend_type=BackendType.SQLITE),
        language="lt",
    )

    missing_forms = [
        (1480, "give", "verb/lt_1p_future"),
        (1481, "take", "verb/lt_3s_past"),
    ]

    message = exporter._format_missing_verb_translation_warning(missing_forms)

    assert "Found 2 missing form(s)." in message
    assert "lemma_id=1480" in message
    assert "lemma_text='give'" in message
    assert "grammatical_form='verb/lt_1p_future'" in message
    assert "Falling back to generated English labels" in message


def test_format_missing_verb_translation_warning_truncates_preview() -> None:
    exporter = WirewordExporter(
        config=DataSourceConfig(backend_type=BackendType.SQLITE),
        language="lt",
    )

    missing_forms = [(1000 + i, f"lemma{i}", f"verb/lt_{i}_future") for i in range(12)]

    message = exporter._format_missing_verb_translation_warning(missing_forms)

    assert "Found 12 missing form(s)." in message
    assert "... and 2 more missing forms" in message
