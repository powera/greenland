# Exemplars Framework

The Exemplars framework allows you to compare responses from different AI models to specific prompts. Unlike benchmarks that focus on scoring models across many questions, exemplars focus on qualitative comparison of responses to the same prompt.

## Overview

Exemplars are designed for:
- Side-by-side comparison of model responses to identical prompts
- Qualitative evaluation of model capabilities for specific tasks
- Generating sample outputs for demonstrations or analysis
- Testing specific model capabilities without binary scoring

## Directory Structure

```
lib/
└── exemplars/
    ├── base.py           # Core framework code
    ├── cli.py            # Command-line interface
    ├── tasks/            # Individual exemplar definitions
    │   ├── __init__.py
    │   ├── granite_definition_exemplar.py
    │   └── wars_of_roses_exemplar.py
    └── reports/          # Generated HTML reports
        ├── granite_definition.html
        ├── wars_of_roses_essay.html
        └── index.html
```

## Usage

### Running Exemplars from Command Line

```bash
# List all available exemplars
python -m lib.exemplars.cli list

# List available models from the benchmarks database
python -m lib.exemplars.cli list --models

# Run a specific exemplar with default models (pulled from database)
python -m lib.exemplars.cli run granite_definition

# Run a specific exemplar with specified models
python -m lib.exemplars.cli run wars_of_roses_essay --models gpt-4o-mini-2024-07-18 smollm2:360m

# Run all exemplars with the first model from the database
python -m lib.exemplars.cli run

# Run all exemplars with a specific model
python -m lib.exemplars.cli run --models gpt-4o-mini-2024-07-18

# Generate reports for all exemplars
python -m lib.exemplars.cli report
```

### Running Exemplars from Python

```python
from lib.exemplars import registry, runner, storage, report_generator
from lib.exemplars.tasks.granite_definition_exemplar import run_granite_definition_exemplar

# Run a specific exemplar with models from the database
run_granite_definition_exemplar()

# Get available models from the database
available_models = runner.get_model_names()
print(f"Available models: {available_models}")

# Run with specific models
run_granite_definition_exemplar(models=["gpt-4o-mini-2024-07-18", "smollm2:360m"])

# Or use the general functions
from lib.exemplars import compare_models, generate_report

# Run with models from the database (first 2 models)
compare_models("granite_definition", runner.get_model_names()[:2])

# Generate an HTML report
generate_report("granite_definition")
```

## Creating New Exemplars

To create a new exemplar:

1. Create a new Python file in `lib/exemplars/tasks/`
2. Use the `register_exemplar` function to define your exemplar
3. Implement a runner function if desired

Example:

```python
from lib.exemplars import register_exemplar, ExemplarType, compare_models, generate_report

# Register the exemplar
register_exemplar(
    id="custom_exemplar",
    name="My Custom Exemplar",
    prompt="Write a sonnet about machine learning.",
    description="Tests the model's ability to write poetry about technical topics.",
    type=ExemplarType.CREATIVE,
    tags=["poetry", "technical"],
    context="You are a poet with technical expertise.",
    temperature=0.7
)

# Function to run this exemplar
def run_custom_exemplar(models=None):
    if models is None:
        models = ["gpt-4o-mini-2024-07-18", "claude-3-sonnet-20240229"]
    compare_models("custom_exemplar", models)
    return generate_report("custom_exemplar")

if __name__ == "__main__":
    run_custom_exemplar()
```

## Viewing Reports

After running exemplars, HTML reports are generated in the `lib/exemplars/reports/` directory. Open the `index.html` file in a web browser to see all available reports, or open individual report files directly.

## Initial Exemplars

Two exemplars are included to start:

1. **Granite Definition** - Tests comprehensive word definition capabilities
2. **Wars of the Roses Essay** - Tests historical essay writing in a concise format

## Integration with Existing Code

The exemplars framework is integrated with your existing benchmarks system:

- **Model Information**: Models are automatically pulled from the benchmarks database 
- **Unified Client**: Uses the same client system for model access as the benchmarks
- **Database Integration**: Shares the same SQLite database infrastructure
- **Code Structure**: Follows similar patterns as the benchmarks system for consistency

This integration ensures that when you add new models to your benchmarks database, they'll automatically be available for exemplar testing without any additional configuration.