import os

DEFAULT_MODEL = "gpt-5-mini"

# Get the src directory
SRC_DIR = os.path.dirname(os.path.abspath(__file__))

# Get the project root (top-level directory)
PROJECT_ROOT = os.path.dirname(SRC_DIR)

# Agents directory
AGENTS_DIR = os.path.join(SRC_DIR, "agents")

# Benchmark paths - Import from benchmarks.benchmark_constants for new code
# These are kept for backwards compatibility with old benchmark generators in src/lib/benchmarks/
try:
    from benchmarks import benchmark_constants as _bc

    # Convert Path objects to strings for backwards compatibility
    BENCHMARK_DATA_DIR = str(_bc.BENCHMARK_DATA_DIR)
    SCHEMA_DIR = str(_bc.BENCHMARK_SCHEMA_DIR)
    SQLITE_DB_PATH = str(_bc.BENCHMARKS_DB_PATH)
except ImportError:
    # Fallback if benchmarks module not available
    BENCHMARK_DATA_DIR = os.path.join(SRC_DIR, "benchmarks")
    SCHEMA_DIR = os.path.join(SRC_DIR, "benchmarks", "schema")
    SQLITE_DB_PATH = os.path.join(SCHEMA_DIR, "benchmarks.db")

KEY_DIR = os.path.join(PROJECT_ROOT, "keys")
OUTPUT_DIR = os.path.join(os.path.dirname(PROJECT_ROOT), "greenland_output")

# Wordfreq directories
WORDFREQ_DB_PATH = os.path.join(SRC_DIR, "wordfreq", "data", "linguistics.sqlite")
WORDFREQ_TEMPLATE_DIR = os.path.join(SRC_DIR, "wordfreq", "templates")
IPA_DICT_PATH = os.path.join(SRC_DIR, "wordfreq", "data", "en_US_ipadict.txt")

# Wiki corpus directories
# WIKI_CORPUS_BASE_PATH = os.path.join(PROJECT_ROOT, "data", "wikicorpus")
WIKI_CORPUS_BASE_PATH = "/Volumes/kelvin/wikipedia/2022_MAY"
WIKI_CORPUS_PREFIX = "enwiki-20220501"
# Note: wiki_index.schema is currently in benchmarks/schema but should probably move
WIKI_INDEX_SCHEMA_PATH = os.path.join(SRC_DIR, "benchmarks", "schema", "wiki_index.schema")

# PostgreSQL configuration
# Template URL with placeholder for password - the actual password is loaded from keys/postgres.key
POSTGRES_URL_TEMPLATE = "postgresql://postgres:[YOUR-PASSWORD]@db.srouvwdghrmwkxnzyzqz.supabase.co:5432/postgres?sslmode=require"
POSTGRES_SCHEMA = "trakaido"
