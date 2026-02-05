# Tests

## Running Tests

```bash
# All tests
python run_tests.py

# Specific directory
python run_tests.py src/tests/clients

# Specific file (via pytest directly)
PYTHONPATH=src pytest src/tests/clients/test_batch_queue.py
```

The test runner (`run_tests.py`) auto-discovers `test_*.py` files under `src/`
using unittest discovery, with `src/` on the Python path.

## Test Organization

```
tests/
├── clients/               # Best coverage
│   ├── test_batch_queue.py
│   ├── test_lib.py
│   ├── test_openai_batch_client.py
│   ├── test_openai_schema_strict.py
│   ├── audio/
│   │   ├── test_gpt_voices.py
│   │   └── test_openai_tts.py
│   └── wiktionary/
│       └── test_wiktionary_client.py
├── agents/
│   ├── test_dramblys_import.py
│   ├── test_vieversys_paths.py
│   └── common/
│       ├── test_common_args.py
│       └── test_lemma_selection.py
├── langtools/
│   └── test_form_alignment.py
├── lib/
│   ├── test_sentence_generation.py
│   └── benchmarks/
│       ├── test_llm_generators.py
│       └── test_local_generators.py
├── wordfreq/
│   ├── test_connection_pool.py
│   └── test_sentence_analysis.py
└── benchmarks/
    └── test_validation.py
```

## Current Coverage

Test coverage is uneven across the codebase:

- **`clients/`** - Good coverage. All changes to `src/clients` require tests
  (per project policy).
- **`agents/`** - Light coverage. A few import and path tests; most agent
  logic is not yet unit-tested.
- **`langtools/`** - Minimal. One form alignment test.
- **`wordfreq/`** - Minimal. Connection pool and sentence analysis only.
- **`lib/`** and **`benchmarks/`** - A handful of generator and validation tests.
- **`barsukas/`** - No automated tests. Changes are tested manually in the browser.

## Writing Tests

Tests use unittest (the runner) and pytest (also works). Use pytest fixtures
and assertions in new tests.

```python
import pytest

def test_example():
    assert 1 + 1 == 2

@pytest.fixture
def sample_data():
    return {"key": "value"}

def test_with_fixture(sample_data):
    assert sample_data["key"] == "value"
```

For database tests, use in-memory SQLite:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from wordfreq.storage.models.schema import Base

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
```

## Conventions

- **File naming:** `test_*.py`
- **Function naming:** `test_*`
- **No tests required for:** `barsukas/` (manual browser testing), `benchmarks/` (no type hints enforced)
- **Tests required for:** any changes to `src/clients/`
