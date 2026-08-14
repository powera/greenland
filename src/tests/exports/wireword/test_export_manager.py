from storage.backend.config import BackendType, DataSourceConfig
from exports.wireword.export_manager import TrakaidoExporter


def test_trakaido_exporter_supports_japanese() -> None:
    exporter = TrakaidoExporter(
        config=DataSourceConfig(backend_type=BackendType.SQLITE),
        language="ja",
    )

    assert exporter.language == "ja"
    assert exporter.language_name == "Japanese"
    assert exporter.language_field == "japanese_translation"
