# Space-Weather SIEM — Implementation Plan

## Context

Build a portfolio-grade SIEM pipeline where the "threats" are space-weather events: ingest → normalize → detect → alert → visualize, using free public feeds. The goal is to demonstrate detection-engineering skills (Elastic, ingestion pipelines, detection-rules-as-code, severity taxonomies, alert dedup/throttling, dashboards) without needing a SOC or sensitive logs. The README explicitly sells the analogy: NOAA scales ≈ severity levels, flare→CME→geomagnetic-storm ≈ multi-stage attack chain, feed polling ≈ log collection.

**Decisions made with user:**
- **Stack:** Elastic Stack (Elasticsearch + Kibana, free basic license, single-node Docker)
- **Language:** Python for collector + detection engine
- **Alert routing:** dedicated alerts index + Kibana triage dashboard only (no external webhooks; design a pluggable notifier interface so one can be added later)
- **Sources:** NOAA SWPC real-time feeds + NASA DONKI event catalog
- **Execution:** NOT on this machine — plan targets any Docker host; first step is creating the GitHub repo

## Architecture

```
NOAA SWPC JSON feeds ──┐
                       ├─► collector (Python, scheduled pollers)
NASA DONKI API ────────┘        │ normalize to common event schema
                                ▼
                    Elasticsearch (data stream: space-weather-events)
                                │
                  detector (Python rule engine, YAML rules in repo)
                                │ dedup + throttle
                                ▼
                    space-weather-alerts index ──► Kibana dashboards
```

Four containers via `docker-compose`: `elasticsearch`, `kibana`, `collector`, `detector`. A one-shot `bootstrap` step applies index templates/ILM and imports Kibana saved objects.

## Data sources (all free)

NOAA SWPC (no API key, JSON, base `https://services.swpc.noaa.gov`):
| Feed | Endpoint | Cadence |
|---|---|---|
| Planetary K-index | `/json/planetary_k_index_1m.json` | 1 min |
| Solar wind plasma (speed/density/temp) | `/products/solar-wind/plasma-7-day.json` | 1 min |
| Solar wind magnetometer (Bz/Bt) | `/products/solar-wind/mag-7-day.json` | 1 min |
| GOES X-ray flux | `/json/goes/primary/xrays-1-day.json` | 1 min |
| GOES integral proton flux | `/json/goes/primary/integral-protons-1-day.json` | 5 min |
| NOAA scales (current G/R/S) | `/products/noaa-scales.json` | on change |
| SWPC alerts/watches/warnings | `/products/alerts.json` | on change |

NASA DONKI (`https://api.nasa.gov/DONKI/{CME,FLR,GST,SEP}`, free API key / `DEMO_KEY`): discrete events for flares, CMEs, geomagnetic storms — fuels the multi-stage correlation rule and historical replay.

Endpoints must be re-verified against live responses during M2/M3 (paths are from knowledge; SWPC occasionally reshuffles products).

## Normalized event schema (ECS-inspired)

```
@timestamp, event.kind (metric|event|alert), event.category
(geomagnetic|solar_wind|xray|solar_radiation|radio_blackout|cme|flare),
event.severity (0–5, mapped from NOAA G/R/S scales), event.dataset,
observer.name (GOES-18, DSCOVR, ...), source.feed, source.url,
metrics.* (kp_index, bz_gsm, bt, speed_km_s, density, xray_flux, proton_flux_10mev, ...),
raw (original record)
```

Indexed into data stream `space-weather-events` with an index template + ILM policy. Alerts go to `space-weather-alerts` with `rule.id`, `rule.name`, `event.severity`, `alert.fingerprint`, `alert.first_seen/last_seen`, `alert.count`.

## Detection rules as code

YAML files in `rules/`, loaded by the Python engine; each has `id`, `name`, `description`, `severity`, `query` (ES DSL or simple field/threshold spec), `window`, `throttle`, `dedup_key`. Initial rule set:

1. **Geomagnetic storm** — Kp ≥ 5 → severity by Kp (5→G1 … 9→G5)
2. **Radio blackout** — X-ray flux ≥ 1e-5 W/m² (M-class → R1/R2), ≥ 1e-4 (X-class → R3+)
3. **Radiation storm** — ≥10 MeV proton flux ≥ 10 pfu → S1..S5 ladder
4. **Storm precursor (correlation)** — Bz ≤ −10 nT sustained ≥ 30 min AND solar wind speed > 600 km/s
5. **"Attack chain" (multi-stage correlation)** — DONKI flare → CME within 6 h → Kp ≥ 5 within 1–3 days ⇒ composite incident alert
6. **Telemetry loss** — no documents from a feed for N × its cadence (the "log source down" detection — very SIEM)

Engine responsibilities: scheduled evaluation, dedup by fingerprint (rule + entity + time bucket), throttling (don't re-alert while an alert is active; update `last_seen`/`count` instead), severity escalation (re-alert if severity increases).

## Demo/replay capability (important)

Space weather is quiet most of the time, so include `scripts/replay.py`: backfills a historical storm (e.g., the May 2024 Gannon storm, G5) from DONKI + SWPC archive JSON fixtures committed to the repo, with timestamps optionally rebased to "now" so every detection rule demonstrably fires. This is the purple-team/attack-simulation analog and makes demos deterministic.

## Kibana dashboards (exported as NDJSON into repo)

1. **SOC Overview** — open alerts by severity, current NOAA scales, event volume timeline
2. **Geomagnetic** — Kp gauge/history, Bz/Bt, solar wind speed & density
3. **Solar Activity** — X-ray flux (log scale) with flare class bands, proton flux, DONKI CME/flare event markers
4. **Pipeline Health** — docs per feed, ingest lag, feed-down status

## Repo layout

```
space-weather-siem/
├── README.md                  # analogy table, architecture diagram, screenshots, quickstart
├── docker-compose.yml
├── .env.example               # ES creds, NASA API key, poll intervals
├── collector/                 # Dockerfile, feeds/ (one module per source), normalizer, ES writer
├── detector/                  # Dockerfile, rule loader, evaluation engine, alert writer, notifier interface
├── rules/                     # YAML detection rules (the "rules as code" artifact)
├── elastic/                   # index templates, ILM policy, bootstrap script
├── kibana/                    # dashboard saved objects (NDJSON)
├── scripts/                   # bootstrap.py, replay.py
├── tests/                     # pytest: normalizers against recorded JSON fixtures, rule-engine unit tests
├── docs/                      # SIEM-analogy writeup, alert runbooks (1 per rule: impact + response)
└── .github/workflows/ci.yml   # ruff + pytest
```

## Milestones (each ends in a working increment + commit)

- **M0 — Repo bootstrap:** `gh repo create space-weather-siem --public`; README skeleton with the analogy pitch, MIT license, .gitignore, CI stub.
- **M1 — Stack up:** docker-compose with single-node ES + Kibana (basic license, security on), bootstrap script applies index template + ILM. Verify: Kibana reachable, template installed.
- **M2 — First ingestion:** collector polls 2 feeds (Kp index, X-ray flux), normalizes, indexes. Verify live endpoint schemas here. Tests: normalizer fixtures.
- **M3 — Full ingestion:** remaining SWPC feeds + DONKI poller; per-feed cadence config; checkpointing to avoid duplicate ingestion (deterministic `_id` from source+timestamp).
- **M4 — Detection engine:** YAML rule loader, threshold rules 1–3, alerts index, dedup/throttle logic. Tests: rule evaluation against synthetic event sets.
- **M5 — Correlation + health rules:** rules 4–6 (windowed correlation, multi-stage chain, telemetry loss).
- **M6 — Dashboards:** build the 4 Kibana dashboards, export NDJSON to repo, bootstrap imports them.
- **M7 — Replay + polish:** historical-storm replay script with committed fixtures; README with architecture diagram, analogy table, dashboard screenshots, runbooks.

## Verification

- **CI:** ruff + pytest on every push (normalizers vs recorded fixtures; rule engine vs synthetic events).
- **End-to-end:** `docker compose up` → bootstrap → wait one poll cycle → events visible in Kibana Discover → run `scripts/replay.py` → all 6 rules fire → alerts appear deduplicated on the SOC Overview dashboard.
- **Idempotency:** re-running collector/replay must not duplicate events (deterministic document IDs).
