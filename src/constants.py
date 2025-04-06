import os

# Get the src directory
SRC_DIR = os.path.dirname(os.path.abspath(__file__))

# Get the project root (top-level directory)
PROJECT_ROOT = os.path.dirname(SRC_DIR)

# Define common paths relative to project root
BENCHMARK_DATA_DIR = os.path.join(SRC_DIR, "benchmarks")  # TODO: split/move?
SCHEMA_DIR = os.path.join(SRC_DIR, "schema")
SQLITE_DB_PATH = os.path.join(SCHEMA_DIR, "benchmarks.db")  # TODO: fix?
KEY_DIR = os.path.join(PROJECT_ROOT, "keys")
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "templates")
OUTPUT_DIR = os.path.join(os.path.dirname(PROJECT_ROOT), "greenland_output")

# Verbalator directories; possibly should be refactored
VERBALATOR_HTML_DIR = os.path.join(PROJECT_ROOT, "public_html")

# Wordfreq directories
WORDFREQ_DB_PATH = os.path.join(SRC_DIR, "wordfreq", "data", "linguistics.sqlite")