Agent context docs live in `.agents/`.
See `.agents/README.md`, `.agents/AGENTS.md`, and `peer-repo/*-status.md`.

This project primarily uses Python, with a PYTHONROOT of src/ .  Use type
hinting in all new Python code - and add missing type hints to any code other
than src/benchmarks .  Don't re-use variable names (like "key") in the same
function for different purposes (to avoid type / initialization errors).

The main purpose of the project is to create a multilingual linguistic
database, and to generate files for the Trakaido language-learning app.

Use DataSourceConfig (defined in src/storage/backend/config.py) to
pass configuration (db_path, model_name, debug, backend_type, etc.) to agents
and other components. Do not pass db_path or similar parameters directly.

src/barsukas is the main web UX used by humans to interact with the database.

src/agents contains scripts to do bulk operations against the database,
generally making LLM calls.  Each agent is named with a Lithuanian animal
name.  The concept agents (vovere = generator, voverukas = red-link ranker,
voveraite = create concepts from explicit Q-ids) live in src/agents/vovere/ .

Do not run commands that make live Wikidata/Wikipedia API calls (e.g. resolving
Q-ids, fetching concept seeds) without first confirming with the developer.

src/storage contains the SQLAlchemy schema for the main database;
the default location is data/wordfreq/linguistics.sqlite .

src/storage/translation_helpers.py contains all language code
manipulation functions and constants (LLM_FIELD_TO_LANG_CODE,
LANG_CODE_TO_LLM_FIELD, convert_llm_response_to_lang_codes, etc.).
Do not create local language mappings - import from translation_helpers.py.

src/clients/ contains all code to access LLMs.  The system was built around
the expectation that different small local models would run for different
tasks; currently it is expected that a remote ChatGPT/Claude/Gemini is used.

Most of the remaining code of relevance is in src/wordfreq ; many of the other
top-level directories in src/ are deprecated.

Always use absolute imports (e.g., "from agents.common_args import")
rather than relative updir imports (e.g., "from ..common_args import").

To run scripts, always use PYTHONPATH and never use cd commands:
  PYTHONPATH=src python src/agents/dramblys.py --help

Set GREENLAND_DISABLE_LLM=1 to hard-block every live LLM call:

  GREENLAND_DISABLE_LLM=1 PYTHONPATH=src python src/agents/dramblys.py ...

Every backend then raises clients.lib.LLMCallsDisabledError instead of sending
its request.  The check sits at each backend's outbound-request method, not on
a wrapper: backends define their own generate_chat/warm_model and callers hold
client objects directly, so a guard on any higher layer can be routed around.
Use it whenever an agent should run only its mechanical/rule-based paths (e.g.
langtools.en form generation) - the run fails loudly rather than quietly falling
back to a paid model.  It overrides GREENLAND_ALLOW_LIVE_LLM, which only opts a
test out of the separate pytest guard and must never re-enable a disabled
backend.

When you do a live LLM test run of a new agent or pipeline phase, persist the
results to the local database.  The call has already been paid for, and the
point of the run is to see the data land in the real schema - a script that
prints its output and exits verifies only that the LLM replied, leaving the
storage path (column types, coercion helpers, NULL handling, the UI render)
untested and the spend wasted.  Prefer the ordinary persistence path the real
callers use (e.g. sentences.translation.store_translation_results) over
bespoke session writes, so the test run exercises the same code production
does.  Ask before making the call, not before saving what it returns.

For agent CLI scripts that should be runnable directly, add this at the top
(before any local imports), adjusting the number of .parent calls to reach src/:
  import sys
  from pathlib import Path
  if str(Path(__file__).parent.parent) not in sys.path:
      sys.path.insert(0, str(Path(__file__).parent.parent))

Tests are in src/tests. Any changes to src/clients or src/storage/crud require
tests. Changes elsewhere in src/storage should also have tests unless they are
documentation-only or cannot change behavior. Changes to barsukas generally do
not require tests. Before creating a Git commit, always
run black and mypy on modified Python files to ensure code quality and type
correctness.  For barsukas changes, ask the developer to test the change in
their local browser.

Testing
-------
There are four test targets, run via ./run_tests.sh :

  ./run_tests.sh smoke     ~16 tests, ~1s    - run on every commit
  ./run_tests.sh portable  ~1676 tests       - base minus optional-native-dep tests
  ./run_tests.sh base      ~1700 tests, ~16s - run often, not every commit
  ./run_tests.sh all       everything, including the audio suite

Extra arguments pass through to pytest:
  ./run_tests.sh base -k combined_rank -x

smoke asserts only that the tree imports and the barsukas app starts.  It is
deliberately shallow: the recurring failure in this repo is a module being moved
while something that named it as a string was not updated, and imports catch
that immediately.  Mark new smoke tests with @pytest.mark.smoke and keep the
total under ~20 - it is worthless if it stops being fast.  Tests needing a
database, an LLM client, or fixtures belong in base instead.

base is everything except src/tests/clients/audio ; all adds that back.

portable is base with the tests that require optional native dependencies
removed, so the suite runs cleanly where those wheels do not build or install.
It is a superset of smoke and a subset of base.  Three dependencies drive the
exclusions, all listed in PORTABLE_EXCLUDES in run_tests.sh :

* jieba (Chinese segmentation) is imported at module load by
  benchmarks.lib.generators.pinyin_letter_count_generator, and
  benchmarks.lib.utils pulls that generators package in eagerly, so the whole
  benchmarks tree fails to *collect* without it - portable drops
  src/tests/benchmarks and src/tests/lib/benchmarks wholesale.
* pypinyin + pykakasi (Chinese pinyin / Japanese readings) are needed by
  src/tests/wireword/test_readings.py, which asserts real reading output;
  portable drops that file.

The exclusions are pytest path --ignore flags, not -m "not ..." marker
deselection: jieba breaks collection before any marker could deselect a test.
Tests that gate themselves on a missing dep (skipif / skipUnless / an
*_AVAILABLE flag, e.g. test_zh_pinyin_sort.py, test_dialect_overrides.py,
test_cognates.py) already skip cleanly and are not excluded.  When the exclusion
set changes, update both run_tests.sh and this section.

Two things to know when writing tests:

* Tests must never use real credentials.  create_app() gates its benchmarks
  PostgreSQL setup on TESTING for this reason; do not un-gate it.
  Relatedly, unified_client.generate_chat / warm_model / unload_model raise
  LiveLLMCallInTestError when called under pytest without being stubbed, so a
  test that forgets to patch the LLM fails loudly instead of quietly spending
  money.  Patch "clients.unified_client.generate_chat"; only set
  GREENLAND_ALLOW_LIVE_LLM=1 for a deliberate recording run.
* Import benchmarks.lib.utils before importing any module under
  benchmarks.lib.runners or benchmarks.lib.generators .  The utils package init
  eagerly imports every runner and then the registry, and the registry imports
  those runners back for their registration side effects, so entering from a
  runner leaves it half-initialized.  This is a convention, not a fix.

When a test fails after a refactor, check whether the production behavior
changed intentionally before editing the test - and prefer asserting against a
constant or a derived value over a hardcoded literal that will go stale again.

After cloning, enable pre-commit hooks to automatically check black formatting:
  git config core.hooksPath .githooks

When writing HTML templates, try to avoid inline CSS/JS; use separate files.
Also, always use ordinary form submits for POST data - do not do an AJAX-based
submission.  Avoid using disappearing UX elements most of the time.

When modifying files in data/release :
* make sure the GUID prefixes match those in storage/models/guid_prefixes.py
* when creating a new "subtype", follow those instructions for updates
* do not "change" GUIDs - keep the file sorted by GUID, and add new words at
  the end, leaving gaps in GUIDs for removed words is expected
* the "difficulty level" for newly added words should be -1 unless otherwise requested
* words should be in "lemma" form, and should specify one definition of a
  word, using a disambiguation if necessary
* use mainland Chinese with simplified characters
