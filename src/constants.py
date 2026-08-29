import os

DEFAULT_MODEL: str = "gpt-5.6-luna"

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
WORDFREQ_DATA_DIR = os.path.join(PROJECT_ROOT, "data", "wordfreq")
WORDFREQ_DB_PATH = os.path.join(WORDFREQ_DATA_DIR, "linguistics.sqlite")
WORDFREQ_TEMPLATE_DIR = os.path.join(SRC_DIR, "wordfreq", "templates")
# Downloaded Gutenberg book text, kept out of git (data/working is ignored).
# Gutenberg rate-limits, so this cache is deliberately persistent rather than
# a scratch directory that a reboot clears.
GUTENBERG_CACHE_DIR = os.path.join(PROJECT_ROOT, "data", "working", "gutenberg")
IPA_DICT_PATH = os.path.join(WORDFREQ_DATA_DIR, "en_US_ipadict.txt")

# Wiki corpus directories
# WIKI_CORPUS_BASE_PATH = os.path.join(PROJECT_ROOT, "data", "wikicorpus")
WIKI_CORPUS_BASE_PATH = "/Volumes/Dorothy Day/wikipedia/2022_MAY"
WIKI_CORPUS_PREFIX = "enwiki-20220501"
# Wikitext read out of the dump, kept out of git (data/working is ignored).
# Seeking and decompressing a ~2MB multistream block per article is the
# expensive part of a corpus build, and the snapshot is fixed, so what is
# cached can never go stale.  Sharded like the offset index; see
# wordfreq.corpora.wikipedia.wiki_dump.
WIKI_CACHE_DIR = os.path.join(PROJECT_ROOT, "data", "working", "wiki_cache")
# Note: wiki_index.schema is currently in benchmarks/schema but should probably move
WIKI_INDEX_SCHEMA_PATH = os.path.join(SRC_DIR, "benchmarks", "schema", "wiki_index.schema")

# Default minimum seconds between outbound HTTP requests to a single host, used
# to stay under Wikimedia's per-minute request quota. Per-host overrides live in
# clients/http_rate_limits.py; this is the fallback for hosts not listed there.
# Override at runtime with GREENLAND_HTTP_MIN_INTERVAL_SECONDS (0 disables).
DEFAULT_HTTP_MIN_INTERVAL_SECONDS = float(
    os.environ.get("GREENLAND_HTTP_MIN_INTERVAL_SECONDS", "6.0")
)

# PostgreSQL configuration
# Template URL with placeholder for password - the actual password is loaded from keys/postgres.key
POSTGRES_URL_TEMPLATE = "postgresql://postgres:[YOUR-PASSWORD]@db.srouvwdghrmwkxnzyzqz.supabase.co:5432/postgres?sslmode=require"
# Shared pooler URL used as fallback when IPv6 is unavailable (IPv4-only environments)
POSTGRES_POOLER_URL_TEMPLATE = "postgresql://postgres.srouvwdghrmwkxnzyzqz:[YOUR-PASSWORD]@aws-0-us-west-2.pooler.supabase.com:5432/postgres?sslmode=require"
POSTGRES_SCHEMA = "trakaido"
