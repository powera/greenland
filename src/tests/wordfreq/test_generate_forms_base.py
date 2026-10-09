import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from langtools.llm_forms_base import FormsAnswer
from storage.backend.config import BackendType, DataSourceConfig
from storage.crud.uncertain_llm_result import get_uncertain_llm_result
from storage.models.schema import Base, DerivativeForm, Lemma
from storage.models.uncertain_llm_result import TOPIC_FORMS
from storage.translation_helpers import set_translation
from wordfreq.translation.generate_forms_base import (
    FormGenerationConfig,
    extract_gender_from_forms,
    process_lemma_forms,
)
from wordfreq.translation.generate_forms_tasks import FORM_GENERATION_TASKS, get_task_key


class TestExtractGenderFromForms(unittest.TestCase):
    def _lt_noun_config(self) -> FormGenerationConfig:
        return FormGenerationConfig(
            language_code="lt",
            language_name="Lithuanian",
            pos_type="noun",
            form_mapping={},
            generator_name="query_lithuanian_noun_declensions",
            min_forms_threshold=2,
            base_form_identifier="nominative_singular",
            extract_gender=True,
        )

    def test_lithuanian_masculine_ending(self) -> None:
        forms = {"nominative_singular": "vilkas"}
        self.assertEqual(extract_gender_from_forms(forms, self._lt_noun_config()), "masculine")

    def test_lithuanian_feminine_ending(self) -> None:
        forms = {"nominative_singular": "upė"}
        self.assertEqual(extract_gender_from_forms(forms, self._lt_noun_config()), "feminine")


if __name__ == "__main__":
    unittest.main()


def test_live_low_confidence_forms_are_recorded_and_skipped(tmp_path: Path) -> None:
    """process_lemma_forms gates a model's answer and skips the lemma next time."""
    db_path = tmp_path / "forms.sqlite"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    with Session(engine) as setup:
        lemma = Lemma(lemma_text="house", definition_text="a building", pos_type="noun")
        setup.add(lemma)
        setup.flush()
        set_translation(setup, lemma, "de", "Haus")
        setup.commit()
        lemma_id = lemma.id
    engine.dispose()

    config = DataSourceConfig(
        backend_type=BackendType.SQLITE, sqlite_path=str(db_path), model="gpt-6-luna"
    )
    task_config = FORM_GENERATION_TASKS[get_task_key("de", "noun")].config
    field = next(iter(task_config.form_mapping))
    answer = FormsAnswer({field: "Haus"}, True, 0.4, "not sure")
    client = MagicMock()

    with patch(
        "wordfreq.translation.generate_forms_base.generate_forms", return_value=answer
    ) as generate:
        assert not process_lemma_forms(client, lemma_id, config, task_config)
        assert not process_lemma_forms(client, lemma_id, config, task_config)
        assert generate.call_count == 1
        process_lemma_forms(client, lemma_id, config, task_config, retry_uncertain=True)
        assert generate.call_count == 2

    with Session(create_engine(f"sqlite:///{db_path}")) as check:
        assert check.query(DerivativeForm).filter_by(lemma_id=lemma_id).count() == 0
        row = get_uncertain_llm_result(check, TOPIC_FORMS, "de", lemma_id=lemma_id)
        assert row is not None
        assert row.note == f"gpt-6-luna leaned {field}=Haus (0.40): not sure"
