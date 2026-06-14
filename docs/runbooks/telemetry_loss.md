# Telemetry Loss — runbook

**Rule:** `telemetry_loss` · **Type:** telemetry_loss (health) · **Throttle:** 1h · **Severity:** 2 (declared)
**Trigger:** a monitored feed has produced no documents for **> 10 × its 1-min cadence** (~10 min).
Monitored: `swpc.planetary_k_index`, `swpc.goes_xray`, `swpc.solar_wind_mag`, `swpc.solar_wind_plasma`.
One alert per silent feed, keyed by dataset.

## What it detects
A detection source has gone dark. This is the space-weather analog of a SIEM **"log
source down" / dead-agent** alert — silence is itself an incident, because a feed
that isn't reporting can't trigger any of the other rules. A coverage gap blinds
the pipeline exactly when you can least afford it (instruments do drop out during
severe storms).

## Why it matters
- **Detection blind spot:** while a feed is silent, storms on that channel go unseen.
- **Root cause is usually one of:** the collector/poller is down, the upstream SWPC
  endpoint changed or is failing, a network/credential issue, or a genuine
  spacecraft telemetry gap (e.g. a DSCOVR solar-wind dropout).

## Triage
1. Open **Pipeline Health** dashboard → **Feed Last-Seen** table — which feed(s),
   and how long since the last document?
2. Is it one feed or several? One feed → likely an upstream/endpoint issue for that
   source. All feeds → the collector itself is down.
3. Check the collector logs: `docker compose logs --tail=50 collector`.
4. Hit the upstream endpoint directly (URLs in [`collector/feeds/`](../../collector/feeds/))
   to tell "SWPC is down" from "our collector is down".

## Response / escalation
- **Collector down:** restart it (`docker compose restart collector`); confirm the
  feed resumes on the **Pipeline Health** dashboard.
- **Upstream endpoint moved/changed:** update the feed module's URL/parser (the
  SWPC `products/*` paths do occasionally reshuffle) and redeploy.
- **Genuine spacecraft gap:** nothing to fix locally; note it, and remember any
  storm rules depending on that feed are degraded until it returns.
- The alert auto-clears (stops re-firing) once the feed reports within cadence again.

## Note for the replay demo
This rule is *absence* detection, so it only fires when a feed is genuinely silent.
[`scripts/replay.py`](../../scripts/replay.py) holds the plasma feed ~18 min short
of "now" so it fires in a replay-only run; with the live collector polling, that
feed stays fresh and the rule correctly stays quiet. To see it live, stop the
source — `docker compose stop collector` — and re-run the detector.

## References
- Detection rule: [`rules/telemetry_loss.yaml`](../../rules/telemetry_loss.yaml)
