# CLAUDE.md

## What this project is

A portfolio detection-engineering lab: a full SIEM pipeline (ingest → normalize → detect → alert → visualize) where the "threats" are space-weather events from NOAA SWPC and NASA DONKI instead of security logs. The point is to demonstrate SIEM concepts — normalization, severity taxonomy, detection-rules-as-code, alert dedup/throttling, dashboards — on free public data.

**Read [docs/PLAN.md](docs/PLAN.md) first.** It contains the full architecture, data-source endpoints, event schema, rule set, repo layout, and milestones. The README's roadmap checklist shows which milestone is current.

## Decisions already made (don't relitigate)

- **Stack:** Elastic Stack — single-node Elasticsearch + Kibana, free basic license, via docker-compose
- **Language:** Python for both `collector/` and `detector/`
- **Alert routing:** alerts index + Kibana triage dashboard only; notifier interface kept pluggable but no external webhooks for now
- **Sources:** NOAA SWPC real-time feeds (no key) + NASA DONKI (free key, `NASA_API_KEY` in `.env`)
- **Rules live as YAML in `rules/`** — that directory is a deliverable, treat it as code

## Conventions

- Events go to the `space-weather-events` data stream, alerts to `space-weather-alerts`; schema is ECS-inspired (see PLAN.md)
- Indexing must be idempotent: deterministic `_id` derived from source + record timestamp
- Severity is the NOAA G/R/S scale mapped to 0–5; every rule maps to it
- Tests: pytest, normalizers tested against recorded JSON fixtures in `tests/`, rule engine against synthetic event sets
- Lint: ruff (CI runs `ruff check .` and pytest on every push)
- SWPC endpoint paths in PLAN.md were written from knowledge — verify each against the live API the first time a feed module is implemented

## Milestone status

- M0 (repo bootstrap) — done 2026-06-11
- M1 (docker-compose ES + Kibana, index templates + ILM via scripts/bootstrap.py) — done 2026-06-11, Elastic Stack pinned to 9.4.2
- Next: M2 — collector polls Kp-index + X-ray feeds, normalizer + fixture tests

When a milestone lands, tick it in the README roadmap and keep commits scoped to one milestone.
