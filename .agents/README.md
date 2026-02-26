# Greenland Database Agents

This directory contains agent-facing documentation for the Greenland repo and
cross-repo context for the wider Trakaido ecosystem.

## What lives here

- **AGENTS.md** - Scope + structure notes for this folder
- **README.md** - This file; quick orientation and maintenance workflow
- **peer-repo/** - High-level status snapshots for sibling repositories
  - `trakaido-status.md` - App clients (React/Swift/Kotlin) and content consumer
  - `greenland-status.md` - Linguistic data generation and export pipeline
  - `atacama-status.md` - API/CMS/backend services
  - `README.md` - Status file template + update checklist
- **scripts/** - Lightweight helpers for validating `.agents` docs

## Why this exists

When working in Greenland, tasks often require context from **Trakaido** and
**Atacama**. This folder gives agents a predictable place to check ecosystem
status before making assumptions about where code lives.

## Fast cross-repo orientation

If a task references UI behavior (for example Kotlin app screens), verify the
repository first before editing:

```bash
# From /workspace/greenland
for d in ../trakaido ../atacama .; do
  if [ -d "$d/.git" ]; then
    echo "repo: $d"
  fi
done
```

Then use the matching status file in `peer-repo/` for context.

## Greenland agent invocation pattern

All Greenland Python agents follow:

```bash
PYTHONPATH=src python3 src/agents/<agent-name>.py [options]
```

Examples:

```bash
PYTHONPATH=src python3 src/agents/lokys.py --help
PYTHONPATH=src python3 src/agents/ungurys.py --help
```

## Maintenance workflow for `.agents`

1. Update the relevant `peer-repo/*-status.md` file.
2. Keep the first heading as `# <Repo> - Current Status`.
3. Run the validation helper:

```bash
bash .agents/scripts/validate_agents_docs.sh
```

4. Commit doc changes with a message that references `.agents`.
