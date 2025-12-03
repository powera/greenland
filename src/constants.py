import os

DEFAULT_MODEL = "gemma-3-12b-it-q4_k_m.gguf"

# Get the src directory
SRC_DIR = os.path.dirname(os.path.abspath(__file__))

# Get the project root (top-level directory)
PROJECT_ROOT = os.path.dirname(SRC_DIR)

# Agents directory
AGENTS_DIR = os.path.join(SRC_DIR, "agents")

# Define common paths relative to project root
BENCHMARK_DATA_DIR = os.path.join(SRC_DIR, "benchmarks")  # TODO: split/move?
SCHEMA_DIR = os.path.join(SRC_DIR, "benchmarks", "schema")
SQLITE_DB_PATH = os.path.join(SCHEMA_DIR, "benchmarks.db")  # TODO: fix?
KEY_DIR = os.path.join(PROJECT_ROOT, "keys")
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "templates")
OUTPUT_DIR = os.path.join(os.path.dirname(PROJECT_ROOT), "greenland_output")

# Verbalator directories; possibly should be refactored
VERBALATOR_HTML_DIR = os.path.join(PROJECT_ROOT, "public_html")

# Wordfreq directories
WORDFREQ_DB_PATH = os.path.join(SRC_DIR, "wordfreq", "data", "linguistics.sqlite")
WORDFREQ_TEMPLATE_DIR = os.path.join(SRC_DIR, "wordfreq", "templates")
IPA_DICT_PATH = os.path.join(SRC_DIR, "wordfreq", "data", "en_US_ipadict.txt")

# Wiki corpus directories
# WIKI_CORPUS_BASE_PATH = os.path.join(PROJECT_ROOT, "data", "wikicorpus")
WIKI_CORPUS_BASE_PATH = "/Volumes/kelvin/wikipedia/2022_MAY"
WIKI_CORPUS_PREFIX = "enwiki-20220501"
WIKI_INDEX_SCHEMA_PATH = os.path.join(SCHEMA_DIR, "wiki_index.schema")
