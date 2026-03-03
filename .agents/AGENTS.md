# .agents Directory

This directory contains agent-facing configuration and ecosystem context docs.

## Structure

- **README.md** - Orientation for `.agents` usage and cross-repo navigation
- **commands/** - Usage tools for various command-line tools or local APIs.
  - `lms.md` - info on the "lms" command line tool and the LMStudio API.
- **peer-repo/** - Status summaries of related repositories
  - `README.md` - Status file template and update checklist
  - `atacama-status.md` - Atacama CMS and backend infrastructure
  - `greenland-status.md` - Greenland linguistic database system
  - `trakaido-status.md` - Trakaido language learning applications
- **scripts/** - Validation tooling for `.agents` documentation
  - `validate_agents_docs.sh` - Checks required files/sections/headings

The peer-repo files provide assistants with context about how this repository
relates to other parts of the project ecosystem. Keep these files concise and
up to date when workflow or ownership boundaries change.
