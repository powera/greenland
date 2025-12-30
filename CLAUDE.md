This project primarily uses Python, with a PYTHONROOT of src/ .

The main purpose of the project is to create a multilingual linguistic
database, and to generate files for the Trakaido language-learning app.

src/barsukas is the main web UX used by humans to interact with the database.

src/agents contains scripts to do bulk operations against the database,
generally making LLM calls.  Each agent is named with a Lithuanian animal
name.

src/wordfreq/storage contains the SQLAlchemy schema for the main database.

src/wordfreq/storage/translation_helpers.py contains all language code
manipulation functions and constants (LLM_FIELD_TO_LANG_CODE,
LANG_CODE_TO_LLM_FIELD, convert_llm_response_to_lang_codes, etc.).
Do not create local language mappings - import from translation_helpers.py.

src/clients/ contains all code to access LLMs.  The system was built around
the expectation that different small local models would run for different
tasks; currently it is expected that a remote ChatGPT/Claude/Gemini is used.

Most of the remaining code of relevance is in src/wordfreq ; many of the other
top-level directories in src/ are deprecated.

IMPORTANT: Always use absolute imports (e.g., "from agents.common_args import")
rather than relative updir imports (e.g., "from ..common_args import"). This
ensures imports work correctly regardless of how the code is invoked.

To run scripts, always use PYTHONPATH and never use cd commands:
  PYTHONPATH=src python src/agents/dramblys.py --help

For agent CLI scripts that should be runnable directly, add this at the top
(before any local imports), adjusting the number of .parent calls to reach src/:
  import sys
  from pathlib import Path
  if str(Path(__file__).parent.parent) not in sys.path:
      sys.path.insert(0, str(Path(__file__).parent.parent))

The number of .parent calls depends on depth: for src/agents/foo.py use .parent.parent,
for src/agents/dramblys/__main__.py use .parent.parent.parent, etc.

Tests are in src/tests ; any changes to src/clients require tests.  Changes to
barsukas generally do not require tests.  Do not run any tests other than a
pycompile to check for code mistakes; ask the developer to test the change in
their local browser.

When writing HTML files, always use ordinary form submits for POST data - do
not do an AJAX-based submission.  Avoid using disappearing UX elements.
