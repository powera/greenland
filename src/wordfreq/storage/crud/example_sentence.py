"""CRUD operations for ExampleSentence model."""

from wordfreq.storage.models.schema import ExampleSentence, DerivativeForm


def add_example_sentence(
    session,
    derivative_form: DerivativeForm,
    example_text: str
) -> ExampleSentence:
    """Add an example sentence for a derivative form."""
    example = ExampleSentence(
        derivative_form_id=derivative_form.id,
        example_text=example_text
    )
    session.add(example)
    # Don't commit here, let the caller handle the transaction
    return example
