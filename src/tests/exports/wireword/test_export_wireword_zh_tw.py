"""The zh-tw WireWord export reads zh-tw rows and nothing else.

Traditional Chinese used to be exported as language="zh" with
simplified_chinese=False: it read zh rows, preferred a zh-tw row when one
existed, and otherwise ran the zh text through opencc.  That was the one
read-time dialect-to-parent fallback in the codebase.  zh-tw is now an ordinary
export language, so a lemma with no zh-tw translation is absent from the zh-tw
export rather than filled in from zh.
"""

from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from exports.wireword.export_wireword import WirewordExporter
from langtools.zh.converter import OPENCC_AVAILABLE
from storage.models import Base, Lemma
from storage.models.schema import LemmaTranslation

# guid -> (zh translation, zh-tw translation or None)
_FIXTURE_WORDS = {
    "N01_001": ("电脑", "電腦"),
    "N01_002": ("软件", "軟體"),  # Taiwan uses a different word, not just a script
    "N01_003": ("鸡", None),  # zh only: no zh-tw translation generated yet
}


@pytest.fixture()
def db_engine(tmp_path: object) -> Generator[Engine, None, None]:
    import storage.models  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path}/zh_tw_export.sqlite")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def session(db_engine: Engine) -> Generator[Session, None, None]:
    factory = sessionmaker(bind=db_engine)
    db_session = factory()

    for index, (guid, (zh_text, zh_tw_text)) in enumerate(_FIXTURE_WORDS.items()):
        lemma = Lemma(
            lemma_text=f"word{index}",
            definition_text=f"Test lemma {index}.",
            pos_type="noun",
            pos_subtype="electronic_device",
            guid=guid,
            difficulty_level=1,
        )
        db_session.add(lemma)
        db_session.flush()
        db_session.add(LemmaTranslation(lemma_id=lemma.id, language_code="zh", translation=zh_text))
        if zh_tw_text is not None:
            db_session.add(
                LemmaTranslation(lemma_id=lemma.id, language_code="zh-tw", translation=zh_tw_text)
            )
    db_session.commit()

    yield db_session
    db_session.close()


def _export_by_guid(session: Session, language: str) -> dict[str, str]:
    exporter = WirewordExporter(language=language)
    entries = exporter.query_trakaido_data_for_wireword(session=session)
    return {entry["GUID"]: entry["target_language"] for entry in entries}


def test_zh_export_reads_zh_translations(session: Session) -> None:
    assert _export_by_guid(session, "zh") == {
        "N01_001": "电脑",
        "N01_002": "软件",
        "N01_003": "鸡",
    }


def test_zh_tw_export_reads_zh_tw_translations(session: Session) -> None:
    """Not converted zh text: 軟體 is Taiwan's word, opencc would give 軟件."""
    exported = _export_by_guid(session, "zh-tw")

    assert exported["N01_001"] == "電腦"
    assert exported["N01_002"] == "軟體"


def test_zh_tw_export_omits_lemmas_with_no_zh_tw_translation(session: Session) -> None:
    """A blank means "not generated yet", never "substitute the parent's"."""
    exported = _export_by_guid(session, "zh-tw")

    assert "N01_003" not in exported


def test_zh_tw_export_normalizes_a_row_stored_in_the_wrong_script(session: Session) -> None:
    """A zh-tw row that holds Simplified text is repaired, not shipped as-is."""
    if not OPENCC_AVAILABLE:
        pytest.skip("opencc not installed")

    lemma = session.query(Lemma).filter(Lemma.guid == "N01_003").one()
    session.add(LemmaTranslation(lemma_id=lemma.id, language_code="zh-tw", translation="鸡"))
    session.commit()

    assert _export_by_guid(session, "zh-tw")["N01_003"] == "雞"
