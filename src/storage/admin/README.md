# Database administration

This package owns database initialization, release loading, corpus setup, and
rank-maintenance operations. Database bootstrap is not an agent operation.

Use the repository-level script for both bootstrap workflows. Loading
`data/release` is the default because that is the normal way to create a useful
Greenland database now:

```bash
# Build a database from the canonical JSONL tree, then load local frequency data.
PYTHONPATH=src python bootstrap_database.py \
  --db-path /path/to/linguistics.sqlite

# Import only checked-in release state, without local frequency enrichment.
PYTHONPATH=src python bootstrap_database.py \
  --db-path /path/to/linguistics.sqlite --release-only

# Rarer path: no release data, only schema plus local corpus/tier/rank sources.
PYTHONPATH=src python bootstrap_database.py \
  --db-path /path/to/linguistics.sqlite --empty
```

Both workflows refuse to replace populated SQLite data. The release workflow
accepts `--force` for an intentional replacement; empty-database bootstrap has
no override because its meaning is specifically “start empty.”

Maintenance operations may run after either bootstrap style:

```bash
PYTHONPATH=src python -m storage.admin --check
PYTHONPATH=src python -m storage.admin --sync-config
PYTHONPATH=src python -m storage.admin --load
PYTHONPATH=src python -m storage.admin --import-tiers
PYTHONPATH=src python -m storage.admin --calc-ranks
```

Barsukas uses `python -m storage.admin` for maintenance actions. It does not
bootstrap databases from within the running web process.
