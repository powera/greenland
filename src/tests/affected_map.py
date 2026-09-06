"""Which test directories to run for a change under a given source directory.

Backs `./run_tests.sh affected`.  A static map, deliberately: it needs no build
step, does not go stale silently the way a recorded coverage map does, and is
readable and editable when you disagree with it.

The entries are not guesswork.  They were derived from an instrumented run of
the full suite (coverage with a per-test dynamic context) that recorded which
tests actually execute each source directory, then rounded up.  The measured
cross-directory edges are why several source dirs list more than their mirror:

  storage    -> barsukas(160) words(128) wordfreq(89) sentences(86) tests
  langtools  -> clients(187!) sentences(87) words(60) storage(41) wordfreq(39)
  ipa        -> langtools(33) storage(27) wordfreq(26) words(20) sentences(18)
  clients    -> barsukas(11) audiotools(10)
  words      -> agents(45) sentences(37) barsukas(15)

langtools is the surprise worth keeping: the wiktionary parser tests under
src/tests/clients exercise more langtools code than src/tests/langtools does.
A mirror-only map would have missed all of it.

Source dirs with no tests of their own (audioshoe, strings, exports, util,
verbalator, reports) map to whatever actually covers them.

Regenerate the underlying measurement with tools/measure_test_coverage.py after
a large refactor, then update this map by hand.  Over-selection is the intended
failure mode: when in doubt add a directory rather than removing one.
"""

from __future__ import annotations

# Source directory (relative to src/) -> test directories (relative to src/tests/).
DIRECTORY_MAP: dict[str, tuple[str, ...]] = {
    "agents": ("agents", "workqueue", "sentences"),
    "audioshoe": ("barsukas",),
    "audiotools": ("audiotools", "workqueue"),
    "barsukas": ("barsukas",),
    "benchmarks": ("benchmarks", "lib"),
    "clients": ("clients", "barsukas", "audiotools"),
    "concepts": ("concepts", "storage"),
    "exports": ("exports", "storage"),
    "idioms": ("storage", "words"),
    "ipa": ("ipa", "langtools", "storage", "wordfreq", "words", "sentences"),
    "langtools": ("langtools", "clients", "sentences", "words", "storage", "wordfreq"),
    "reports": ("reports", "agents", "storage"),
    "regtest": ("storage",),
    "sentences": ("sentences", "workqueue", "agents", "storage"),
    "storage": ("storage", "barsukas", "words", "wordfreq", "sentences"),
    "strings": ("strings", "barsukas"),
    "util": ("clients", "workqueue", "sentences", "agents", "benchmarks"),
    "verbalator": ("sentences",),
    "verification": ("words", "storage"),
    "wordfreq": ("wordfreq", "words", "sentences", "storage"),
    "words": ("words", "agents", "sentences", "barsukas"),
    "workqueue": ("workqueue", "barsukas", "sentences", "words"),
}

# Non-Python paths no source map covers, matched by prefix (longest wins).
PATH_MAP: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("src/barsukas/templates/", ("barsukas",)),
    ("src/barsukas/static/", ("barsukas",)),
    ("prompts/", ("clients", "langtools")),
    ("data/release/", ("storage",)),
    ("migrations/", ("storage",)),
    ("pyproject.toml", ()),  # tooling config; smoke alone is the right check
)

# A change to a file directly under src/ (constants.py, logging_config.py) is
# broad enough that only the full suite is honest about it.
ROOT_LEVEL_RUNS_EVERYTHING = True
