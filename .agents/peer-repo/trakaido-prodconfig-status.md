# Trakaido Prodconfig - Current Status

## Repository Overview

**trakaido-prodconfig** holds the shared **production configuration and
deployment tooling** for the DigitalOcean server that hosts the ecosystem's
services. It is not an application: it is the glue that defines how the other
repositories are deployed, routed, and run in production. When a task involves
ports, domains, systemd units, NGINX routing, or where a service's code lives on
the server, this repo is the source of truth.

## What it manages

The repo maps each running service to its user, port, public domain, and source
repository. Services it deploys include:

- **newslettr-reader / -publisher / -admin** (ports 2201/2202/2203) →
  `shragafeivel.com`, `blog.pow3.com`, `earlyversion.com`, `earlyversion.com/admin/`
  — code from the **newslettr** repo.
- **atacama-web** (legacy blog, port 5000, rollback only) and **spaceship**
  (port 8998, `spaceship.computer`) — code from the **atacama** repo.
- **trakaido-api** (port 6370, `*.trakaido.com` app API) — served from an
  Atacama checkout; **trakaido-landing** (port 6010, `trakaido.com`).
- **barsukas** (port 5555, testing) — the **greenland** web UI.
- Other unrelated tenants on the same box (pow3web, dssres, yevaud) and the
  metrics/monitoring host (Prometheus + Perses).

Trakaido production domains fan out to landing (6010), per-language production
and staging app static builds (API 6370), and admin-authenticated reverse
proxies for metrics dashboards.

## Technical Architecture

Plain configuration, organized by concern:

```
prodconfig/
├── README.md
├── services/     # systemd service files
├── nginx/        # nginx site configs
├── env/          # environment file templates (*.env.example)
├── monitoring/   # Prometheus / Perses config
├── sudoers/      # sudoers entries for deploy users
└── scripts/      # deploy-all.sh, status.sh, verify.sh
```

## Development Workflow

- **Secrets are never committed.** Environment files hold secrets and live on the
  server under each service user's `keys/` directory; the repo ships only
  `*.env.example` templates.
- Deployment helpers live in `scripts/` (`deploy-all.sh`, `status.sh`,
  `verify.sh` for comprehensive verification).
- Service files and NGINX configs are deployed to the server; config changes
  generally require a service restart.

## Integration with Ecosystem

This repo is the deployment layer beneath **newslettr**, **atacama**,
**trakaido**, and **greenland** (barsukas). It does not contain application
logic; instead it pins where each app runs, on which port, behind which domain,
and as which system user. Cross-repo questions about production topology — "which
domain serves the Trakaido API?", "where does newslettr's admin route?" — are
answered here.

## Current State

An actively maintained, configuration-only repository tracking the live
DigitalOcean deployment. It reflects the current production topology of the
ecosystem's services and is updated as services, ports, or domains change.
