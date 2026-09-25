import os

DEFAULT_MODEL: str = "gpt-6-luna"

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

# The checked-in JSONL release tree: the exported, reviewable form of the
# linguistic database. Its per-entity subdirectories ("lemmas", "sentences",
# ...) are named by storage.release.registry rather than spelled out at call
# sites, so this constant is the only place the root itself is derived.
RELEASE_DIR = os.path.join(PROJECT_ROOT, "data", "release")

# Curriculum bounds, in three bands with deliberate gaps between them:
#
#   1-30        the curated general core, taught in order; the rebalancer
#               fills it from 1 and uses only as many levels as it needs
#   100-499     "named" units, each a single pos_subtype (Animals 3, Body
#               Parts, Appliances 2)
#   1000-1299   topic-specific extensions, outside the general course
#
# The gaps are the point. Each old level 21-64 maps to ``100 + (old-21)*5``,
# and the five numbers it owns are where its single-topic units go: the level
# that held a mixed bag of 45 words becomes Animals 5, Disease 4 and so on,
# without renumbering anything after it.
#
# Within the named band the numbers are **not** a teaching order. A unit is
# reached when its prerequisites are met, so Disease 1 at 670 may well come
# before Animals 9 at 129. Only the core (1-20) is strictly sequential.
#
# ``-1`` is the intentional exclusion sentinel, not a level.
MIN_DIFFICULTY_LEVEL: int = 1
CORE_DIFFICULTY_LEVEL_MAX: int = 30
NAMED_DIFFICULTY_LEVEL_MIN: int = 100
GENERAL_DIFFICULTY_LEVEL_MAX: int = 499
TOPIC_DIFFICULTY_LEVEL_MIN: int = 1000
MAX_DIFFICULTY_LEVEL: int = 1299
EXCLUDE_DIFFICULTY_LEVEL: int = -1

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
