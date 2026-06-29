# .agents Directory

This directory contains agent-facing configuration and ecosystem context docs.
Its core purpose is to give agents a lightweight, predictable summary of what the
sibling repositories are for, so references between projects can be understood
without guessing where code lives.

## Structure

- **README.md** - Orientation for `.agents` usage and the maintenance workflow
- **peer-repo/** - Status summaries of the repositories in the ecosystem
  - `README.md` - Status file template and update checklist
  - `newslettr-status.md` - Newslettr Go batched-publishing system
  - `atacama-status.md` - Atacama CMS/blog and Trakaido Stats API backend
  - `trakaido-status.md` - Trakaido language-learning app clients
  - `greenland-status.md` - Greenland linguistic database system
  - `trakaido-prodconfig-status.md` - Production deployment configuration
- **scripts/** - Validation tooling for `.agents` documentation
  - `validate_agents_docs.sh` - Checks required files/sections/headings
- **commands/** - (optional, repo-specific) usage notes for command-line tools or
  local APIs; e.g. greenland's `lms.md` covers the LM Studio CLI and API.

The `peer-repo/` files are kept identical across every repo in the ecosystem.
Keep them concise and up to date when workflow or ownership boundaries change,
and run `scripts/validate_agents_docs.sh` after edits.
