# Space-Weather SIEM

A complete SIEM (Security Information and Event Management) pipeline where the "threats" are **space-weather events** instead of security logs.

The bet: space weather is structurally identical to security telemetry — noisy real-time feeds from remote sensors, discrete events of varying severity, heterogeneous sources that need normalizing into one schema, detection rules that fire on threshold crossings, and alerting/dashboards on top. This project practices the full detection-engineering loop — **ingest → normalize → detect → alert → visualize** — on data that is free, public, schema-stable, and genuinely interesting.

## The analogy

| SIEM concept | Space-weather equivalent |
|---|---|
| Log sources / endpoints | NOAA SWPC real-time feeds (GOES, DSCOVR), NASA DONKI |
| Log collection / forwarders | Scheduled feed pollers (Python collector) |
| Normalization to a common schema (ECS) | One ECS-inspired event schema across all feeds |
| Severity taxonomy (low → critical) | NOAA G/R/S scales (G1–G5, R1–R5, S1–S5) |
| Threshold detection rules | Kp ≥ 5, X-ray flux ≥ M-class, proton flux ≥ 10 pfu |
| Multi-stage attack chain (kill chain) | Solar flare → CME → geomagnetic storm sequence |
| Alert dedup / throttling | Fingerprinted alerts, no re-alerting while active |
| "Log source down" detection | Telemetry-loss rule (feed silent for N × cadence) |
| Attack simulation / purple team | Replay of a historical G5 storm (May 2024 Gannon storm) |
| SOC dashboards | Kibana: alert triage, geomagnetic, solar activity, pipeline health |

And the "so what" of every alert is concrete: geomagnetic storms degrade GPS/GNSS accuracy and induce currents in power grids, radio blackouts knock out HF communications, radiation storms damage satellites and threaten polar-route aviation.

## Architecture

```mermaid
flowchart LR
    A[NOAA SWPC<br/>JSON feeds] --> C[collector<br/>Python pollers]
    B[NASA DONKI<br/>event catalog] --> C
    C -->|normalized events| E[(Elasticsearch<br/>space-weather-events)]
    E --> D[detector<br/>YAML rule engine]
    D -->|dedup + throttle| F[(space-weather-alerts)]
    E --> K[Kibana dashboards]
    F --> K
```

Four containers via `docker-compose`: **elasticsearch**, **kibana**, **collector**, **detector** — plus a one-shot bootstrap that applies index templates/ILM and imports dashboards.

## Data sources (all free)

- **NOAA SWPC** (`services.swpc.noaa.gov`, no API key): planetary K-index, solar wind plasma & magnetometer (DSCOVR), GOES X-ray flux, GOES proton flux, current NOAA scales, official alerts.
- **NASA DONKI** (`api.nasa.gov/DONKI`, free key): solar flares, CMEs, geomagnetic storms, SEP events — fuels the multi-stage correlation rule and historical replay.

## Detection rules

Rules live as YAML in [`rules/`](rules/) — detection-as-code, reviewed like any other code:

1. **Geomagnetic storm** — Kp ≥ 5, severity mapped to G1–G5
2. **Radio blackout** — GOES X-ray flux at M/X-class thresholds → R1–R5
3. **Radiation storm** — ≥10 MeV proton flux ≥ 10 pfu → S1–S5
4. **Storm precursor** — southward Bz ≤ −10 nT sustained + solar wind > 600 km/s (correlation)
5. **Event chain** — flare → CME within 6 h → Kp ≥ 5 within 1–3 days (multi-stage correlation)
6. **Telemetry loss** — a feed goes silent (the "log source down" classic)

## Quickstart

```sh
cp .env.example .env   # set passwords; add a NASA API key for higher DONKI limits
docker compose up -d   # ES + Kibana, one-shot bootstrap (templates/ILM), then the collector
```

That's the whole pipeline: `bootstrap` applies the index templates + ILM, `collector` polls all seven SWPC feeds and the four NASA DONKI catalogs on per-feed cadences (60 s / 5 min / 15 min) and indexes into `space-weather-events`, and `detector` evaluates the YAML rules in [`rules/`](rules/) every minute, writing deduped/throttled alerts to `space-weather-alerts`. Watch them with `docker compose logs -f collector detector`.

Kibana is at <http://localhost:5601> — log in as `elastic` with your `ELASTIC_PASSWORD`. On Linux hosts, Elasticsearch needs `sysctl -w vm.max_map_count=262144` first (Docker Desktop and OrbStack handle this for you).

To run the collector outside Docker (dev/tests), it reads `.env` automatically:

```sh
python -m venv .venv && .venv/bin/pip install -r collector/requirements.txt
.venv/bin/python -m collector --once   # one pass over every feed, then exit
```

> 🚧 Space weather is usually quiet, so the threshold rules rarely fire on live data. Correlation rules, dashboards, and replay land with M5–M7 — see the [roadmap](#roadmap). Coming up: `python scripts/replay.py` to replay the May 2024 G5 storm so every rule fires on demand.

## Roadmap

- [x] **M0** — Repo bootstrap: README, license, CI stub
- [x] **M1** — Elasticsearch + Kibana via docker-compose, index templates + ILM
- [x] **M2** — First ingestion: Kp-index + X-ray feeds, normalizer + tests
- [x] **M3** — Full ingestion: all SWPC feeds + DONKI, idempotent indexing
- [x] **M4** — Detection engine: YAML rules, threshold rules 1–3, alert dedup/throttle
- [ ] **M5** — Correlation rules 4–6
- [ ] **M6** — Kibana dashboards (exported to repo as NDJSON)
- [ ] **M7** — Historical-storm replay + runbooks + screenshots

The full implementation plan is in [docs/PLAN.md](docs/PLAN.md).

## License

[MIT](LICENSE)
