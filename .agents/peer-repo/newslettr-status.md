# Newslettr - Current Status

## Repository Overview

**Newslettr** is a small, self-hosted publishing system for **batched** updates,
written in **Go**. Authors stage posts, links, and calendar entries throughout
the week; when ready, they assemble a single **Newsletter** and send it — one
considered digest rather than a stream of notifications. The newsletter is the
unit of output (see `PHILOSOPHY.md`).

Posts are written in **AML**, a color/semantic markup language conceptually
shared with Atacama. Newslettr parses AML into an AST and renders safe HTML,
storing both the raw source and the rendered output (`STYLE.md`).

## Architecture

Newslettr is split into separately-served sections, each its own binary with a
scoped session cookie and static asset tree. Cookies are **not** interchangeable
between sections.

| Section       | Binary                     | Default port | Audience                      |
| ------------- | -------------------------- | ------------ | ----------------------------- |
| **Reader**    | `cmd/newslettr-reader`     | `2201`       | Subscribers and the public    |
| **Publisher** | `cmd/newslettr-publisher`  | `2202`       | Authors writing content       |
| **Admin**     | `cmd/newslettr-admin`      | `2203`       | Operators and moderators      |
| **MCP**       | `cmd/newslettr-mcp`        | `2204`       | Read-only project/context API |
| **Worker**    | `cmd/newslettr-worker`     | —            | Background jobs (skeleton)    |

Supporting binaries live alongside these: `newslettr-seed` (idempotent admin +
starter topics), `newslettr-load-domains` (loads domain/topic config into
Postgres), `newslettr-dev`, and importers (`newslettr-import-atacama`,
`newslettr-import-git`, `newslettr-import-substack`).

## Technical Architecture

- **Language**: Go (module `newslettr`, Go 1.25+).
- **Database**: PostgreSQL via `pgx/v5` (shared Supabase Postgres `newslettr`
  schema in development).
- **Views**: rendered through **templ** components in `internal/views/`
  (`*.templ` source compiled to generated `*_templ.go` — never hand-edit the
  generated files; regenerate per-file).
- **Internal packages** (`internal/`): `aml` (markup pipeline), `app` (per-section
  HTTP apps and routes), `auth`/`sessions`/`csrf` (security), `store`/`models`
  (data layer), `newsletter`/`digest` (assembly + send), `calendar`, `mailer`,
  `llm`, `mcpserver`, and importers (`atacamaimport`, `gitimport`,
  `substackimport`).
- **MCP server**: read-only, low-token, store-backed; stdio-first with optional
  local HTTP (`NEWSLETTR_MCP_TRANSPORT=http`, default `127.0.0.1:2204`).

## Development Workflow

- `go` is not on the default non-login PATH; use `/usr/local/go/bin/go`. The
  templ generator is `$HOME/go/bin/templ` (keep version in sync with `go.mod`).
- `./run_dev_server.sh` builds and runs Reader/Publisher/Admin against the shared
  Postgres schema after seeding. Seed admin: `admin@newslettr.local` /
  `newslettr-dev`.
- Standard checks: `go build ./...`, `go test ./...`. Test views by rendering
  components directly and exercise routes through the in-process
  `internal/app/apptest` harness; do **not** write login/session-based HTTP tests
  against a running server.
- Reference docs in the repo: `README.md`, `PHILOSOPHY.md`, `STYLE.md`,
  `API.md`, `BACKEND.md`, `MCP.md`, `GO_IMPLEMENTATION_PLAN.md`.

## Integration with Ecosystem

- Shares the **AML** markup concept with **Atacama** and can import legacy
  content from it (`newslettr-import-atacama`).
- Deployed alongside the other ecosystem services on the shared DigitalOcean
  server; **trakaido-prodconfig** owns the systemd units, NGINX routing, and
  environment templates for the Reader/Publisher/Admin binaries
  (`shragafeivel.com`, `blog.pow3.com`, `earlyversion.com`).

## Current State

The core servers (Reader, Publisher, Admin), data model, auth/sessions, AML
pipeline, and the mobile JSON/token API are implemented. Remaining work centers
on calendar import and the forward-looking parts of newsletter assembly
(see `BACKEND.md`). The Worker binary is currently a skeleton.
