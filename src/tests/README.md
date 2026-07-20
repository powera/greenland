# Tests

## Running Tests

```bash
# Fast import/startup checks (~16 tests, ~1s) - run on every commit
./run_tests.sh smoke

# The tests known to pass (~1700 tests, ~16s) - run often
./run_tests.sh base

# Everything, including the audio suite
./run_tests.sh all

# Extra args pass through to pytest
./run_tests.sh base -k combined_rank -x

# Specific file (via pytest directly)
PYTHONPATH=src pytest src/tests/clients/test_batch_queue.py
```

`base` excludes `src/tests/clients/audio`, which needs the audio submodule
synced to its recorded commit; `all` adds it back.

Tests must never reach a real LLM. `unified_client.generate_chat`,
`warm_model`, and `unload_model` raise `LiveLLMCallInTestError` when called
under pytest, so an unstubbed call fails loudly rather than quietly costing
money. Patch `clients.unified_client.generate_chat` in your test; set
`GREENLAND_ALLOW_LIVE_LLM=1` only for a deliberate recording run.

New smoke tests are marked `@pytest.mark.smoke`. Keep the smoke suite under
~20 tests and free of databases, LLM clients, and fixtures, so it stays fast
enough to run every time.

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
from storage.models.schema import Base

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
