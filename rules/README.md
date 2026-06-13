# Detection rules

Detection-as-code: each `*.yaml` here is one rule, loaded by the `detector/`
engine. Treat them like code — review changes, keep them in version control.

## Schema

```yaml
id: geomagnetic_storm          # unique rule id (also the alert's rule.id)
name: Geomagnetic Storm        # human label (alert's rule.name)
description: >                  # what it detects + real-world impact
  ...
category: geomagnetic          # event.category stamped on the alert
scale: G                       # G/R/S label prefix for the severity in messages
query:
  dataset: swpc.planetary_k_index   # which event.dataset to evaluate
  field: metrics.kp_index           # numeric field to threshold (dotted path)
  op: ">="                          # >=, >, <=, <, ==
  threshold: 5                      # value to compare against
throttle: 1h                   # re-alert / dedup bucket (e.g. 30s, 15m, 1h, 2d)
```

## How evaluation works

Every `DETECTOR_INTERVAL` seconds the engine, per rule:

1. Fetches events of `query.dataset` in the **current throttle bucket**
   (`[bucket_start, now]`, where buckets are fixed windows of length `throttle`).
2. Keeps the events where `field op threshold` holds.
3. If any match, upserts a single alert into `space-weather-alerts` whose `_id`
   is `sha1(rule.id : entity : bucket)` — so re-evaluating the same bucket
   **updates in place** (dedup + throttle) rather than spamming new alerts.

The alert aggregates the bucket's matches: `event.severity` = the max severity
already stamped on those events by the collector (the G/R/S mapping), `alert.count`
= number of breaching events, `alert.first_seen` / `alert.last_seen` = their time
span. A new bucket produces a fresh alert (the re-alert period). Within a bucket,
a higher-severity event escalates the alert in place.
