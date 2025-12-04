This project primarily uses Python, with a PYTHONROOT of src/ .

The main purpose of the project is to create a multilingual linguistic
database, and to generate files for the Trakaido language-learning app.

src/barsukas is the main web UX used by humans to interact with the database.

src/agents contains scripts to do bulk operations against the database,
generally making LLM calls.  Each agent is named with a Lithuanian animal
name.

src/wordfreq/storage contains the SQLAlchemy schema for the main database.

src/clients/ contains all code to access LLMs.  The system was built around
the expectation that different small local models would run for different
tasks; currently it is expected that a remote ChatGPT/Claude/Gemini is used.

Most of the remaining code of relevance is in src/wordfreq ; many of the other
top-level directories in src/ are deprecated.

Tests are in src/tests ; any changes to src/clients require tests.  Changes to
barsukas generally do not require tests.  Do not run any tests other than a
pycompile to check for code mistakes; ask the developer to test the change in
their local browser.

When writing HTML files, always use ordinary form submits for POST data - do
not do an AJAX-based submission.  Avoid using disappearing UX elements.
