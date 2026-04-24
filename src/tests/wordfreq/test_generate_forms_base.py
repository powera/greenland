import unittest

from wordfreq.translation.generate_forms_base import FormGenerationConfig, extract_gender_from_forms


class TestExtractGenderFromForms(unittest.TestCase):
    def _lt_noun_config(self) -> FormGenerationConfig:
        return FormGenerationConfig(
            language_code="lt",
            language_name="Lithuanian",
            pos_type="noun",
            form_mapping={},
            client_method_name="query_lithuanian_noun_declensions",
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
