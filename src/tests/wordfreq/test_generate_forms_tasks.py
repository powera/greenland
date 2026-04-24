import unittest

from wordfreq.translation.generate_forms_tasks import FORM_GENERATION_TASKS, get_task_key


class TestGenerateFormsTasks(unittest.TestCase):
    def test_lithuanian_noun_task_extracts_gender(self) -> None:
        task_key = get_task_key("lt", "noun")
        task = FORM_GENERATION_TASKS[task_key]
        self.assertTrue(task.config.extract_gender)


if __name__ == "__main__":
    unittest.main()
