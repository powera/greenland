# Peer Repo Status Files

These files summarize the current state of the repositories that make up the
project ecosystem. They are synced identically across every participating repo so
that, from inside any one repo, an agent can orient on the others.

## Required files

- `newslettr-status.md` - Go batched-publishing system (AML; Reader/Publisher/Admin)
- `atacama-status.md` - CMS/blog, React widgets, and the Trakaido Stats API backend
- `trakaido-status.md` - Language-learning app clients (React / Swift / Kotlin)
- `greenland-status.md` - Linguistic database and WireWord data generation pipeline
- `trakaido-prodconfig-status.md` - Production deployment config (systemd, NGINX, env)

## Required structure

Each status file should include:

1. Title: `# <Repo> - Current Status`
2. `## Repository Overview`
3. `## Technical Architecture` (or equivalent)
4. `## Development Workflow` (or equivalent)
5. `## Current State`

## Update checklist

- Prefer short, factual updates over speculative roadmap notes.
- Mention where code for each platform actually lives.
- Call out build/test entry points when known.
- Keep sections skimmable with headings and bullets.
- When you change a status file, sync the same content to every repo's
  `.agents/peer-repo/` (these files are intended to be identical everywhere).
