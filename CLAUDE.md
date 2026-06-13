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
- M2 (collector: Kp-index + GOES X-ray feeds → normalize → idempotent index) — done 2026-06-13. Run host-side via `python -m collector [--once]`; verified live endpoint schemas (Kp `time_tag` is naive UTC; X-ray feed has two energy bands, we keep only the long 0.1-0.8nm channel). Idempotency = deterministic sha1 `_id` + bulk `op_type=create` (409 = skip). Severity ladders (`kp_to_severity`/`xray_to_severity`) live in collector/schema.py for the detector to reuse.
- M3 (full ingestion) — done 2026-06-13. All 7 SWPC feeds (Kp, X-ray, solar-wind plasma+mag, GOES protons, NOAA scales, official alerts) + 4 DONKI catalogs (FLR/CME/GST/SEP), one module each under collector/feeds/, registered in feeds.ALL. Per-feed cadence via `GROUP` (realtime/slow/donki) → collector/config.py `interval_for`. Solar wind uses the 6-hour windows (not 7-day) for light frequent polls. Added severity ladders `proton_to_severity` (S-scale) + `flare_class_to_severity`. `products/*` feeds are array-of-arrays (header row) → `schema.zip_header`; `build_event` gained an `extra` arg for queryable fields since `raw` is unindexed. Collector containerized (collector/Dockerfile) + compose `bootstrap` (one-shot) and `collector` services; compose `environment:` overrides ES_URL to the in-network address. DONKI key/lookback from env (DEMO_KEY default).
- M4 (detection engine) — done 2026-06-13. `rules/*.yaml` (geomagnetic_storm/radio_blackout/radiation_storm) loaded by `detector/`. Engine split: `engine.evaluate(rule, events, now)` is pure (unit-tested vs synthetic events); `es_gateway` fetches events + upserts alerts; `runner.run_cycle` glues them; `notifier` is a pluggable Protocol (default LogNotifier). Dedup/throttle = deterministic alert `_id = sha1(rule:entity:bucket)` overwritten each cycle (idempotent, restart-safe); new throttle bucket = re-alert; higher severity escalates in place. Detector reuses `event.severity` already stamped by the collector (no cross-package import). Containerized (detector/Dockerfile, COPYs rules/) + compose `detector` service. Run host-side via `python -m detector [--once]`.
- M5 (correlation + health rules 4–6) — done 2026-06-13. Rules now carry a `type`: `threshold` (M4, default), `precursor`, `chain`, `telemetry_loss`. `Rule` generalized — flat `dataset/field/op/threshold` replaced by `conditions: tuple[Condition]` (threshold=1, precursor=N AND'd, chain=ordered stages) + `monitors: tuple[Monitor]` (telemetry) + derived `datasets`/`lookback_s`; `Condition` is the one matcher shared across types (optional `field`/`threshold` for presence-only chain stages, plus `sustain_s`/`within_s`/`min_severity`). `engine.evaluate` dispatches on `type` to four pure evaluators sharing `_matches`; threshold output byte-for-byte preserved (M4 engine tests untouched). New rules: `storm_precursor` (Bz≤−10 sustained 30m AND speed>600, 1h window, sev 3), `solar_storm_chain` (donki.flr≥M → donki.cme within 6h → donki.gst Kp≥5 within 3d, walks back from the terminal storm → one incident per storm keyed by its ts, sev=max(floor 4, stage sevs), lookback override 4d), `telemetry_loss` (4 realtime feeds silent >10× their 1m cadence, one alert per feed keyed by dataset, sev 2). Correlation/health rules declare `severity` (their events are sev-0 metrics or silence); loader enforces it. `runner` fetches the rolling `now−lookback_s` window for non-threshold rules (threshold keeps the aligned bucket); `es_gateway.fetch_events(es, datasets, …)` now takes a dataset list (`terms`). No new feeds/endpoints. Alert doc shape unchanged → no template change. Tests: rules loader per type + engine vs synthetic mag/plasma/flare/cme/gst sets (82 pass).
- Next: M6 — Kibana dashboards (4 dashboards, export NDJSON to repo, bootstrap imports them)

When a milestone lands, tick it in the README roadmap and keep commits scoped to one milestone.
