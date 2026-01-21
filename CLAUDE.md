This project primarily uses Python, with a PYTHONROOT of src/ .

The main purpose of the project is to create a multilingual linguistic
database, and to generate files for the Trakaido language-learning app.

Use DataSourceConfig (defined in src/wordfreq/storage/backend/config.py) to
pass configuration (db_path, model_name, debug, backend_type, etc.) to agents
and other components. Do not pass db_path or similar parameters directly.

src/barsukas is the main web UX used by humans to interact with the database.

src/agents contains scripts to do bulk operations against the database,
generally making LLM calls.  Each agent is named with a Lithuanian animal
name.

src/wordfreq/storage contains the SQLAlchemy schema for the main database;
the default location is src/wordfreq/data/linguistics.sqlite .

src/wordfreq/storage/translation_helpers.py contains all language code
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

For agent CLI scripts that should be runnable directly, add this at the top
(before any local imports), adjusting the number of .parent calls to reach src/:
  import sys
  from pathlib import Path
  if str(Path(__file__).parent.parent) not in sys.path:
      sys.path.insert(0, str(Path(__file__).parent.parent))

Tests are in src/tests ; any changes to src/clients require tests.  Changes to
barsukas generally do not require tests.  Before creating a Git commit, always
run black and mypy on modified Python files to ensure code quality and type
correctness.  For barsukas changes, ask the developer to test the change in
their local browser.

After cloning, enable pre-commit hooks to automatically check black formatting:
  git config core.hooksPath hooks

When writing HTML files, always use ordinary form submits for POST data - do
not do an AJAX-based submission.  Avoid using disappearing UX elements.

When modifying files in data/release :
* make sure the GUID prefixes match those in wordfreq/storage/models/guid_prefixes.py
* when creating a new "subtype", follow those instructions for updates
* do not "change" GUIDs - keep the file sorted by GUID, and add new words at
  the end, leaving gaps in GUIDs for removed words is expected
* the "difficulty level" for newly added words should be -1 unless otherwise requested
* words should be in "lemma" form, and should specify one definition of a
  word, using a disambiguation if necessary
