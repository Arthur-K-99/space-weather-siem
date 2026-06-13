# Detection rules

Detection-as-code: each `*.yaml` here is one rule, loaded by the `detector/`
engine. Treat them like code — review changes, keep them in version control.

A rule's `type` selects how the engine evaluates it. All rules share the same
metadata header and emit the same alert shape; only the matching logic differs.

| `type` | Rule | What it detects |
|---|---|---|
| `threshold` | geomagnetic_storm, radio_blackout, radiation_storm | one field crosses a threshold |
| `precursor` | storm_precursor | several conditions hold together over a window, one *sustained* |
| `chain` | solar_storm_chain | ordered stages each occur within a gap of the previous |
| `telemetry_loss` | telemetry_loss | a monitored feed has gone silent ("log source down") |

## Common header (every rule)

```yaml
id: geomagnetic_storm     # unique rule id (also the alert's rule.id)
name: Geomagnetic Storm   # human label (alert's rule.name)
description: > ...        # what it detects + real-world impact
category: geomagnetic     # event.category stamped on the alert
scale: G                  # G/R/S/H label prefix used in alert messages
type: threshold           # threshold | precursor | chain | telemetry_loss (default threshold)
severity: 3               # declared 0-5 severity — REQUIRED for every type except threshold
throttle: 1h              # re-alert / dedup bucket (e.g. 30s, 15m, 1h, 2d)
```

`threshold` rules derive severity from the events themselves (the G/R/S scale the
collector already stamped), so they omit `severity`. The correlation/health rules
match on severity-0 metrics (solar wind, CME) or on silence, so they declare a
severity floor.

## `threshold` — one field over a limit (rules 1-3)

```yaml
query:
  dataset: swpc.planetary_k_index   # which event.dataset to evaluate
  field: metrics.kp_index           # numeric field to threshold (dotted path)
  op: ">="                          # >=, >, <=, <, ==
  threshold: 5
```

Fetches events of `query.dataset` in the **current throttle bucket**, keeps those
where `field op threshold` holds, and upserts one alert. `event.severity` = the
max severity on the matching events; `alert.count` = number of breaches;
`first_seen`/`last_seen` = their span.

## `precursor` — conditions that hold together over a window (rule 4)

```yaml
type: precursor
window: 1h                # rolling look-back to evaluate over
conditions:               # ALL must hold (logical AND)
  - dataset: swpc.solar_wind_mag
    field: metrics.bz_gsm
    op: "<="
    threshold: -10
    sustain: 30m          # the matching readings must span >= this duration
  - dataset: swpc.solar_wind_plasma
    field: metrics.speed_km_s
    op: ">"
    threshold: 600
```

Fires when every condition has a match in the look-back `window` and any
`sustain` condition's matches span at least that long. (`sustain` is a coarse
proxy — first-to-last span of the qualifying readings, not gap-free continuity.)

## `chain` — multi-stage correlation (rule 5)

```yaml
type: chain
lookback: 4d              # optional: widen the fetch (default = sum of within gaps)
stages:                   # ordered; each must occur after the previous
  - name: flare
    dataset: donki.flr
    min_severity: 1       # gate on the stamped severity (>= M-class)
  - name: cme
    dataset: donki.cme
    within: 6h            # ... within this gap after the flare
  - name: storm
    dataset: donki.gst
    field: metrics.kp_index
    op: ">="
    threshold: 5
    within: 3d            # ... within this gap after the CME
```

For each event matching the **last** stage, the engine walks backward picking the
closest preceding match for each earlier stage within its `within` gap. A complete
walk emits **one composite incident** keyed by the terminal event (so two flares
feeding one storm yield one alert, not two). `event.severity` = max of the floor
and the stages' severities; `first_seen`/`last_seen` span the chain.

## `telemetry_loss` — feed-down detection (rule 6)

```yaml
type: telemetry_loss
monitors:
  - dataset: swpc.planetary_k_index
    cadence: 1m
    multiplier: 10        # alert if silent for > cadence x multiplier (= 10 min)
```

One alert **per monitored feed** whose most recent document is older than
`cadence x multiplier` (or which has no documents at all in the look-back). The
alert's `entity` is the feed, so each down feed deduplicates independently;
`alert.count` = whole missed intervals of silence.

## Dedup, throttle, escalation (all types)

Every alert's `_id` is `sha1(rule.id : entity : bucket)` where `bucket` is the
fixed `throttle`-length window containing `now`. Re-evaluating the same bucket
**updates the alert in place** (dedup + throttle); a new bucket re-alerts; a
higher severity escalates in place. `entity` is `global` for threshold/precursor,
the terminal-event time for a chain, and the feed for telemetry loss.
