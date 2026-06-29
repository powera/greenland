# Ecosystem Agents Directory

This directory holds agent-facing documentation for this repo and cross-repo
context for the wider project ecosystem. It is a lightweight summary of what the
sibling repositories are for, so agents can understand references between projects
before making assumptions about where code lives.

## What lives here

- **AGENTS.md** - Scope + structure notes for this folder
- **README.md** - This file; quick orientation and maintenance workflow
- **peer-repo/** - High-level status snapshots for the ecosystem repositories
  - `newslettr-status.md` - Go batched-publishing system (AML)
  - `atacama-status.md` - CMS/blog backend and the Trakaido Stats API
  - `trakaido-status.md` - App clients (React / Swift / Kotlin) and content consumer
  - `greenland-status.md` - Linguistic data generation and export pipeline
  - `trakaido-prodconfig-status.md` - Production deployment config
  - `README.md` - Status file template + update checklist
- **scripts/** - Lightweight helpers for validating `.agents` docs
- **commands/** - (optional, repo-specific) CLI / local-API usage notes

## The ecosystem at a glance

- **greenland** generates linguistic data → **trakaido** consumes it across its
  React/Swift/Kotlin clients.
- **atacama** hosts the Trakaido Stats API (cloud sync, auth) and is also a
  CMS/blog publishing platform with an AML markup language.
- **newslettr** is a separate Go batched-publishing system that shares the AML
  concept with Atacama.
- **trakaido-prodconfig** is the deployment layer: it pins ports, domains,
  systemd units, and NGINX routing for the services above on the shared server.

## Maintenance workflow for `.agents`

1. Update the relevant `peer-repo/*-status.md` file.
2. Keep the first heading as `# <Repo> - Current Status`.
3. Run the validation helper:

   ```bash
   bash .agents/scripts/validate_agents_docs.sh
   ```

4. Sync the same `peer-repo/` content to the other repos (these files are meant
   to be identical everywhere), and commit with a message that references
   `.agents`.
